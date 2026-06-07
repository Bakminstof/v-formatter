from pathlib import Path

from core.concatenator import VideoConcatenator, VideosStructureModel
from core.database import VideoRegistry
from core.meta import VideoMetaProcessor
from loguru import logger
from PySide6.QtCore import QThread, Signal

from core.process import ManagedProcess


class Worker(QThread):
    finished = Signal(bool)

    def __init__(
        self,
        input_dir: Path,
        structure: VideosStructureModel,
        target_suffix: str,
        *,
        video_concatenator: VideoConcatenator,
        meta_processor: VideoMetaProcessor,
        registry: VideoRegistry,
        start_at: str | None = None,
        end_at: str | None = None,
    ) -> None:
        super().__init__()

        self.video_concatenator = video_concatenator
        self.meta_processor = meta_processor
        self.registry = registry

        self.input_dir = input_dir
        self.structure = structure
        self.target_suffix = target_suffix

        self._time_interval = (start_at, end_at) if start_at and end_at else None

        self._stop = False

        self._process: ManagedProcess | None = None

    def _get_target_files(self) -> dict[int, Path]:
        if not self._time_interval:
            return self.structure.data[self.input_dir].files

        files: dict[int, Path] = {}

        idx = 1

        for item in self.registry.search_by_time_interval(
            self.input_dir,
            *self._time_interval,
        ):
            files[idx] = item.file_path
            idx += 1

        return files

    def run(self) -> None:
        if self._process is not None:
            msg = "Worker already running"
            logger.critical(msg)
            raise RuntimeError(msg)

        self._process = ManagedProcess("EMPTY", [])

        try:
            self.meta_processor.update_meta_bulk(
                self.structure.data[self.input_dir].files.values()
            )

            target_files = self._get_target_files()

            self.video_concatenator.run(
                self.input_dir,
                target_files,
                self.structure.data[self.input_dir].destination,
                self.target_suffix,
                process=self._process,
            )

            if not self._stop:
                self.finished.emit(True)

            self._process = None

        except Exception as e:
            logger.error("[{}] Exception: {}", self.input_dir.name, str(e))
            self.finished.emit(False)

    def stop(self) -> None:
        self._stop = True

        if self._process is not None:
            self._process.kill()

        self._process = None
