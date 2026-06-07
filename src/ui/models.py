from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from re import match

from pydantic import BaseModel, ConfigDict, field_validator


class Lang(StrEnum):
    ru_RU = "ru_RU"


class Status(StrEnum):
    waiting = "⏳"
    processing = "⚙️"
    done = "✅"
    error = "❌"
    unknown = "❓"


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


@dataclass(frozen=True)
class VideoFormat:
    label: str
    extension: str


VIDEO_FORMATS: list[VideoFormat] = [
    VideoFormat("MP4 (H.264)", "mp4"),
    VideoFormat("MKV", "mkv"),
    VideoFormat("AVI", "avi"),
    VideoFormat("3GP", "3gp"),
]


class TimeFilterModel(BaseModel):
    model_config = ConfigDict(validate_default=True)

    time_from: str | None = None
    time_to: str | None = None

    @field_validator("time_from", "time_to", mode="before")
    @classmethod
    def time_validator(cls, v: str | None) -> str:
        if v is None:
            return "00:00"

        if match(r"^\d{2}:\d{2}$", v):
            return v

        raise ValueError(f"Invalid time value: {v}")


class FiltersModel(BaseModel):
    time: TimeFilterModel = TimeFilterModel()


class LocalMetaModel(BaseModel):
    input_dir: Path | None = None
    output_dir: Path | None = None
    video_format: str = "3gp"

    filters: FiltersModel = FiltersModel()
