import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Iterator

import humanize
from loguru import logger
from PySide6.QtWidgets import QHBoxLayout, QPushButton

from core.concatenator import VideoConcatenator
from core.context import AppContext
from core.meta import VideoMetaProcessor
from threads.manage import DEFAULT_MAX_WORKERS
from threads.workers.directory_worker import DirectoryWorker
from ui.models import VideoDirStatus
from ui.widgets.elapsed_time_widget import ElapsedTimeManger
from ui.widgets.progress_bar_widget import ProgressBarManager
from ui.widgets.queue_list_widget import QueueListManager


class ScanManager:
    __started: bool = False

    def __init__(
        self,
        start_btn_label: str,
        stop_btn_label: str,
        context: AppContext,
        meta_processor: VideoMetaProcessor,
        video_concatenator: VideoConcatenator,
        elapsed_time_manger: ElapsedTimeManger,
        progress_bar_manager: ProgressBarManager,
        queue_manager: QueueListManager,
        max_workers: int = DEFAULT_MAX_WORKERS,
    ) -> None:
        # UI
        self.start_btn = QPushButton(start_btn_label)
        self.stop_btn = QPushButton(stop_btn_label)
        self.stop_btn.setVisible(False)

        self.start_btn.clicked.connect(self.start)
        self.stop_btn.clicked.connect(self.stop)

        # Logic
        self.context = context
        self.meta_processor = meta_processor
        self.video_concatenator = video_concatenator
        self.elapsed_time_manger = elapsed_time_manger
        self.progress_bar_manager = progress_bar_manager
        self.queue_manager = queue_manager

        self.context.main_buttons.update({self.start_btn, self.stop_btn})

        self.__total_tasks: int = 0
        self.__current_task_index: int = 0
        self.__current_task_iter: Iterator[Path] | None = None
        self.__start_time: float | int = 0.0

        self.__thread_pool: ThreadPoolExecutor | None = None
        self.__thread_pool_max_workers: int = max_workers
        self.__worker: DirectoryWorker | None = None

    def start(self) -> None:
        self.__started = True
        self.__switch_btn()

        logger.info("Starting scan")

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
            self.__started = False
            self.__switch_btn()
            return

        self.queue_manager.widget.clear()
        self.progress_bar_manager.widget.setValue(0)

        self.context.concat_structure = self.video_concatenator.collect_data_dirs(
            self.context.metadata.input_dir,
            self.context.metadata.output_dir,
            self.context.metadata.video_format,
        )

        for inp_path in self.context.concat_structure.data.keys():
            self.add_directory_status(inp_path.name, VideoDirStatus.waiting)

        self.__total_tasks = len(self.context.concat_structure.data)
        self.__current_task_index = 0
        self.__current_task_iter = iter(self.context.concat_structure.data.keys())

        self.__start_time = time.monotonic()
        self.elapsed_time_manger.widget.reset()
        self.elapsed_time_manger.widget.start()

        self.__thread_pool = ThreadPoolExecutor(max_workers=self.__thread_pool_max_workers)

        self._process_next()

    def _process_next(self) -> None:
        if self.__worker is not None:
            self.__worker.stop()

        self.__worker = None

        if self.__current_task_index >= self.__total_tasks:
            self.elapsed_time_manger.widget.stop()

            elapsed = time.monotonic() - self.__start_time
            logger.success("Processing completed for {}", humanize.precisedelta(elapsed))
            self.progress_bar_manager.widget.setValue(100)

            self.__started = False
            self.__switch_btn()

            if self.__thread_pool:
                self.__thread_pool.shutdown(wait=True)
                self.__thread_pool = None

            return

        index = self.__current_task_index
        inp_path = next(self.__current_task_iter)

        self.update_directory_status(index, VideoDirStatus.processing)

        logger.info("Scanning: {}", inp_path.absolute().as_posix())

        worker = DirectoryWorker(
            "scan",
            inp_path,
            self.context.concat_structure,
            video_concatenator=self.video_concatenator,
            meta_processor=self.meta_processor,
            thread_pool=self.__thread_pool,
        )
        worker.finished.connect(self._on_task_finished)
        worker.start()

        self.__worker = worker

    def stop(self) -> None:
        self.__started = False
        self.__switch_btn()

        if self.__thread_pool:
            self.__thread_pool.shutdown(wait=True)
            self.__thread_pool = None

        logger.info("Stopping scan")

    def _update_progress(self) -> None:
        percent = int(
            (self.__current_task_index / self.__total_tasks) * 100 if self.__total_tasks else 0
        )
        self.progress_bar_manager.widget.setValue(percent)

    def _on_task_finished(self, status: VideoDirStatus) -> None:
        self.update_directory_status(self.__current_task_index, status)

        self.__current_task_index += 1
        self._update_progress()

        if self.__started:
            self._process_next()

    def add_directory_status(
        self,
        directory: str,
        status: str = VideoDirStatus.waiting,
    ) -> None:
        self.queue_manager.widget.addItem(f"{status} {directory}")

    def update_directory_status(self, index: int, status: VideoDirStatus) -> None:
        item = self.queue_manager.widget.item(index)

        if not item:
            return

        directory_name = item.text().split(" ", 1)[1]
        item.setText(f"{status} {directory_name}")

    def __switch_btn(self) -> None:
        for btn in self.context.main_buttons:
            btn.setEnabled(not self.__started)

        self.start_btn.setVisible(not self.__started)
        self.start_btn.setEnabled(not self.__started)
        self.stop_btn.setVisible(self.__started)
        self.stop_btn.setEnabled(self.__started)

    def layout(self) -> QHBoxLayout:
        buttons_row = QHBoxLayout()
        buttons_row.addWidget(self.start_btn)
        buttons_row.addWidget(self.stop_btn)
        return buttons_row
