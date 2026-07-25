from pathlib import Path
from queue import Queue

from PySide6.QtCore import QEvent, QThreadPool
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from core.concatenator import VideoConcatenator
from core.context import AppContext
from core.database import FormatRegistry, Registry, VideoRegistry
from core.helpers import MetadataHelper
from core.meta import VideoMetaProcessor
from core.models import AppInfoModel
from core.utils import get_supported_formats
from processes import ProcessResult
from threads.executor import (
    MANAGED_PROCESS_FINISHED_EVENT_TYPE,
    ProcessFinishedEvent,
    ProcessPoolExecutorThread,
    ProcessQueueExecutorThread,
)
from threads.manage import Runnable, TaskScheduler
from ui.i18n import I18n
from ui.models import VideoDirStatus
from ui.widgets.concat_widget import ConcatManager
from ui.widgets.dir_selector_widget import DirSelectorManger
from ui.widgets.elapsed_time_widget import ElapsedTimeManger
from ui.widgets.format_selector_widget import FormatSelectorManager
from ui.widgets.log_widget import LogManager
from ui.widgets.progress_bar_widget import ProgressBarManager
from ui.widgets.queue_list_widget import QueueListManager
from ui.widgets.repo_origin_widget import RepoOriginManager
from ui.widgets.scan_widget import ScanManager
from ui.widgets.time_interval_widget import TimeIntervalManager
from ui.widgets.version_widget import VersionManager
from updates.git_updater import GitUpdater
from workers.processing_workers import VideoProcessingAction


