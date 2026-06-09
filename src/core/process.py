from datetime import datetime, timedelta
from pathlib import Path
from subprocess import CREATE_NO_WINDOW, PIPE, STDOUT, Popen
from sys import platform
from threading import Lock
from typing import Iterable

from loguru import logger
from pydantic import BaseModel

DEFAULT_ERROR_FLAGS = ["error", "fail", "crash", "exception"]


class ProcessResultModel(BaseModel):
    exit_code: int
    stdout: list[str] = []
    error_lines: list[str] = []


def is_error_line(
    line: str,
    error_flags: Iterable[str] | None = None,
) -> bool:
    flags = error_flags or DEFAULT_ERROR_FLAGS
    lower = line.lower()
    return any(flag in lower for flag in flags)


def emit_log(
    title: str,
    line: str,
    *,
    is_error: bool,
    output_log_level: str = "INFO",
) -> None:
    prefix = f"[{title}] {line}"

    if is_error:
        logger.error("{}", prefix)
    else:
        logger.log(output_log_level, "{}", prefix)


def consume_remaining_output(
    title: str,
    process: Popen,
    result: ProcessResultModel,
    *,
    capture_output: bool = False,
    error_flags: Iterable[str] | None = None,
    output_log_level: str = "INFO",
) -> None:
    if not process.stdout:
        return

    for raw in process.stdout.readlines():  # type: str
        line = raw.strip()
        if not line:
            continue

        is_error = is_error_line(line, error_flags)
        emit_log(title, line, is_error=is_error, output_log_level=output_log_level)

        if is_error:
            result.error_lines.append(line)

        if capture_output:
            result.stdout.append(line)


class ManagedProcess:
    def __init__(
        self,
        title: str,
        command: list[str | Path],
        *,
        timeout: int | None = None,
        cwd: str | Path | None = None,
        error_flags: Iterable[str] | None = None,
        shell: bool = False,
        capture_output: bool = False,
        output_log_level: str = "INFO",
    ) -> None:
        self.title = title
        self.command = command
        self.timeout = timeout
        self.cwd = cwd
        self.error_flags = error_flags
        self.shell = shell
        self.capture_output = capture_output
        self.output_log_level = output_log_level

        self._lock = Lock()
        self._process: Popen | None = None
        self._killed = False

    def run(self) -> ProcessResultModel:
        logger.log(
            self.output_log_level,
            "[{}] Command: {}",
            self.title,
            " ".join([str(i) for i in self.command]),
        )

        self._process = Popen(
            self.command,
            stdout=PIPE,
            stderr=STDOUT,
            cwd=self.cwd,
            text=True,
            shell=self.shell,
            bufsize=1,
            creationflags=CREATE_NO_WINDOW if platform == "win32" else 0,
        )

        stdout: list[str] = []
        error_lines: list[str] = []

        deadline = datetime.now() + timedelta(seconds=self.timeout or 0)
        has_timeout = self.timeout is not None

        while self._process.poll() is None:
            if has_timeout and datetime.now() > deadline:
                logger.error("[{}] Timeout exceeded", self.title)
                self.kill()
                break

            if self._killed:
                self.kill()
                break

            raw = self._process.stdout.readline() if self._process.stdout else ""
            line = raw.strip()

            if not line:
                continue

            if self.capture_output:
                stdout.append(line)

            is_error = is_error_line(line, self.error_flags)
            emit_log(
                self.title,
                line,
                is_error=is_error,
                output_log_level=self.output_log_level,
            )

            if is_error:
                error_lines.append(line)

        result = ProcessResultModel(
            exit_code=self._process.returncode if self._process else -1,
            stdout=stdout,
            error_lines=error_lines,
        )

        consume_remaining_output(
            self.title,
            self._process,
            result,
            error_flags=self.error_flags,
            capture_output=self.capture_output,
            output_log_level=self.output_log_level,
        )
        return result

    def kill(self) -> None:
        with self._lock:
            self._killed = True

            if self._process and self._process.poll() is None:
                self._process.kill()

                logger.warning("[{}] Killed", self.title)
