from enum import StrEnum, auto
from pathlib import Path
from typing import Protocol

from loguru import logger
from PySide6.QtCore import QCoreApplication, QObject

from core.concatenator import VideoConcatenator
from core.context import AppContext
from core.database import VideoRegistry
from core.meta import VideoMetaProcessor
from core.mixins import ReprMixin
from processes import ManagedProcessProtocol
from threads.executor import (
    ProcessFinishedEvent,
    ProcessPoolExecutorThread,
    ProcessQueueExecutorThread,
)
from ui.models import VideoDirStatus
from workers.process import FFProcess


class VideoProcessingAction(StrEnum):
    concat = auto()
    scan = auto()


class VideoProcessingWorkerProtocol[E](Protocol):
    @property
    def executor(self) -> E: ...

    @property
    def running(self) -> bool: ...

    def start(self, target_dir: Path) -> None | VideoDirStatus: ...
    def stop(self) -> None: ...


class ScanWorker(VideoProcessingWorkerProtocol[ProcessPoolExecutorThread], ReprMixin):
    def __init__(
        self,
        context: AppContext,
        gui_receiver: QObject,
        *,
        meta_processor: VideoMetaProcessor,
    ) -> None:
        self.__context = context
        self.__gui_receiver = gui_receiver

        self.__meta_processor = meta_processor
        self.__indexed_structure: dict[Path, dict[Path, bool]] = {}

    @property
    def executor(self) -> ProcessPoolExecutorThread:
        executor = self.__context.processes.pool_executor

        if executor is None:
            msg = ("[{}] Executor({}) is None", self, ProcessPoolExecutorThread)
            logger.error(*msg)
            raise RuntimeError(msg[0].format(*msg[1:]))

        return executor

    @property
    def running(self) -> bool:
        return self.executor.running

    def stop(self) -> None:
        if not self.running:
            return

        self.executor.stop_all_processes()

    def start(self, target_dir: Path) -> None | VideoDirStatus:
        self.__indexed_structure.clear()

        if not self.__context.concat_structure.data[target_dir].process_it:
            return VideoDirStatus.empty

        self.__kiq_scan(target_dir)
        return None

    def __on_item_scan_finished(self, process: ManagedProcessProtocol) -> None:
        item: Path = process.metadata["item"]
        item_dir: Path = item.parent

        result = process.result

        if not result.stdout:
            is_success = False
        else:
            try:
                model = self.__meta_processor.parse_video_info(item, result.stdout)
                self.__meta_processor.update(model)
                is_success = True
            except Exception as e:
                logger.exception("[{}] Error: {}", self, str(e))
                is_success = False

        logger.debug("[{}] Item scan finished, result: success={}", process, is_success)

        self.__indexed_structure.setdefault(item_dir, {})[item] = is_success
        self.__check_scan_progress(item_dir)

    def __check_scan_progress(self, target_dir: Path) -> None:
        if len(self.__context.concat_structure.data[target_dir].files) == len(
            self.__indexed_structure[target_dir]
        ):
            is_all_success = all(self.__indexed_structure[target_dir].values())
            meta = {
                "processed_dir": target_dir,
                "is_success": is_all_success,
                "action": VideoProcessingAction.scan,
            }

            event = ProcessFinishedEvent(None, None, meta)
            QCoreApplication.postEvent(self.__gui_receiver, event)

    def __kiq_scan(self, target_dir: Path) -> None:
        for file in self.__context.concat_structure.data[target_dir].files.values():
            if not self.__meta_processor.need_update(file):
                self.__indexed_structure.setdefault(target_dir, {})[file] = True
                self.__check_scan_progress(target_dir)
                continue

            p = self.__meta_processor.get_video_info(file, run=False)
            p: FFProcess

            p.metadata["action"] = VideoProcessingAction.scan
            p.metadata["item"] = file

            self.executor.put(
                p,
                self.__on_item_scan_finished,
            )


class ConcatWorker(VideoProcessingWorkerProtocol[ProcessQueueExecutorThread], ReprMixin):
    def __init__(
        self,
        context: AppContext,
        gui_receiver: QObject,
        *,
        video_concatenator: VideoConcatenator,
        video_registry: VideoRegistry,
    ) -> None:
        self.__context = context
        self.__gui_receiver = gui_receiver

        self.__video_concatenator = video_concatenator
        self.__video_registry = video_registry

    @property
    def executor(self) -> ProcessQueueExecutorThread:
        executor = self.__context.processes.sequential_executor

        if executor is None:
            msg = ("[{}] Executor({}) is None", self, ProcessQueueExecutorThread)
            logger.error(*msg)
            raise RuntimeError(msg[0].format(*msg[1:]))

        return executor

    @property
    def running(self) -> bool:
        return self.executor.running

    def stop(self) -> None:
        if not self.running:
            return

        self.executor.stop_current_process()

    def start(
        self,
        target_dir: Path,
    ) -> VideoDirStatus | None:
        start_at = self.__context.metadata.filters.time.time_from
        end_at = self.__context.metadata.filters.time.time_to

        time_interval = (start_at, end_at) if start_at and end_at else None

        if not self.__context.concat_structure.data[target_dir].process_it:
            return VideoDirStatus.empty

        return self.__kiq_concat(target_dir, time_interval)

    def _get_target_files(
        self,
        target_dir: Path,
        time_interval: tuple[str, str] | None = None,
    ) -> dict[int, Path]:
        if not self.__context.concat_structure.data[target_dir].process_it:
            return {}

        if not time_interval:
            return self.__context.concat_structure.data[target_dir].files

        files: dict[int, Path] = {}

        idx = 1

        for item in self.__video_registry.search_by_time_interval(
            target_dir,
            *time_interval,
        ):
            files[idx] = item.file_path
            idx += 1

        return files

    def __kiq_concat(
        self,
        target_dir: Path,
        time_interval: tuple[str, str] | None = None,
    ) -> VideoDirStatus | None:
        target_files = self._get_target_files(target_dir, time_interval)

        if not target_files:
            return VideoDirStatus.empty

        p = self.__video_concatenator.prepare_run(
            target_dir,
            target_files,
            self.__context.concat_structure.data[target_dir].destination,
        )

        if p is None:
            return VideoDirStatus.empty

        p.metadata["action"] = VideoProcessingAction.concat

        self.executor.put(p)

        return None
