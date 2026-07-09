from pydantic import BaseModel

from core.concatenator import VideosStructureModel
from core.models import MetadataModel


class AppContext(BaseModel):
    metadata: MetadataModel = MetadataModel()
    concat_structure: VideosStructureModel = VideosStructureModel()
