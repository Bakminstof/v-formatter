from typing import Callable

from loguru import logger
from PySide6.QtCore import QThread, QTimer, Signal


class TaskWorker(QThread):
    finished_iteration = Signal()
    finished = Signal()
    error_occurred = Signal(str)

    def __init__(
        self,
        callback: Callable[..., None],
        interval_s: int = 0,
        *callback_args,
        **callback_kwargs,
    ) -> None:
        super().__init__()

        self.interval_ms = int(interval_s * 1000)

        self.callback = callback
        self._callback_name = getattr(callback, "__qualname__", None) or getattr(
            callback, "__name__", str(callback)
        )
        self.callback_args = callback_args
        self.callback_kwargs = callback_kwargs

        self._timer = None

    def __str__(self) -> str:
        return f"{self.__class__.__name__}[{self._callback_name}](interval_s={self.interval_ms})"

    def __repr__(self) -> str:
        return f"'{self.__str__()}'"

    def run(self) -> None:
        logger.debug("[{}] Start", self)

        if self.interval_ms <= 0:
            self._execute()
            self.finished.emit()
            return

        self._timer = QTimer(self)
        self._timer.setInterval(self.interval_ms)
        self._timer.timeout.connect(self._execute)
        self._timer.start()

    def stop(self) -> None:
        if self._timer:
            self._timer.stop()
            self._timer = None

            logger.debug("[{}] Stopped", self)

        self.quit()
        self.wait()

    def _execute(self) -> None:
        try:
            self.callback(*self.callback_args, **self.callback_kwargs)
            self.finished_iteration.emit()
            logger.debug("[{}] Execute", self)
        except Exception as e:
            self.error_occurred.emit(str(e))
