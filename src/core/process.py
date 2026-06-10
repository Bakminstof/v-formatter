from datetime import datetime, timedelta
from pathlib import Path
from subprocess import CREATE_NO_WINDOW, PIPE, STDOUT, Popen
from sys import platform
from threading import Lock
from typing import Iterable, Mapping

from loguru import logger
from pydantic import BaseModel

DEFAULT_ERROR_FLAGS = frozenset(("error", "fail", "crash", "exception"))


class ProcessResultModel(BaseModel):
    exit_code: int
    stdout: list[str] = []
    error_lines: list[str] = []


def is_error_line(line: str, error_flags: Iterable[str]) -> bool:
    lower = line.lower()
    return any(flag in lower for flag in error_flags)


def emit_log(title: str, line: str, *, is_error: bool, output_log_level: str = "INFO") -> None:
    prefix = f"[{title}] {line}"
    if is_error:
        logger.error("{}", prefix)
    else:
        logger.log(output_log_level, "{}", prefix)


class ManagedProcess:
    def __init__(
        self,
        title: str,
        command: list[str | Path],
        *,
        encoding: str = "utf-8",
        timeout: int | None = None,
        cwd: str | Path | None = None,
        env: Mapping[str, str] | None = None,
        error_flags: Iterable[str] = DEFAULT_ERROR_FLAGS,
        shell: bool = False,
        capture_output: bool = False,
        output_log_level: str = "INFO",
        max_stdout_lines: int = 1000,
    ) -> None:
        self.title = title
        self.command = command
        self.timeout = timeout
        self.cwd = cwd
        self.env = env
        self.encoding = encoding
        self.error_flags = error_flags
        self.shell = shell
        self.capture_output = capture_output
        self.output_log_level = output_log_level
        self.max_stdout_lines = max_stdout_lines

        self._lock = Lock()
        self._process: Popen | None = None
        self._killed = False

    def run(self) -> ProcessResultModel:
        logger.log(
            self.output_log_level,
            "[{}] Command: {}",
            self.title,
            " ".join(str(i) for i in self.command),
        )

        self._process = Popen(
            self.command,
            stdout=PIPE,
            stderr=STDOUT,
            cwd=self.cwd,
            env=self.env,
            text=True,
            encoding=self.encoding,
            errors="replace",
            shell=self.shell,
            bufsize=-1,
            creationflags=CREATE_NO_WINDOW if platform == "win32" else 0,
        )

        stdout: list[str] = []
        error_lines: list[str] = []

        deadline = datetime.now() + timedelta(seconds=self.timeout or 0)
        has_timeout = self.timeout is not None

        while True:
            if has_timeout and datetime.now() > deadline:
                logger.error("[{}] Timeout exceeded", self.title)
                self._kill()
                break

            if self._process.poll() is not None:
                self._read_remaining(self._process, stdout, error_lines)
                break

            try:
                line = self._process.stdout.readline()
            except Exception as e:
                logger.error("[{}] Readline error: {}", self.title, str(e))
                break

            if not line:
                continue

            line = line.strip()
            self._process_line(line, stdout, error_lines)

        self._process.wait(10)

        return ProcessResultModel(
            exit_code=self._process.returncode if self._process else -1,
            stdout=stdout,
            error_lines=error_lines,
        )

    def _process_line(self, line: str, stdout: list[str], error_lines: list[str]) -> None:
        if self.capture_output:
            if len(stdout) >= self.max_stdout_lines:
                stdout.pop(0)

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

    def _read_remaining(
        self,
        process: Popen,
        stdout: list[str],
        error_lines: list[str],
    ) -> None:
        if not process.stdout:
            return

        try:
            while True:
                line = process.stdout.readline()
                if not line:
                    break
                line = line.strip()

                self._process_line(line, stdout, error_lines)

        except ValueError:
            pass
        except Exception as e:
            logger.error("[{}] Error reading remaining output: {}", self.title, e)
        finally:
            process.stdout.close()

    def _kill(self) -> None:
        with self._lock:
            if not self._process:
                return

            self._process.kill()

            logger.warning("[{}] Killed", self.title)

    def kill(self) -> None:
        if self._killed:
            return

        self._killed = True
        self._kill()
