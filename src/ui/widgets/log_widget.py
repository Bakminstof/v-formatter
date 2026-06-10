from loguru import logger
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QTextEdit

from ui.models import LOG_COLORS


class QtLogHandler(QObject):
    log_signal = Signal(str, str)

    def __init__(self, log_level: str) -> None:
        super().__init__()
        logger.add(
            self._emit,
            level=log_level,
            format="{time:HH:mm:ss} | {level} | {message}",
            colorize=False,
        )

    def _emit(self, message) -> None:
        record = message.record
        level = record["level"].name
        text = message.strip()

        self.log_signal.emit(text, level)


class LogWidget(QTextEdit):
    def __init__(self) -> None:
        super().__init__()
        self.setReadOnly(True)
        self.setLineWrapMode(QTextEdit.WidgetWidth)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet(
            """
            background-color: #1e1e1e;
            color: #ffffff;
            border: 1px solid #3c3c3c;
            font-family: Consolas, monospace;
            font-size: 12px;
        """
        )

    def append_log(self, message: str, level: str) -> None:
        color = LOG_COLORS.get(level, LOG_COLORS["INFO"])
        html = f'<span style="color:{color}">{message}</span>'
        self.append(html)
        self.moveCursor(QTextCursor.End)
