from datetime import datetime
from pathlib import Path

from pydantic import BaseModel


class ArgsModel(BaseModel):
    verbose: bool = False


class AppInfoModel(BaseModel):
    name: str


class VideoMetaModel(BaseModel):
    file_path: Path
    mtime: float
    size: int
    start_datetime: datetime
    end_datetime: datetime
    duration: float
    error: str | None = None
    processed_at: datetime = datetime.now()


UNKNOWN_VERSION = "unknown"


class VersionsInfoModel(BaseModel):
    current: str
    latest: str = "unknown"
    all: list[str]