class MainWindow(QMainWindow):
    def __init__(
        self,
        ffmpeg: Path,
        main_icon_path: Path,
        origin_icon_path: Path,
        i18n: I18n,
        app_info: AppInfoModel,
        git_updater: GitUpdater,
        video_concatenator: VideoConcatenator,
        meta_processor: VideoMetaProcessor,
        registry: Registry,
        log_level: str = "INFO",
    ) -> None:
        super().__init__(parent=None)

        self.context = AppContext(i18n=i18n)
        self.registry = registry

        self._metadata_helper = MetadataHelper(self.registry, self.context)

        self.ffmpeg = ffmpeg

        self._app_info = app_info
        self.main_icon_path = main_icon_path

        self.i18n = i18n

        # --- Initialize Widget Managers ---
        self.input_dir_widget_manager = DirSelectorManger(
            self.context,
            "input_dir",
            self.i18n.t("input_dir"),
            self.i18n.t("select_folder"),
        )
        self.output_dir_widget_manager = DirSelectorManger(
            self.context,
            "output_dir",
            self.i18n.t("output_dir"),
            self.i18n.t("select_folder"),
        )
        self.log_manger = LogManager(log_level)
        self.queue_manager = QueueListManager(self.context)
        self.progress_bar_manager = ProgressBarManager()
        self.elapsed_time_manger = ElapsedTimeManger(self.i18n.t("elapsed_time"))
        self.time_interval_filter_manager = TimeIntervalManager(
            self.context,
            self.i18n.t("time_filter"),
            self.i18n.t("time_filter_label_time_from"),
            self.i18n.t("time_filter_label_time_to"),
        )
        self.scan_manager = ScanManager(
            start_btn_label=self.i18n.t("scan.start"),
            stop_btn_label=self.i18n.t("scan.stop"),
            context=self.context,
            gui_receiver=self,
            meta_processor=meta_processor,
            video_concatenator=video_concatenator,
            elapsed_time_manger=self.elapsed_time_manger,
            progress_bar_manager=self.progress_bar_manager,
            queue_manager=self.queue_manager,
        )
        self.concat_manager = ConcatManager(
            start_btn_label=self.i18n.t("concat.start"),
            stop_btn_label=self.i18n.t("concat.stop"),
            context=self.context,
            gui_receiver=self,
            video_concatenator=video_concatenator,
            elapsed_time_manger=self.elapsed_time_manger,
            progress_bar_manager=self.progress_bar_manager,
            queue_manager=self.queue_manager,
            video_registry=getattr(
                registry,
                VideoRegistry.__table_name__,
            ),
        )
        self.format_selector_manager = FormatSelectorManager(
            self.context,
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
        self.repo_origin_manager = RepoOriginManager(self._app_info, i18n, origin_icon_path)

        # Tasks
        self.task_scheduler = TaskScheduler()

        self.__build_layout()
        self.__on_startup()

    def __build_layout(self) -> None:
        self.resize(1000, 650)
        self.setMinimumSize(900, 550)

        self.setWindowIcon(QIcon(self.main_icon_path.absolute().as_posix()))
        self.setWindowTitle(self._app_info.name)

        layout = QVBoxLayout()

        top_layout = QHBoxLayout()
        top_layout.addWidget(self.version_manager.widget)
        top_layout.addStretch(1)
        top_layout.addWidget(self.repo_origin_manager.widget)
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
        buttons_layout = QHBoxLayout()
        buttons_layout.addLayout(self.scan_manager.layout())
        buttons_layout.addLayout(self.concat_manager.layout())
        layout.addLayout(buttons_layout)

        container = QWidget()
        container.setLayout(layout)

        self.setCentralWidget(container)

    def __update_metadata(self) -> None:
        self._metadata_helper.load_metadata()

        self.input_dir_widget_manager.startup()
        self.output_dir_widget_manager.startup()
        self.time_interval_filter_manager.startup()

        self.__update_supported_formats()

    def __update_version_info(self) -> None:
        self.version_manager.startup()

    def __update_supported_formats(self) -> None:
        format_registry: FormatRegistry = getattr(
            self.registry,
            FormatRegistry.__table_name__,
        )

        formats = format_registry.list_all()

        if not formats:
            formats = get_supported_formats(self.ffmpeg)

        format_registry.add_batch(formats)

        self.format_selector_manager.widget.fill(formats)
        self.format_selector_manager.startup()

    def __startup_process_infrastructure(self) -> None:
        self.context.processes.sequential_queue = Queue(self.context.processes.queue_max_size)
        self.context.processes.pool_queue = Queue(self.context.processes.queue_max_size)

        self.context.processes.sequential_executor = ProcessQueueExecutorThread(
            self,
            self.context.processes.sequential_queue,
        )
        self.context.processes.pool_executor = ProcessPoolExecutorThread(
            self,
            self.context.processes.pool_queue,
        )

        executors = self.context.processes.sequential_executor, self.context.processes.pool_executor

        for executor in executors:
            executor.start()

    def __shutdown_process_infrastructure(self) -> None:
        executors = self.context.processes.sequential_executor, self.context.processes.pool_executor

        for executor in executors:
            if not executor:
                continue

            executor.stop()

    def __on_startup(self) -> None:
        self.__startup_process_infrastructure()

        global_pool = QThreadPool.globalInstance()
        tasks = [
            Runnable(self.__update_metadata),
            Runnable(self.__update_version_info),
            Runnable(self.__update_supported_formats),
            Runnable(self.version_manager.prepare_update),
        ]

        for t in tasks:
            global_pool.start(t)

        self.task_scheduler.add_task(
            self._metadata_helper.save_metadata,
            30,
        )

    def event(self, e: QEvent) -> bool:
        if e.type() == MANAGED_PROCESS_FINISHED_EVENT_TYPE:
            e: ProcessFinishedEvent

            if (
                e.meta.get("action") is VideoProcessingAction.scan
                and e.meta.get("is_success") is not None
            ):
                status = VideoDirStatus.done if e.meta.get("is_success") else VideoDirStatus.error
                self.scan_manager.on_task_finished(e.meta["processed_dir"], status)
                return True

            if e.meta.get("action") is VideoProcessingAction.concat and e.result:
                if isinstance(e.result, ProcessResult) and e.result.exit_code == 0:
                    status = VideoDirStatus.done
                else:
                    status = VideoDirStatus.error

                self.concat_manager.on_task_finished(e.meta["processed_dir"], status)
                return True

        return super().event(e)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._metadata_helper.save_metadata()
        self.task_scheduler.stop_all()
        self.__shutdown_process_infrastructure()
        super().closeEvent(event)
