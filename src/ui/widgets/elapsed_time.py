import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


class ElapsedTimeWidget(QWidget):
    def __init__(self, label: str) -> None:
        super().__init__()

        self._start_time: float | None = None

        self._label = QLabel(label)
        self._time_label = QLabel("00:00")

        self._time_label.setMinimumWidth(60)
        self._time_label.setAlignment(self._time_label.alignment() | self._time_label.alignment())

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._update_time)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self._label)
        layout.addWidget(self._time_label)

        self.setLayout(layout)

    def start(self) -> None:
        self._start_time = time.monotonic()
        self._update_time()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def reset(self) -> None:
        self._start_time = None
        self._time_label.setText("00:00")

    def _update_time(self) -> None:
        if self._start_time is None:
            return

        elapsed = int(time.monotonic() - self._start_time)
        minutes, seconds = divmod(elapsed, 60)
        hours, minutes = divmod(minutes, 60)

        if hours > 0:
            self._time_label.setText(f"{hours:02}:{minutes:02}:{seconds:02}")
        else:
            self._time_label.setText(f"{minutes:02}:{seconds:02}")
