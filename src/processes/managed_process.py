from __future__ import annotations

import time
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from threading import Event, Lock
from typing import Any, Mapping, Protocol
from uuid import UUID, uuid4

from loguru import logger

from processes.models import (
    ProcessCallbacks,
    ProcessLine,
    ProcessResult,
    ProcessState,
    StreamType,
)
from processes.reader import ProcessOutputReader
from processes.runner import ProcessRunner
from processes.utils import (
    DEFAULT_ERROR_FLAGS,
    emit_log,
    is_error_line,
)


class ManagedProcessProtocol(Protocol):
    title: str
    command: list
    timeout: int | float | None
    error_flags: frozenset[str]
    log_level: str
    metadata: dict

    callbacks: ProcessCallbacks

    runner: ProcessRunner
    result: ProcessResult

    def run(self) -> ProcessResult: ...
    def stop(
        self,
        force: bool = False,
        timeout: int | float = 1,
    ) -> None: ...

    def write_stdin(self, data: str, flush: bool = False) -> None: ...

    @property
    def uid(self) -> UUID: ...

    def __hash__(self) -> int: ...
    def __eq__(self, other: Any) -> bool: ...
    def __str__(self) -> str: ...
    def __repr__(self) -> str: ...


class ManagedProcess(ManagedProcessProtocol):
    def __init__(
        self,
        title: str,
        command: list,
        *,
        cwd: str | Path | None = None,
        env: Mapping[str, str] | None = None,
        encoding: str = "utf-8",
        shell: bool = False,
        timeout: float | int | None = None,
        merge_stderr: bool = False,
        capture_output: bool = False,
        max_output_lines: int = 1000,
        error_flags: frozenset[str] = DEFAULT_ERROR_FLAGS,
        log_level: str = "INFO",
        metadata: dict | None = None,
        callbacks: ProcessCallbacks | None = None,
    ) -> None:
        self.title = title
        self.command = command

        self.timeout = timeout
        self.error_flags = error_flags
        self.log_level = log_level
        self.metadata = metadata or {}

        self.callbacks = callbacks or ProcessCallbacks()

        self.runner = ProcessRunner(
            command,
            cwd=cwd,
            env=env,
            encoding=encoding,
            shell=shell,
            merge_stderr=merge_stderr,
        )

        self.result = ProcessResult()

        self.__capture_output = capture_output
        self.__max_output_lines = max_output_lines

        self._stdout_reader: ProcessOutputReader | None = None
        self._stderr_reader: ProcessOutputReader | None = None

        self._stop_event = Event()

        self._lock = Lock()

        self._stdout_lines: list[str] = []
        self._stderr_lines: list[str] = []

        self.__uid = uuid4()

    @property
    def uid(self) -> UUID:
        return self.__uid

    def __hash__(self) -> int:
        return hash(self.__uid)

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, ManagedProcess):
            return False

        return self.__hash__() == other.__hash__()

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.title})[{self.__uid}]"

    def __repr__(self) -> str:
        return f"'{self.__str__()}'"

    # ================================================================
    def run(self) -> ProcessResult:
        with self._lock:
            if self.result.state is ProcessState.CANCELED:
                logger.debug("[{}] Is canceled, skip execution", self.title)
                return self.result

            if self.result.state is not ProcessState.CREATED:
                msg = "[{}] Process already executed", self.title
                logger.debug(*msg)
                raise RuntimeError(msg[0].format(*msg[1:]))

            self.result.state = ProcessState.STARTING

        self.__execute()

        if self.callbacks.on_finished:
            self.callbacks.on_finished(self.result)

        return self.result

    def __execute(self) -> None:
        with self._lock:
            self.result.state = ProcessState.RUNNING

        try:
            logger.log(
                self.log_level,
                "[{}] Starting: {}",
                self.title,
                " ".join(map(str, self.command)),
            )

            self.runner.start()

            self.result.statistics.started_at = datetime.now()

            if self.callbacks.on_started:
                self.callbacks.on_started()

            self._start_readers()

            start_time = time.monotonic()

            while self.runner.is_running:
                if self._stop_event.is_set():
                    logger.warning(
                        "[{}] Stopping...",
                        self.title,
                    )
                    break

                if self.timeout is not None and time.monotonic() - start_time > self.timeout:
                    logger.warning(
                        "[{}] Timeout exceeded, stopping...",
                        self.title,
                    )
                    self.result.state = ProcessState.TIMEOUT
                    break

                self._stop_event.wait(0.05)

            self._finish()

        except Exception as e:
            logger.exception(
                "[{}] Failed: {}",
                self.title,
                e,
            )

            self.result.state = ProcessState.FAILED

            self.stop()

        finally:
            self._wait_readers()

            self._collect_exit_code()

            self.runner.dispose()

    # ================================================================
    def write_stdin(self, data: str, flush: bool = False) -> None:
        if not self.runner.stdin:
            msg = "[{}] STDIN not available", self
            logger.error(*msg)
            raise RuntimeError(msg[0].format(*msg[1:]))

        self.runner.stdin.write(data)

        if flush:
            self.runner.stdin.flush()

    # ================================================================
    def stop(
        self,
        force: bool = False,
        timeout: int | float = 2,
    ) -> None:
        with self._lock:
            if self._stop_event.is_set():
                return

            self._stop_event.set()

            if self.result.state is ProcessState.RUNNING:
                self.result.state = ProcessState.KILLED

            if force:
                self.runner.stop(timeout)
                self._stop_readers()

    # ================================================================
    def cancel(self) -> None:
        if self.result.state is ProcessState.CANCELED:
            return

        if self.result.state is ProcessState.CREATED:
            logger.debug("[{}] Canceled", self.title)
            self.result.state = ProcessState.CANCELED
            return

        logger.debug("[{}] Can`t cancel running or exited process. Use stop() inteed", self.title)

    # ================================================================
    def _start_readers(self) -> None:
        self._stdout_reader = ProcessOutputReader(
            self.runner.stdout,
            StreamType.STDOUT,
            self._process_line,
        )

        self._stdout_reader.start()

        if self.runner.stderr:
            self._stderr_reader = ProcessOutputReader(
                self.runner.stderr,
                StreamType.STDERR,
                self._process_line,
            )

            self._stderr_reader.start()

    # ================================================================
    def _wait_readers(self, timeout: int | float = 5) -> None:
        start = time.monotonic()

        for reader in (
            self._stderr_reader,
            self._stdout_reader,
        ):
            if reader is None or reader.finished or reader.stopped:
                continue

            if not reader.is_alive():
                return

            while not reader.finished or not reader.stopped:
                if time.monotonic() - start > timeout:
                    break

                time.sleep(0.05)

    # ================================================================
    def _stop_readers(self) -> None:
        for reader in (
            self._stdout_reader,
            self._stderr_reader,
        ):
            if reader is None or reader.finished or reader.stopped:
                continue

            reader.stop()

            if not reader.is_alive():
                return

            with suppress(Exception):
                reader.join(1)

    # ================================================================
    def _process_line(
        self,
        line: ProcessLine,
    ) -> None:
        is_error = is_error_line(
            line.text,
            self.error_flags,
        )

        emit_log(
            self.title,
            line.text,
            is_error=is_error,
            log_level=self.log_level,
        )

        if is_error:
            self.result.error_lines.append(line.text)

        if self.__capture_output:
            if line.stream is StreamType.STDOUT:
                self._stdout_lines.append(line.text)

                if len(self._stdout_lines) > self.__max_output_lines:
                    self._stdout_lines.pop(0)
            else:
                self._stderr_lines.append(line.text)

                if len(self._stderr_lines) > self.__max_output_lines:
                    self._stderr_lines.pop(0)

        if line.stream is StreamType.STDOUT:
            self.result.statistics.stdout_lines += 1

            if self.callbacks.on_stdout:
                self.callbacks.on_stdout(line)

        else:
            self.result.statistics.stderr_lines += 1

            if self.callbacks.on_stderr:
                self.callbacks.on_stderr(line)

        if is_error:
            self.result.statistics.error_lines += 1

            if self.callbacks.on_error_line:
                self.callbacks.on_error_line(line)

    # ================================================================
    def _finish(self) -> None:
        if self.result.state in {
            ProcessState.TIMEOUT,
            ProcessState.KILLED,
        }:
            return

        self.result.state = ProcessState.FINISHED

    # ================================================================
    def _collect_exit_code(self) -> None:
        self.result.exit_code = self.runner.return_code

        self.result.statistics.finished_at = datetime.now()

        if self.__capture_output:
            self.result.stdout = self._stdout_lines
            self.result.stderr = self._stderr_lines
