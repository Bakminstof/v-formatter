from pathlib import Path
from typing import Callable

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLineEdit, QPushButton, QWidget


class DirSelectorWidget(QWidget):
    def __init__(
        self,
        label_text: str,
        initial_path: Path | None = None,
        on_change_callback: Callable | None = None,
    ) -> None:
        super().__init__()

        self.on_change_callback = on_change_callback

        # LineEdit
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(label_text)
        self.edit.setText(initial_path.absolute().as_posix() if initial_path else "")

        # Button
        self.btn = QPushButton("📁")
        self.btn.clicked.connect(self.select_dir)

        # Layout
        row = QHBoxLayout()
        row.addWidget(self.edit)
        row.addWidget(self.btn)
        self.setLayout(row)

    def select_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Select folder", self.edit.text() or ""
        )
        if path:
            self.set_path(path)

    def set_path(self, path: str) -> None:
        self.edit.setText(path)

        if self.on_change_callback:
            self.on_change_callback(Path(path))

    def get_path(self) -> str:
        return self.edit.text().strip()
