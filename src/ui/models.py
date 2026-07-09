from __future__ import annotations

from enum import StrEnum


class Lang(StrEnum):
    ru_RU = "ru_RU"


class VideoDirStatus(StrEnum):
    waiting = "⏳"
    processing = "⚙️"
    not_found = "⦿"
    done = "✅"
    error = "❌"
    unknown = "❓"


class VersionStatus(StrEnum):
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
