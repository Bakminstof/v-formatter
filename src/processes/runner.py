from __future__ import annotations

from sys import platform

if platform == "win32":
    from signal import CTRL_C_EVENT
elif platform == "linux":
    from signal import SIGHUP

from contextlib import suppress
from pathlib import Path
from subprocess import (
    CREATE_NEW_PROCESS_GROUP,
    CREATE_NO_WINDOW,
    PIPE,
    STDOUT,
    Popen,
    TimeoutExpired,
)
from threading import RLock
from time import sleep
from typing import IO, Mapping, Self

from loguru import logger


class ProcessRunner:
    def __init__(
        self,
        command: list[str | Path],
        *,
        cwd: str | Path | None = None,
        env: Mapping[str, str] | None = None,
        encoding: str = "utf-8",
        shell: bool = False,
        merge_stderr: bool = False,
    ) -> None:
        self._command = command
        self._cwd = cwd
        self._env = env
        self._encoding = encoding
        self._shell = shell
        self._merge_stderr = merge_stderr

        self._process: Popen[str] | None = None

        self._lock = RLock()

    # ------------------------------------------------------------------
    def start(self) -> None:
        creation_flags = (
            (CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP)
            if platform == "win32"
            else 0 | CREATE_NEW_PROCESS_GROUP
        )

        with self._lock:
            if self._process is not None:
                raise RuntimeError("Process already started.")

            self._process = Popen(
                self._command,
                stdin=PIPE,
                stdout=PIPE,
                stderr=STDOUT if self._merge_stderr else PIPE,
                cwd=self._cwd,
                env=self._env,
                shell=self._shell,
                text=True,
                encoding=self._encoding,
                errors="replace",
                bufsize=1,
                universal_newlines=True,
                creationflags=creation_flags,
            )

    # ------------------------------------------------------------------
    @property
    def process(self) -> Popen[str]:
        if self._process is None:
            raise RuntimeError("Process not started.")

        return self._process

    # ------------------------------------------------------------------
    @property
    def stdout(self) -> IO[str]:
        stdout = self.process.stdout

        if stdout is None:
            raise RuntimeError("stdout unavailable.")

        return stdout

    # ------------------------------------------------------------------
    @property
    def stderr(self) -> IO[str] | None:
        return self.process.stderr

    # ------------------------------------------------------------------
    @property
    def stdin(self) -> IO[str] | None:
        return self.process.stdin

    # ------------------------------------------------------------------
    @property
    def pid(self) -> int:
        return self.process.pid

    # ------------------------------------------------------------------
    @property
    def return_code(self) -> int | None:
        if not self._process:
            return None

        return self.process.poll()

    # ------------------------------------------------------------------
    @property
    def is_running(self) -> bool:
        return self.return_code is None

    # ------------------------------------------------------------------
    def poll(self) -> int | None:
        return self.process.poll()

    # ------------------------------------------------------------------
    def wait(
        self,
        timeout: float | int | None = None,
    ) -> int:
        logger.debug("[{}] Wait process end", self.pid)

        return self.process.wait(timeout)

    # ------------------------------------------------------------------
    def terminate(self) -> None:
        logger.debug("[{}] Terminating process", self.pid)

        with suppress(Exception):
            if self.is_running:
                self.process.terminate()

        logger.debug("[{}] Terminated process", self.pid)

    # ------------------------------------------------------------------
    def kill(self) -> None:
        logger.debug("[{}] Killing process", self.pid)

        with suppress(Exception):
            if self.is_running:
                self.process.kill()

        logger.debug("[{}] Killed process", self.pid)

    # ------------------------------------------------------------------
    def stop(
        self,
        timeout: float | int = 10.0,
    ) -> None:
        """
        stop event
              ↓
        wait(timeout)
              ↓
        terminate()
              ↓
        kill()
        """
        if not self._process or not self.is_running:
            return

        pid = self.pid

        logger.debug("[{}] Stopping process", pid)

        if platform == "win32":
            stop_event = CTRL_C_EVENT
        else:
            stop_event = SIGHUP

        self.process.send_signal(stop_event)

        sleep(2)

        if not self.is_running:
            logger.debug("[{}] Stopped process (stop event)", pid)
            return

        self.terminate()
        sleep(2)

        if not self.is_running:
            logger.debug("[{}] Stopped process (terminated)", pid)
            return

        try:
            self.wait(timeout)
            logger.debug("[{}] Stopped process (waited)", pid)

        except TimeoutExpired:
            logger.debug("[{}] Stopping process (timeout:{})", pid, timeout)

            self.kill()

            with suppress(Exception):
                self.wait()

            logger.debug("[{}] Stopped process (killed)", pid)

    # ------------------------------------------------------------------
    def dispose(self) -> None:
        self._process = None

    # ------------------------------------------------------------------
    def __enter__(self) -> Self:
        self.start()
        return self

    # ------------------------------------------------------------------
    def __exit__(self, *_) -> None:
        self.stop()
        self.dispose()
