from core.context import AppContext
from core.database import MetadataRegistry, Registry


class MetadataHelper:
    def __init__(self, inited_registry: Registry, context: AppContext) -> None:
        self.metadata_registry: MetadataRegistry = getattr(
            inited_registry,
            MetadataRegistry.__table_name__,
        )

        self.context = context

    def load_metadata(self) -> None:
        self.context.metadata = self.metadata_registry.load()

    def save_metadata(self) -> None:
        self.metadata_registry.save(self.context.metadata)
