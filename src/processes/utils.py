from __future__ import annotations

from typing import Iterable

from loguru import logger

DEFAULT_ERROR_FLAGS: frozenset[str] = frozenset(
    {
        "error",
        "errors",
        "failed",
        "failure",
        "fatal",
        "panic",
        "exception",
        "traceback",
        "crash",
    }
)


def normalize_line(line: str) -> str:
    return line.rstrip("\r\n")


def is_error_line(
    line: str,
    error_flags: Iterable[str] = DEFAULT_ERROR_FLAGS,
) -> bool:
    lower = line.casefold()

    return any(flag.casefold() in lower for flag in error_flags)


def emit_log(
    title: str,
    line: str,
    *,
    is_error: bool = False,
    log_level: str = "INFO",
) -> None:
    message = "[{}] {}", title, line

    if is_error:
        logger.error(*message)
    else:
        logger.log(log_level, *message)
