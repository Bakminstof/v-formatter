from pathlib import Path

from PySide6.QtCore import QThreadPool
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from core.concatenator import VideoConcatenator
from core.database import Registry, VideoRegistry
from core.meta import VideoMetaProcessor
from core.mixins import MetadataMixin
from core.models import AppInfoModel
from threads.manage import Runnable, TaskManager
from ui.i18n import I18n
from ui.widgets.concat_widget import ConcatManager
from ui.widgets.dir_selector_widget import DirSelectorManger
from ui.widgets.elapsed_time_widget import ElapsedTimeManger
from ui.widgets.format_selector_widget import FormatSelectorManager
from ui.widgets.log_widget import LogManager
from ui.widgets.progress_bar_widget import ProgressBarManager
from ui.widgets.queue_list_widget import QueueListManager
from ui.widgets.time_interval_widget import TimeIntervalManager
from ui.widgets.version_widget import VersionManager
from updates.git_updater import GitUpdater


class MainWindow(QMainWindow, MetadataMixin):
    def __init__(
        self,
        icon_path: Path,
        i18n: I18n,
        app_info: AppInfoModel,
        git_updater: GitUpdater,
        video_concatenator: VideoConcatenator,
        meta_processor: VideoMetaProcessor,
        registry: Registry,
        log_level: str = "INFO",
    ) -> None:
        super().__init__(inited_registry=registry, parent=None)

        self._app_info = app_info
        self.icon_path = icon_path

        self.i18n = i18n

        # --- Initialize Managers ---
        self.input_dir_widget_manager = DirSelectorManger(
            self.get_metadata_cache,
            "input_dir",
            self.i18n.t("input_dir"),
            self.i18n.t("select_folder"),
        )
        self.output_dir_widget_manager = DirSelectorManger(
            self.get_metadata_cache,
            "output_dir",
            self.i18n.t("output_dir"),
            self.i18n.t("select_folder"),
        )
        self.log_manger = LogManager(log_level)
        self.queue_manager = QueueListManager()
        self.progress_bar_manager = ProgressBarManager()
        self.elapsed_time_manger = ElapsedTimeManger(self.i18n.t("elapsed_time"))
        self.time_interval_filter_manager = TimeIntervalManager(
            self.get_metadata_cache,
            self.i18n.t("time_filter"),
            self.i18n.t("time_filter_label_time_from"),
            self.i18n.t("time_filter_label_time_to"),
        )
        self.concat_manager = ConcatManager(
            self.i18n.t("start"),
            self.i18n.t("stop"),
            self.get_metadata_cache,
            video_concatenator,
            meta_processor,
            getattr(
                registry,
                VideoRegistry.__table_name__,
            ),
            self.elapsed_time_manger,
            self.progress_bar_manager,
            self.queue_manager,
            self.time_interval_filter_manager,
        )
        self.format_selector_manager = FormatSelectorManager(
            self.get_metadata_cache,
            self.i18n.t("format"),
        )

        self.version_manager = VersionManager(
            self,
            git_updater,
            self.i18n,
            self.i18n.t("app_current_version"),
            self.i18n.t("update_do"),
            self.i18n.t("app_all_versions"),
        )

        # Tasks
        self.task_scheduler = TaskManager()

        self.__build_layout()
        self.__on_startup()

    def __build_layout(self) -> None:
        self.resize(1000, 650)
        self.setMinimumSize(900, 550)

        self.setWindowIcon(QIcon(self.icon_path.absolute().as_posix()))
        self.setWindowTitle(self._app_info.name)

        layout = QVBoxLayout()

        top_layout = QHBoxLayout()
        top_layout.addStretch(1)
        top_layout.addWidget(self.version_manager.widget)
        layout.addLayout(top_layout)

        # Directory selectors
        layout.addWidget(QLabel(self.i18n.t("input_dir")))
        layout.addWidget(self.input_dir_widget_manager.widget)
        layout.addWidget(QLabel(self.i18n.t("output_dir")))
        layout.addWidget(self.output_dir_widget_manager.widget)

        # Format/time/filters
        format_row = QHBoxLayout()
        format_row.addWidget(self.format_selector_manager.widget)
        format_row.addWidget(self.elapsed_time_manger.widget)
        format_row.addWidget(self.time_interval_filter_manager.widget)
        format_row.addStretch(1)
        layout.addLayout(format_row)

        # Queue
        layout.addWidget(QLabel(self.i18n.t("queue")))
        layout.addWidget(self.queue_manager.widget)

        # Progress bar
        layout.addWidget(self.progress_bar_manager.widget)

        # Logs
        layout.addWidget(QLabel(self.i18n.t("logs")))
        layout.addWidget(self.log_manger.widget)

        # Buttons
        layout.addLayout(self.concat_manager.layout())

        container = QWidget()
        container.setLayout(layout)

        self.setCentralWidget(container)

    def __update_metadata(self) -> None:
        self.load_metadata()

        self.input_dir_widget_manager.startup()
        self.output_dir_widget_manager.startup()
        self.format_selector_manager.startup()
        self.time_interval_filter_manager.startup()

    def __update_version_info(self) -> None:
        self.version_manager.startup()

    def __on_startup(self) -> None:
        global_pool = QThreadPool.globalInstance()
        tasks = [
            Runnable(self.__update_metadata),
            Runnable(self.__update_version_info),
            Runnable(self.version_manager.prepare_update),
        ]

        for t in tasks:
            global_pool.start(t)

        self.task_scheduler.add_task(
            self.save_metadata,
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        self.save_metadata()
        self.task_scheduler.stop_all()
        super().closeEvent(event)
