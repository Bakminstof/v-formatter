from core.database import MetadataRegistry, Registry
from core.models import MetadataModel


class MetadataMixin:
    def __init__(self, inited_registry: Registry, **kwargs) -> None:
        super().__init__(**kwargs)

        self.metadata_registry: MetadataRegistry = getattr(
            inited_registry,
            MetadataRegistry.__table_name__,
        )

        self.__metadata_cache = MetadataModel()

    def get_metadata_cache(self) -> MetadataModel:
        return self.__metadata_cache

    def load_metadata(self) -> None:
        self.__metadata_cache = self.metadata_registry.load()

    def save_metadata(self) -> None:
        self.metadata_registry.save(self.__metadata_cache)
