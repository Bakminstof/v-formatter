from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QWidget


class DirectoryItemWidget(QWidget):
    checkbox_toggled = Signal(Path, bool)

    def __init__(
        self,
        source_path: Path,
        status: str,
        checked: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.source_path = source_path

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.checkbox = QCheckBox()
        self.checkbox.setChecked(checked)
        self.checkbox.toggled.connect(
            lambda is_checked: self.checkbox_toggled.emit(self.source_path, is_checked)
        )

        self.label = QLabel(f"{status} {source_path.name}")
        layout.addWidget(self.checkbox)
        layout.addWidget(self.label)
        layout.addStretch()
        self.setLayout(layout)

    def set_status(
        self,
        status: str,
        directory_name: str | None = None,
    ) -> None:
        if directory_name is None:
            directory_name = self.source_path.name

        self.label.setText(f"{status} {directory_name}")
