from pathlib import Path

from PySide6.QtCore import QObject

from core.concatenator import VideoConcatenator
from core.context import AppContext
from core.database import VideoRegistry
from ui.models import VideoDirStatus
from ui.widgets.base_processing_widget import BaseWorkerProcessingManager
from ui.widgets.elapsed_time_widget import ElapsedTimeManger
from ui.widgets.progress_bar_widget import ProgressBarManager
from ui.widgets.queue_list_widget import QueueListManager
from workers.processing_workers import ConcatWorker


class ConcatManager(BaseWorkerProcessingManager):
    def __init__(
        self,
        start_btn_label: str,
        stop_btn_label: str,
        context: AppContext,
        gui_receiver: QObject,
        *,
        video_concatenator: VideoConcatenator,
        video_registry: VideoRegistry,
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
        self.__video_registry = video_registry

        self.__worker = ConcatWorker(
            self.context,
            gui_receiver,
            video_concatenator=self.__video_concatenator,
            video_registry=self.__video_registry,
        )

    @property
    def worker(self) -> ConcatWorker:
        return self.__worker

    def _on_before_start(self, input_dir: Path, output_dir: Path) -> None:
        for inp_path in self.context.concat_structure.data.keys():
            info = self.context.concat_structure.data[inp_path]

            if info.process_it:
                status = VideoDirStatus.waiting
            else:
                status = VideoDirStatus.empty

            self.update_directory_status(inp_path, status)
