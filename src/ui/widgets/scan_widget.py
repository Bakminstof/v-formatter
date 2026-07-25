from pathlib import Path

from PySide6.QtCore import QObject

from core.concatenator import VideoConcatenator
from core.context import AppContext
from core.meta import VideoMetaProcessor
from ui.models import VideoDirStatus
from ui.widgets.base_processing_widget import BaseWorkerProcessingManager
from ui.widgets.elapsed_time_widget import ElapsedTimeManger
from ui.widgets.progress_bar_widget import ProgressBarManager
from ui.widgets.queue_list_widget import QueueListManager
from workers.processing_workers import ScanWorker


class ScanManager(BaseWorkerProcessingManager):
    def __init__(
        self,
        start_btn_label: str,
        stop_btn_label: str,
        context: AppContext,
        gui_receiver: QObject,
        *,
        video_concatenator: VideoConcatenator,
        meta_processor: VideoMetaProcessor,
        elapsed_time_manger: ElapsedTimeManger,
        progress_bar_manager: ProgressBarManager,
        queue_manager: QueueListManager,
    ) -> None:
        super().__init__(
            start_btn_label,
            stop_btn_label,
            context,
            elapsed_time_manger=elapsed_time_manger,
            progress_bar_manager=progress_bar_manager,
            queue_manager=queue_manager,
        )
        self.__video_concatenator = video_concatenator

        self.__worker = ScanWorker(
            self.context,
            gui_receiver,
            meta_processor=meta_processor,
        )

    @property
    def worker(self) -> ScanWorker:
        return self.__worker

    def _on_before_start(self, input_dir: Path, output_dir: Path) -> None:
        self.queue_manager.clear()

        self.context.concat_structure = self.__video_concatenator.collect_data_dirs(
            input_dir,
            output_dir,
            self.context.metadata.video_format,
        )

        for inp_path in self.context.concat_structure.data.keys():
            info = self.context.concat_structure.data[inp_path]
            self.add_directory_status(inp_path, VideoDirStatus.waiting, info.process_it)
