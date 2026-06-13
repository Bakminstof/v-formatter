from datetime import datetime, timedelta
from json import loads
from pathlib import Path
from typing import Iterable

from core.database import VideoRegistry
from core.models import VideoMetaModel
from core.process import ManagedProcess
from threads.manage import run_in_thread_pool


class VideoMetaProcessor:
    def __init__(
        self,
        ffprobe: Path,
        registry: VideoRegistry,
        timeout: int = 30,
    ) -> None:
        self.ffprobe = ffprobe
        self.registry = registry

        self.timeout = timeout

    def __str__(self) -> str:
        return self.__class__.__name__

    def __repr__(self) -> str:
        return f"'{self}'"

    def _update(self, item: Path) -> VideoMetaModel:
        meta_model = self.load_video_meta(item)
        self.registry.upsert(meta_model)
        return meta_model

    def update_meta(self, item: Path) -> None:
        meta_model = self.registry.get_by_path(item)

        if not meta_model:
            self._update(item)
            return

        stat = item.stat()

        if meta_model.mtime != stat.st_mtime or meta_model.size != stat.st_size:
            self._update(item)

    def update_meta_bulk(self, items: Iterable[Path]) -> None:
        run_in_thread_pool([(self.update_meta, (item,)) for item in items])

    def load_video_meta(self, video_path: Path) -> VideoMetaModel:
        args = [
            self.ffprobe,
            "-v",
            "quiet",
            "-show_entries",
            "format=duration:format_tags=creation_time",
            "-of",
            "json",
            video_path,
        ]

        title = f"FFProbe:{video_path.name}"
        process = ManagedProcess(
            title,
            args,
            timeout=self.timeout,
            capture_output=True,
        )

        res = process.run()
        data = loads(" ".join(res.stdout))

        video_path_stat = video_path.stat()

        tags = data["format"]["tags"]
        duration = float(data["format"]["duration"])
        start_datetime = datetime.fromisoformat(tags["creation_time"])

        return VideoMetaModel(
            file_path=video_path,
            mtime=video_path_stat.st_mtime,
            size=video_path_stat.st_size,
            start_datetime=start_datetime,
            end_datetime=start_datetime + timedelta(seconds=duration),
            duration=duration,
        )
