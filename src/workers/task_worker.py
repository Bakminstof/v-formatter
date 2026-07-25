from threading import Event, Thread
from typing import Callable

from loguru import logger


class TaskWorker(Thread):
    def __init__(
        self,
        callback: Callable[..., None],
        interval_s: int = 0,
        *callback_args,
        **callback_kwargs,
    ) -> None:
        super().__init__()

        self.interval_s = interval_s

        self.callback = callback
        self._callback_name = getattr(callback, "__qualname__", None) or getattr(
            callback, "__name__", str(callback)
        )
        self.callback_args = callback_args
        self.callback_kwargs = callback_kwargs

        self.stop_event = Event()

    def __str__(self) -> str:
        return f"{self.__class__.__name__}[{self._callback_name}](interval_s={self.interval_s})"

    def __repr__(self) -> str:
        return f"'{self.__str__()}'"

    def run(self) -> None:
        logger.debug("[{}] Starting", self)

        while not self.stop_event.wait(self.interval_s):
            self._execute()

        logger.debug("[{}] Finished", self)

    def stop(self) -> None:
        logger.debug("[{}] Stopping", self)

        self.stop_event.set()

    def _execute(self) -> None:
        logger.debug("[{}] Execute", self)

        try:
            self.callback(*self.callback_args, **self.callback_kwargs)

        except Exception as e:
            logger.warning("[{}] Error: {}", self, str(e), exc_info=e)
