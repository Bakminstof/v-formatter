from __future__ import annotations

from enum import Enum


class Lang(Enum):
    ru_RU = "ru_RU"


class ConcatStatus(Enum):
    waiting = "⏳"
    processing = "⚙️"
    done = "✅"
    error = "❌"
    unknown = "❓"


class VersionStatus(Enum):
    actual = "✅"
    cant_check = "⦿"
    need_update = "⬆️"


LOG_COLORS = {
    "TRACE": "#AAAAAA",
    "DEBUG": "#BBBBBB",
    "INFO": "#FFFFFF",
    "SUCCESS": "#4CAF50",
    "WARNING": "#FFC107",
    "ERROR": "#F44336",
    "CRITICAL": "#E91E63",
    "-DEFAULT-": "#FFFFFF",
}
