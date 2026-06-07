import logging
import sys
from pathlib import Path

from loguru import logger


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame.f_back and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level,
            record.getMessage(),
        )


def setup_logging(
    rotation: str,
    retention: str,
    compression: str,
    file_format: str,
    encoding: str,
    console_format: str,
    verbose: bool = False,
    log_file: str | None = None,
) -> None:
    root_logger = logging.getLogger()
    root_logger.handlers = [InterceptHandler()]

    logger.remove()

    level = "DEBUG" if verbose else "INFO"

    logger.add(
        sys.stdout,
        level=level,
        colorize=True,
        format=console_format,
    )

    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        logger.add(
            log_path.absolute().as_posix(),
            level="DEBUG",
            format=file_format,
            rotation=rotation,
            retention=retention,
            compression=compression,
            encoding=encoding,
            backtrace=True,
            diagnose=True,
        )

        logger.info("Logfile: {}", log_path.absolute().as_posix())
