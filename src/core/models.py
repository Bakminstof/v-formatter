from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from re import match
from sqlite3 import Row
from typing import Self

from pydantic import BaseModel, ConfigDict, field_validator


class ArgsModel(BaseModel):
    verbose: bool = False


class AppInfoModel(BaseModel):
    name: str
    orign_url: str
    feedback_url: str


class VideoMetaModel(BaseModel):
    file_path: Path
    mtime: float
    size: int
    start_datetime: datetime
    end_datetime: datetime
    duration: float
    error: str | None = None
    processed_at: datetime = datetime.now()

    @classmethod
    def from_row(cls, data: Row) -> Self:
        return cls.model_validate(
            {
                "file_path": data[1],
                "mtime": data[2],
                "size": data[3],
                "start_datetime": data[4],
                "end_datetime": data[5],
                "duration": data[6],
                "error": data[7],
                "processed_at": data[8],
            }
        )


UNKNOWN_VERSION = "unknown"


class VersionsInfoModel(BaseModel):
    current: str = UNKNOWN_VERSION
    latest: str = UNKNOWN_VERSION
    all: list[str] = []


class Emojis(StrEnum):
    dir = "📁"


class TimeFilterModel(BaseModel):
    model_config = ConfigDict(validate_default=True)

    enabled: bool = True

    time_from: str = "00:00"
    time_to: str = "23:59"

    @field_validator("time_from", "time_to", mode="before")
    @classmethod
    def time_validator(cls, v: str) -> str:
        if match(r"^\d{2}:\d{2}$", v):
            return v

        raise ValueError(f"Invalid time value: {v}")


class FiltersModel(BaseModel):
    time: TimeFilterModel = TimeFilterModel()


class MetadataModel(BaseModel):
    input_dir: Path | None = None
    output_dir: Path | None = None
    video_format: str = "mov,mp4,m4a,3gp,3g2,mj2"

    filters: FiltersModel = FiltersModel()


class VideoFormat(BaseModel):
    extension: str
    description: str

    demuxing: bool = False
    muxing: bool = False
    device: bool = False

    def __hash__(self) -> int:
        return hash(self.extension)
