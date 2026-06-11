from typing import Callable

from PySide6.QtCore import QRunnable, Slot


class Runnable(QRunnable):
    def __init__(self, func: Callable, *args, **kwargs) -> None:
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    @Slot()
    def run(self):
        self.func(*self.args, **self.kwargs)
