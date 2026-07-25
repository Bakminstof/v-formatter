from pathlib import Path

from PySide6.QtWidgets import QListWidget, QListWidgetItem

from core.context import AppContext
from ui.widgets.directory_item_widget import DirectoryItemWidget


class QueueListManager:
    def __init__(self, context: AppContext) -> None:
        self.context = context

        self.widget = QListWidget()

        self.__next_index = 0
        self.__source_path_idx_map: dict[Path, int] = {}

    def get_idx_by_source_path(self, source_path: Path) -> int:
        return self.__source_path_idx_map[source_path]

    def add_directory_status(
        self,
        source_path: Path,
        status: str,
        process_it: bool = True,
    ) -> None:
        item = QListWidgetItem()
        widget = DirectoryItemWidget(source_path, status, checked=process_it)
        widget.checkbox_toggled.connect(self._on_checkbox_toggled)

        self.widget.addItem(item)
        self.widget.setItemWidget(item, widget)

        self.__source_path_idx_map[source_path] = self.__next_index
        self.__next_index += 1

    def update_directory_status(self, index: int, status: str) -> None:
        item = self.widget.item(index)

        if item is None:
            return

        widget = self.widget.itemWidget(item)

        if isinstance(widget, DirectoryItemWidget):
            widget.set_status(status)

    def clear(self) -> None:
        self.__next_index = 0
        self.__source_path_idx_map.clear()
        self.widget.clear()

    def _on_checkbox_toggled(self, source_path: Path, checked: bool) -> None:
        if source_path in self.context.concat_structure.data:
            self.context.concat_structure.data[source_path].process_it = checked
