from pydantic import BaseModel, ConfigDict
from PySide6.QtWidgets import QPushButton

from core.concatenator import VideosStructureModel
from core.models import MetadataModel


class AppContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    metadata: MetadataModel = MetadataModel()
    concat_structure: VideosStructureModel = VideosStructureModel()
    main_buttons: set[QPushButton] = set()
