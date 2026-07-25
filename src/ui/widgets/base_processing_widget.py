import time
from pathlib import Path
from threading import Lock
from typing import Iterator

import humanize
from loguru import logger
from PySide6.QtWidgets import QHBoxLayout, QPushButton

from core.context import AppContext
from core.mixins import ReprMixin
from ui.models import VideoDirStatus
from ui.widgets.elapsed_time_widget import ElapsedTimeManger
from ui.widgets.progress_bar_widget import ProgressBarManager
from ui.widgets.queue_list_widget import QueueListManager
from workers.processing_workers import VideoProcessingWorkerProtocol


class BaseWorkerProcessingManager(ReprMixin):
    def __init__(
        self,
        start_btn_label: str,
        stop_btn_label: str,
        context: AppContext,
        *,
        elapsed_time_manger: ElapsedTimeManger,
        progress_bar_manager: ProgressBarManager,
        queue_manager: QueueListManager,
    ) -> None:
        # --- UI buttons ---
        self.start_btn = QPushButton(start_btn_label)
        self.stop_btn = QPushButton(stop_btn_label)
        self.stop_btn.setVisible(False)
        self.start_btn.clicked.connect(self.start)
        self.stop_btn.clicked.connect(self.stop)

        # --- Services ---
        self.context = context
        self.elapsed_time_manger = elapsed_time_manger
        self.progress_bar_manager = progress_bar_manager
        self.queue_manager = queue_manager

        context.main_buttons.update({self.start_btn, self.stop_btn})

        # --- Internal state ---
        self._lock = Lock()
        self._started: bool = False
        self._start_time: float | int = 0.0
        self._total_tasks: int = 0
        self._current_task_index: int = 0
        self._current_task_iter: Iterator[Path] | None = None

    # ---------- Public API ----------
    def start(self) -> None:
        self._started = True

        self.switch_btn()

        input_dir = self.context.metadata.input_dir
        output_dir = self.context.metadata.output_dir

        if not self._validate_directories(
            (input_dir, "Input directory"),
            (output_dir, "Output directory"),
        ):
            self._started = False
            self.switch_btn()
            return

        input_dir: Path
        output_dir: Path

        self.progress_bar_manager.widget.setValue(0)

        self._on_before_start(input_dir, output_dir)

        folders = list(self.context.concat_structure.data.keys())

        if not folders:
            self._started = False
            self.switch_btn()

            logger.warning(
                "[{}] Zero directories chosen or directories not found. You can try {!r}",
                self,
                self.context.i18n.t("scan.start"),
            )

            return

        self._total_tasks = len(folders)
        self._current_task_index = 0
        self._current_task_iter = iter(folders)

        self._start_time = time.monotonic()
        self.elapsed_time_manger.widget.reset()
        self.elapsed_time_manger.widget.start()

        logger.info("Directories found: {}", self._total_tasks)

        self._process_next()

    def stop(self) -> None:
        self.stop_btn.setEnabled(False)

        if not self._started:
            return

        self.worker.stop()

        self.elapsed_time_manger.widget.stop()

        logger.info("Processing stopping")

        self._started = False

    def layout(self) -> QHBoxLayout:
        buttons_row = QHBoxLayout()
        buttons_row.addWidget(self.start_btn)
        buttons_row.addWidget(self.stop_btn)
        return buttons_row

    # Progress & Status
    def add_directory_status(
        self,
        source_path: Path,
        status: str = VideoDirStatus.waiting,
        process_it: bool = True,
    ) -> None:
        self.queue_manager.add_directory_status(source_path, status, process_it)

    def update_directory_status(self, input_path: Path, status: VideoDirStatus) -> None:
        index = self.queue_manager.get_idx_by_source_path(input_path)
        self.queue_manager.update_directory_status(index, status)

    # Callbacks
    def _on_before_start(self, input_dir: Path, output_dir: Path) -> None:
        raise NotImplementedError("Must be implemented by subclass")

    # Internal helpers
    def _validate_directories(self, *dirs: tuple[Path | None, str]) -> bool:
        for current_dir, info in dirs:
            if current_dir is None or not current_dir.exists():
                logger.error(
                    "[{}] Invalid dir: {} ({})",
                    self,
                    (
                        current_dir.absolute().as_posix()
                        if isinstance(current_dir, Path)
                        else current_dir
                    ),
                    info,
                )
                return False

        return True

    def switch_btn(self) -> None:
        for btn in self.context.main_buttons:
            btn.setEnabled(not self._started)

        self.start_btn.setVisible(not self._started)
        self.start_btn.setEnabled(not self._started)
        self.stop_btn.setVisible(self._started)
        self.stop_btn.setEnabled(self._started)

    def _update_progress(self) -> None:
        percent = (
            int((self._current_task_index / self._total_tasks) * 100) if self._total_tasks else 0
        )
        self.progress_bar_manager.widget.setValue(percent)

    def on_task_finished(
        self,
        target_dir: Path,
        status: VideoDirStatus,
    ) -> None:
        self.update_directory_status(
            target_dir,
            status,
        )

        with self._lock:
            self._current_task_index += 1

        self._update_progress()

        if self._started:
            self._process_next()
        else:
            self.switch_btn()

    def _process_next(self) -> None:
        if self._current_task_index >= self._total_tasks:
            self.elapsed_time_manger.widget.stop()
            self.progress_bar_manager.widget.setValue(100)

            self._started = False
            self.switch_btn()

            elapsed = time.monotonic() - self._start_time
            logger.success(
                "Processing completed in {}",
                humanize.precisedelta(elapsed),
            )

            return

        with self._lock:
            target_dir = next(self._current_task_iter)

        self.update_directory_status(
            target_dir,
            VideoDirStatus.processing,
        )

        res = self.worker.start(target_dir)

        if res is not None:
            self.on_task_finished(target_dir, res)

    @property
    def worker(self) -> VideoProcessingWorkerProtocol:
        raise NotImplementedError("Must be implemented by subclass")
