from __future__ import annotations

from threading import Event, Thread, get_native_id
from typing import IO, Callable

from loguru import logger

from processes.models import ProcessLine, StreamType
from processes.utils import normalize_line


class ProcessOutputReader(Thread):
    def __init__(
        self,
        stream: IO[str],
        stream_type: StreamType,
        callback: Callable[[ProcessLine], None],
        *,
        daemon: bool = True,
    ) -> None:
        super().__init__(daemon=daemon, name=f"stream_reader[{stream_type}]")

        self.id: int | None = None

        self._stream = stream
        self._stream_type = stream_type
        self._callback = callback

        self._stop_event = Event()
        self._finished_event = Event()

    # ------------------------------------------------------------------
    @property
    def finished(self) -> bool:
        return self._finished_event.is_set()

    # ------------------------------------------------------------------
    @property
    def stopped(self) -> bool:
        return self._stop_event.is_set()

    # ------------------------------------------------------------------
    def stop(self) -> None:
        self._stop_event.set()

        logger.debug(
            "[{}:{}] Stream stopping",
            self._stream_type,
            self.id,
        )

    # ------------------------------------------------------------------
    def run(self) -> None:
        self.id = get_native_id()

        logger.debug(
            "[{}:{}] Stream started",
            self._stream_type,
            self.id,
        )

        try:
            for line in self._stream:
                if self._stop_event.is_set():
                    break

                self._callback(
                    ProcessLine(
                        text=normalize_line(line),
                        stream=self._stream_type,
                    )
                )

        except Exception as e:
            logger.warning(
                "[{}:{}] Stream reading exception: {}",
                self._stream_type,
                self.id,
                str(e),
                exc_info=e,
            )

        finally:
            self._finished_event.set()

            logger.debug(
                "[{}:{}] Stream finished",
                self._stream_type,
                self.id,
            )
