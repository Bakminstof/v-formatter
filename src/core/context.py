from queue import Queue

from pydantic import BaseModel, ConfigDict
from PySide6.QtWidgets import QPushButton

from core.models import MetadataModel, VideosStructureModel
from threads.executor import ProcessPoolExecutorThread, ProcessQueueExecutorThread
from ui.i18n import I18n


class ProcessesInfrastructureContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    queue_max_size: int = 10_000

    sequential_queue: Queue | None = None
    sequential_executor: ProcessQueueExecutorThread | None = None

    pool_queue: Queue | None = None
    pool_executor: ProcessPoolExecutorThread | None = None


class AppContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    metadata: MetadataModel = MetadataModel()
    concat_structure: VideosStructureModel = VideosStructureModel()
    main_buttons: set[QPushButton] = set()

    processes: ProcessesInfrastructureContext = ProcessesInfrastructureContext()

    i18n: I18n
