import time
from pathlib import Path
from typing import Iterator

import humanize
from core.database import VideoRegistry
from core.meta import VideoMetaProcessor
from core.models import AppInfoModel
from loguru import logger
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.concatenator import VideoConcatenator, VideosStructureModel
from ui.i18n import I18n, get_windows_ui_language
from ui.models import LocalMetaModel, Status, Lang
from ui.settings import load_local_meta, save_local_meta
from ui.widgets.dir_selector import DirSelectorWidget
from ui.widgets.elapsed_time import ElapsedTimeWidget
from ui.widgets.format_selector import FormatSelectorWidget
from ui.widgets.log_widget import LogWidget, QtLogHandler
from ui.widgets.time_interval import TimeIntervalWidget
from ui.workers.directory_worker import Worker


class MainWindow(QMainWindow):
    def __init__(
        self,
        icon_path: Path,
        temp_dir: Path,
        encoding: str,
        default_locale: Lang,
        locales_dir: Path,
        local_meta_file_path: Path,
        *,
        app_info: AppInfoModel,
        video_concatenator: VideoConcatenator,
        meta_processor: VideoMetaProcessor,
        registry: VideoRegistry,
    ) -> None:
        super().__init__()
        self._app_info = app_info

        self.__temp_dir = temp_dir
        self.__encoding = encoding

        self.video_concatenator = video_concatenator
        self.meta_processor = meta_processor
        self.registry = registry

        # --- Window config ---
        self.icon_path = icon_path

        self.videos_structure = VideosStructureModel()

        # Tasks
        self.total_tasks: int = 0
        self.current_task_index: int = 0
        self.current_task_iter: Iterator[Path] | None = None
        self.start_time: float = 0.0

        # i18n
        self.i18n = I18n(
            get_windows_ui_language(default_locale),
            self.__encoding,
            locales_dir,
        )

        self.setWindowTitle(f"{self._app_info.name} ({self._app_info.version})")

        # load settings
        self.local_meta_file_path = local_meta_file_path
        self.local_meta: LocalMetaModel = load_local_meta(
            self.local_meta_file_path,
            encoding=self.__encoding,
        )

        self.worker: Worker
        self.format_widget: FormatSelectorWidget
        self.elapsed_time_widget: ElapsedTimeWidget
        self.time_filter_widget: TimeIntervalWidget

        # --- Initialize UI ---
        self.input_dir_widget: DirSelectorWidget
        self.output_dir_widget: DirSelectorWidget

        self._init_window()

        self.log_widget: LogWidget
        self.log_handler: QtLogHandler
        self._init_log_container()

        self._init_dir_selectors()
        self._init_status_container()
        self._init_buttons()
        self._init_format_selector()
        self._init_elapsed_time_widget()
        self._init_time_filter_widget()
        self._init_layout()

    # ---------- UI Initialization ----------
    def _init_window(self) -> None:
        self.resize(1000, 650)
        self.setMinimumSize(900, 550)

        self.setWindowIcon(QIcon(self.icon_path.absolute().as_posix()))

    def _init_dir_selectors(self):
        self.input_dir_widget = DirSelectorWidget(
            self.i18n.t("input_dir"),
            self.local_meta.input_dir,
            self._on_input_dir_changed,
        )
        self.output_dir_widget = DirSelectorWidget(
            self.i18n.t("output_dir"),
            self.local_meta.output_dir,
            self._on_output_dir_changed,
        )

    def _init_status_container(self) -> None:
        self.queue_label = QLabel(self.i18n.t("queue"))
        self.queue_list = QListWidget()
        self.progress_bar = QProgressBar()

    def _init_log_container(self) -> None:
        self.log_widget = LogWidget()
        self.log_handler = QtLogHandler()
        self.log_handler.log_signal.connect(self.log_widget.append_log)

    def _init_buttons(self):
        self.start_btn = QPushButton(self.i18n.t("start"))
        self.stop_btn = QPushButton(self.i18n.t("stop"))

        self.start_btn.clicked.connect(self.start)
        self.stop_btn.clicked.connect(self.stop)

    def _init_format_selector(self) -> None:
        self.format_widget = FormatSelectorWidget(
            self.i18n.t("format"),
            self.local_meta.video_format,
            self._on_format_changed,
        )

    def _init_elapsed_time_widget(self) -> None:
        self.elapsed_time_widget = ElapsedTimeWidget(self.i18n.t("elapsed_time"))

    def _init_time_filter_widget(self) -> None:
        self.time_filter_widget = TimeIntervalWidget(
            self.i18n.t("time_filter"),
            self.i18n.t("time_filter_label_time_from"),
            self.local_meta.filters.time.time_from,
            self.i18n.t("time_filter_label_time_to"),
            self.local_meta.filters.time.time_to,
        )

    def _init_layout(self):
        layout = QVBoxLayout()

        # --- Directory selectors ---
        layout.addWidget(QLabel(self.i18n.t("input_dir")))
        layout.addWidget(self.input_dir_widget)
        layout.addWidget(QLabel(self.i18n.t("output_dir")))
        layout.addWidget(self.output_dir_widget)

        format_row = QHBoxLayout()
        format_row.addWidget(self.format_widget)
        format_row.addWidget(self.elapsed_time_widget)
        format_row.addWidget(self.time_filter_widget)
        format_row.addStretch(1)

        layout.addLayout(format_row)

        # --- Split: Status container / Logs container ---
        # Status container
        layout.addWidget(self.queue_label)
        layout.addWidget(self.queue_list)
        layout.addWidget(self.progress_bar)

        # Logs container
        layout.addWidget(QLabel(self.i18n.t("logs")))
        layout.addWidget(self.log_widget)

        # Buttons
        buttons_row = QHBoxLayout()
        buttons_row.addWidget(self.start_btn)
        buttons_row.addWidget(self.stop_btn)
        layout.addLayout(buttons_row)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    # ---------- Callbacks ----------

    def _on_input_dir_changed(self, path: Path) -> None:
        self.local_meta.input_dir = path
        save_local_meta(
            self.local_meta,
            self.local_meta_file_path,
            encoding=self.__encoding,
        )

    def _on_output_dir_changed(self, path: Path) -> None:
        self.local_meta.output_dir = path
        save_local_meta(
            self.local_meta,
            self.local_meta_file_path,
            encoding=self.__encoding,
        )

    def _on_format_changed(self, fmt: str) -> None:
        self.local_meta.video_format = fmt
        save_local_meta(
            self.local_meta,
            self.local_meta_file_path,
            encoding=self.__encoding,
        )

    # ---------- Worker control ----------

    def _save_current_meta(self) -> None:
        input_dir = Path(self.input_dir_widget.get_path())
        output_dir = Path(self.output_dir_widget.get_path())

        if not input_dir.is_absolute():
            input_dir = self.__temp_dir / input_dir
        if not output_dir.is_absolute():
            output_dir = self.__temp_dir / output_dir

        self.input_dir_widget.set_path(input_dir.absolute().as_posix())
        self.output_dir_widget.set_path(output_dir.absolute().as_posix())

        self.local_meta.filters.time.time_from = self.time_filter_widget.time_range[0]
        self.local_meta.filters.time.time_to = self.time_filter_widget.time_range[1]

        save_local_meta(
            self.local_meta,
            self.local_meta_file_path,
            encoding=self.__encoding,
        )

    def start(self) -> None:
        self._save_current_meta()

        self.videos_structure = self.video_concatenator.collect_data_dirs(
            self.local_meta.input_dir,
            self.local_meta.output_dir,
            self.local_meta.video_format,
        )

        self.queue_list.clear()
        self.progress_bar.setValue(0)

        for inp_path in self.videos_structure.data.keys():
            self.add_directory_status(inp_path.name, Status.waiting)

        self.total_tasks = len(self.videos_structure.data)
        self.current_task_index = 0
        self.current_task_iter = iter(self.videos_structure.data.keys())

        self.start_time = time.monotonic()
        self.elapsed_time_widget.reset()
        self.elapsed_time_widget.start()

        logger.info(f"Найдено директорий: {self.total_tasks}")

        self._process_next()

    def stop(self) -> None:
        if hasattr(self, "worker"):
            self.worker.stop()

        self.elapsed_time_widget.stop()

    def _update_progress(self) -> None:
        percent = int(
            (self.current_task_index / self.total_tasks) * 100 if self.total_tasks else 0
        )
        self.progress_bar.setValue(percent)

    def _on_task_finished(self, success: bool) -> None:
        status = Status.done if success else Status.error
        self.update_directory_status(self.current_task_index, status)

        self.current_task_index += 1
        self._update_progress()

        self._process_next()

    def _process_next(self) -> None:
        self.worker = None

        if self.current_task_index >= self.total_tasks:
            self.elapsed_time_widget.stop()

            elapsed = time.monotonic() - self.start_time
            text = humanize.precisedelta(elapsed)
            logger.success("Обработка завершена за {}", text)
            self.progress_bar.setValue(100)
            self._save_current_meta()
            return

        index = self.current_task_index
        inp_path = next(self.current_task_iter)

        self.update_directory_status(index, Status.processing)

        self.worker = Worker(
            inp_path,
            self.videos_structure,
            self.local_meta.video_format,
            video_concatenator=self.video_concatenator,
            meta_processor=self.meta_processor,
            registry=self.registry,
            start_at=self.time_filter_widget.time_range[0],
            end_at=self.time_filter_widget.time_range[1],
        )
        self.worker.finished.connect(self._on_task_finished)
        self.worker.start()

    # ---------- Status & Logging ----------

    def add_directory_status(
        self,
        directory: str,
        status: str = Status.waiting,
    ) -> None:
        self.queue_list.addItem(f"{status} {directory}")

    def update_directory_status(self, index: int, status: Status) -> None:
        item = self.queue_list.item(index)

        if not item:
            return

        directory_name = item.text().split(" ", 1)[1]
        item.setText(f"{status} {directory_name}")
