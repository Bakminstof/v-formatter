import time
from pathlib import Path
from typing import Iterator

import humanize
from loguru import logger
from PySide6.QtWidgets import QHBoxLayout, QPushButton

from core.concatenator import VideoConcatenator
from core.context import AppContext
from core.database import VideoRegistry
from core.meta import VideoMetaProcessor
from threads.workers.directory_worker import DirectoryWorker
from ui.models import ConcatStatus
from ui.widgets.elapsed_time_widget import ElapsedTimeManger
from ui.widgets.progress_bar_widget import ProgressBarManager
from ui.widgets.queue_list_widget import QueueListManager
from ui.widgets.time_interval_widget import TimeIntervalManager


class ConcatManager:
    __concat_started: bool = False

    def __init__(
        self,
        start_btn_label: str,
        stop_btn_label: str,
        context: AppContext,
        video_concatenator: VideoConcatenator,
        meta_processor: VideoMetaProcessor,
        video_registry: VideoRegistry,
        elapsed_time_manger: ElapsedTimeManger,
        progress_bar_manager: ProgressBarManager,
        queue_manager: QueueListManager,
        time_interval_filter_manager: TimeIntervalManager,
    ) -> None:
        # UI
        self.start_btn = QPushButton(start_btn_label)
        self.stop_btn = QPushButton(stop_btn_label)

        self.start_btn.clicked.connect(self.start)
        self.stop_btn.clicked.connect(self.stop)

        # Logic
        self.context = context

        self.video_concatenator = video_concatenator
        self.meta_processor = meta_processor
        self.video_registry = video_registry

        self.elapsed_time_manger = elapsed_time_manger
        self.progress_bar_manager = progress_bar_manager
        self.queue_manager = queue_manager
        self.time_interval_filter_manager = time_interval_filter_manager

        self.__total_tasks: int = 0
        self.__current_task_index: int = 0
        self.__current_task_iter: Iterator[Path] | None = None
        self.__start_time: float | int = 0.0

        self.__filters: dict[str, dict] = {}

        self.worker: DirectoryWorker | None = None

    def layout(self) -> QHBoxLayout:
        buttons_row = QHBoxLayout()
        buttons_row.addWidget(self.start_btn)
        buttons_row.addWidget(self.stop_btn)
        return buttons_row

    def start(self) -> None:
        if self.__concat_started:
            logger.warning("Concat is already started")
            return

        self.__concat_started = True

        if (
            self.context.metadata.input_dir is None
            or self.context.metadata.output_dir is None
            or not self.context.metadata.input_dir.exists()
            or not self.context.metadata.output_dir.exists()
        ):
            logger.error(
                "[{}] Input or output dir are invalid: input_dir={!r}, output_dir={!r}",
                self,
                str(self.context.metadata.input_dir),
                str(self.context.metadata.output_dir),
            )
            self.__concat_started = False
            return

        self.context.concat_structure = self.video_concatenator.collect_data_dirs(
            self.context.metadata.input_dir,
            self.context.metadata.output_dir,
            self.context.metadata.video_format,
        )

        self.queue_manager.widget.clear()
        self.progress_bar_manager.widget.setValue(0)

        for inp_path in self.context.concat_structure.data.keys():
            self.add_directory_status(inp_path.name, ConcatStatus.waiting)

        self.__total_tasks = len(self.context.concat_structure.data)
        self.__current_task_index = 0
        self.__current_task_iter = iter(self.context.concat_structure.data.keys())

        self.__start_time = time.monotonic()
        self.elapsed_time_manger.widget.reset()
        self.elapsed_time_manger.widget.start()

        logger.info("Directories found: {}", self.__total_tasks)

        time_from = (
            self.context.metadata.filters.time.time_from
            if self.time_interval_filter_manager.widget.is_enabled()
            else None
        )
        time_to = (
            self.context.metadata.filters.time.time_to
            if self.time_interval_filter_manager.widget.is_enabled()
            else None
        )

        self.__filters["time"] = {
            "time_from": time_from,
            "time_to": time_to,
        }

        self._process_next()

    def stop(self) -> None:
        if self.worker is not None:
            self.worker.stop(kill=True)

        self.elapsed_time_manger.widget.stop()
        self.__concat_started = False

    def _update_progress(self) -> None:
        percent = int(
            (self.__current_task_index / self.__total_tasks) * 100 if self.__total_tasks else 0
        )
        self.progress_bar_manager.widget.setValue(percent)

    def _on_task_finished(self, status: ConcatStatus) -> None:
        self.update_directory_status(self.__current_task_index, status)

        self.__current_task_index += 1
        self._update_progress()

        self._process_next()

    def _process_next(self) -> None:
        if self.worker is not None:
            self.worker.stop()

        self.worker = None

        if self.__current_task_index >= self.__total_tasks:
            self.elapsed_time_manger.widget.stop()

            elapsed = time.monotonic() - self.__start_time
            logger.success("Processing completed for {}", humanize.precisedelta(elapsed))
            self.progress_bar_manager.widget.setValue(100)

            self.__concat_started = False

            return

        index = self.__current_task_index
        inp_path = next(self.__current_task_iter)

        self.update_directory_status(index, ConcatStatus.processing)

        worker = DirectoryWorker(
            inp_path,
            self.context.concat_structure,
            video_concatenator=self.video_concatenator,
            meta_processor=self.meta_processor,
            registry=self.video_registry,
            start_at=self.__filters["time"]["time_from"],
            end_at=self.__filters["time"]["time_to"],
        )
        worker.finished.connect(self._on_task_finished)
        worker.start()

        self.worker = worker

    def add_directory_status(
        self,
        directory: str,
        status: str = ConcatStatus.waiting,
    ) -> None:
        self.queue_manager.widget.addItem(f"{status} {directory}")

    def update_directory_status(self, index: int, status: ConcatStatus) -> None:
        item = self.queue_manager.widget.item(index)

        if not item:
            return

        directory_name = item.text().split(" ", 1)[1]
        item.setText(f"{status} {directory_name}")
