from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

from loguru import logger
from PySide6.QtCore import QThread, Signal

from core.concatenator import VideoConcatenator, VideosStructureModel
from core.database import VideoRegistry
from core.meta import VideoMetaProcessor
from core.process import ManagedProcess
from ui.models import VideoDirStatus


class DirectoryWorker(QThread):
    finished = Signal(str)

    def __init__(
        self,
        action: Literal["scan", "concat"],
        input_dir: Path,
        structure: VideosStructureModel,
        *,
        video_concatenator: VideoConcatenator,
        meta_processor: VideoMetaProcessor,
        registry: VideoRegistry | None = None,
        thread_pool: ThreadPoolExecutor | None = None,
        start_at: str | None = None,
        end_at: str | None = None,
    ) -> None:
        super().__init__()

        self.__action = action

        self.video_concatenator = video_concatenator
        self.meta_processor = meta_processor
        self.registry = registry
        self.thread_pool = thread_pool

        self.input_dir = input_dir
        self.structure = structure

        self._time_interval = (start_at, end_at) if start_at and end_at else None

        self._stop = False

        self._process: ManagedProcess | None = None

    def _get_target_files(self) -> dict[int, Path]:
        if not self.structure.data[self.input_dir].process_it:
            return {}

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

    def __scan(self) -> bool:
        return self.meta_processor.update_meta_bulk(
            self.structure.data[self.input_dir].files.values(), executor=self.thread_pool
        )

    def __concat(self) -> bool:
        target_files = self._get_target_files()

        if not target_files:
            self.finished.emit(VideoDirStatus.not_found)
            return True

        exit_code, result_file = self.video_concatenator.run(
            self.input_dir,
            target_files,
            self.structure.data[self.input_dir].destination,
            process=self._process,
        )

        return exit_code == 0

    def run(self) -> None:
        if not self.structure.data[self.input_dir].process_it:
            logger.debug(
                "[Dir:{}] Process it: False. Skipping",
                self.input_dir.absolute().as_posix(),
            )
            return

        if self._process is not None:
            msg = "Worker already running"
            logger.critical(msg)
            raise RuntimeError(msg)

        self._process = ManagedProcess("EMPTY", [])

        try:
            if self.__action == "scan":
                is_success = self.__scan()
            elif self.__action == "concat":
                is_success_scan = self.__scan()
                is_success_concat = self.__concat()
                is_success = all((is_success_scan, is_success_concat))
            else:
                msg = (
                    "[Dir:{}] Unknown action: {}",
                    self.input_dir.absolute().as_posix(),
                    self.__action,
                )
                logger.error(*msg)
                raise NotImplementedError(msg[0], *msg[1:])

            if not self._stop and is_success:
                self.finished.emit(VideoDirStatus.done)
            else:
                self.finished.emit(VideoDirStatus.error)

        except Exception as e:
            logger.exception(
                "[Dir:{}] Exception: {}",
                self.input_dir.name,
                str(e),
                exc_info=e,
            )
            self.finished.emit(VideoDirStatus.error)

    def stop(self, kill: bool = False) -> None:
        self._stop = True

        if kill and self._process is not None:
            self._process.kill()

        self._process = None
        self.quit()
