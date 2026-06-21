from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLineEdit, QPushButton, QWidget

from core.models import Emojis, MetadataModel


class DirSelectorWidget(QWidget):
    def __init__(
        self,
        placeholder_text: str,
        select_folder_label: str,
        on_change_callback: Callable[[Path], None] | None = None,
        push_btn_label: str = Emojis.dir.value,
    ) -> None:
        super().__init__()

        # Callbacks
        self.__on_change_callback = on_change_callback

        # Text
        self.placeholder_text = placeholder_text
        self.select_folder_label = select_folder_label

        # LineEdit
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(self.placeholder_text)
        self.edit.setText("")

        # Button
        self.btn = QPushButton(push_btn_label)
        self.btn.clicked.connect(self.select_dir)

        # Layout
        row = QHBoxLayout()
        row.addWidget(self.edit)
        row.addWidget(self.btn)
        self.setLayout(row)

    def select_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            self.select_folder_label,
            self.edit.text() or "",
        )

        if path:
            self.set_path(path)

    def set_path(self, path: str | None) -> None:
        self.edit.setText(path)

        if self.__on_change_callback and path:
            self.__on_change_callback(Path(path))

    def get_path(self) -> str:
        return self.edit.text().strip()


class DirSelectorManger:
    def __init__(
        self,
        metadata_cache_getter: Callable[[], MetadataModel],
        metadata_cache_key: str,
        placeholder_text: str,
        select_folder_label: str,
        push_btn_label: str = Emojis.dir.value,
    ) -> None:
        self.metadata_cache_key = metadata_cache_key
        self.__metadata_cache = metadata_cache_getter

        self.widget = DirSelectorWidget(
            placeholder_text,
            select_folder_label,
            self.__on_change,
            push_btn_label,
        )

    def startup(self) -> None:
        self.widget.set_path(str(getattr(self.__metadata_cache(), self.metadata_cache_key)))

    def __on_change(self, path: Path) -> None:
        setattr(self.__metadata_cache(), self.metadata_cache_key, path)
