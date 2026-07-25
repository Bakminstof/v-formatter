from datetime import datetime, timedelta
from json import loads
from pathlib import Path

from core.database import VideoRegistry
from core.mixins import ReprMixin
from core.models import VideoMetaModel
from processes import ManagedProcess
from workers.process import FFProcess


class VideoMetaProcessor(ReprMixin):
    def __init__(
        self,
        ffprobe: Path,
        registry: VideoRegistry,
        timeout: int = 30,
    ) -> None:
        self.ffprobe = ffprobe
        self.registry = registry

        self.timeout = timeout

    def update(self, meta_model: VideoMetaModel) -> VideoMetaModel:
        self.registry.upsert(meta_model)
        return meta_model

    def need_update(self, item: Path) -> bool:
        meta_model = self.registry.get_by_path(item)

        if not meta_model:
            return True

        stat = item.stat()

        if meta_model.mtime != stat.st_mtime or meta_model.size != stat.st_size:
            return True

        return False

    @staticmethod
    def parse_video_info(video_path: Path, output: list[str]) -> VideoMetaModel:
        data = loads(" ".join(output))

        video_path_stat = video_path.stat()

        tags = data["format"]["tags"]
        duration = float(data["format"]["duration"])
        start_datetime = datetime.fromisoformat(tags["creation_time"].replace("Z", "+00:00"))

        return VideoMetaModel(
            file_path=video_path,
            mtime=video_path_stat.st_mtime,
            size=video_path_stat.st_size,
            start_datetime=start_datetime,
            end_datetime=start_datetime + timedelta(seconds=duration),
            duration=duration,
        )

    def get_video_info(
        self,
        video_path: Path,
        run: bool = True,
    ) -> FFProcess | list[str]:
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

        process = FFProcess(
            f"FFProbe:{video_path.name}",
            args,
            timeout=self.timeout,
            capture_output=True,
            metadata={"processed_dir": video_path.parent},
        )

        if not run:
            return process

        res = process.run()
        return res.stdout
