from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum, auto
from pathlib import Path
from typing import Callable, Mapping


class StreamType(StrEnum):
    STDOUT = auto()
    STDERR = auto()


class ProcessState(StrEnum):
    CREATED = auto()
    STARTING = auto()
    RUNNING = auto()
    STOPPING = auto()
    CANCELED = auto()
    FINISHED = auto()
    TIMEOUT = auto()
    KILLED = auto()
    FAILED = auto()


@dataclass(slots=True, frozen=True)
class ProcessLine:
    text: str
    stream: StreamType
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass(slots=True)
class ProcessStatistics:
    started_at: datetime | None = None
    finished_at: datetime | None = None

    stdout_lines: int = 0
    stderr_lines: int = 0
    error_lines: int = 0

    @property
    def duration(self) -> float | None:
        if self.started_at is None or self.finished_at is None:
            return None

        return (self.finished_at - self.started_at).total_seconds()


@dataclass(slots=True)
class ProcessResult:
    state: ProcessState = ProcessState.CREATED

    exit_code: int | None = None

    stdout: list[str] = field(default_factory=list)

    stderr: list[str] = field(default_factory=list)

    error_lines: list[str] = field(default_factory=list)

    statistics: ProcessStatistics = field(default_factory=ProcessStatistics)

    @property
    def success(self) -> bool:
        return self.state is ProcessState.FINISHED and self.exit_code == 0

    @property
    def failed(self) -> bool:
        return not self.success


@dataclass(slots=True)
class ProcessCallbacks:
    on_started: Callable[[], None] | None = None
    on_finished: Callable[[ProcessResult], None] | None = None
    on_stdout: Callable[[ProcessLine], None] | None = None
    on_stderr: Callable[[ProcessLine], None] | None = None
    on_error_line: Callable[[ProcessLine], None] | None = None


@dataclass(slots=True)
class ProcessConfig:
    encoding: str = "utf-8"
    timeout: float | int | None = None
    capture_output: bool = False
    max_output_lines: int = 1000
    shell: bool = False
    merge_stderr: bool = False
    cwd: Path | None = None
    env: Mapping[str, str] | None = None
