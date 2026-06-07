from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from core.models import VersionsInfoModel


class VersionWidget(QWidget):
    update_requested = Signal()
    switch_version_requested = Signal(str)

    def __init__(
        self,
        label: str,
        update_button_label: str,
        all_versions_label: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.label = label
        self.update_button_label = update_button_label
        self.all_versions_label = all_versions_label

        self._model: VersionsInfoModel | None = None
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.version_label = QLabel(f"{self.label}: unknown")
        self.update_btn = QPushButton(self.update_button_label)
        self.update_btn.setVisible(False)
        self.update_btn.clicked.connect(self._on_update_clicked)

        self.versions_label = QLabel(self.all_versions_label)
        self.version_combo = QComboBox()
        self.version_combo.currentIndexChanged.connect(self._on_combo_changed)

        layout.addWidget(self.version_label)
        layout.addWidget(self.update_btn)
        layout.addWidget(self.versions_label)
        layout.addWidget(self.version_combo)
        self.setLayout(layout)

    def set_model(self, model: VersionsInfoModel) -> None:
        self._model = model
        self._refresh()

    def _refresh(self) -> None:
        if not self._model:
            return

        current = self._model.current
        latest = self._model.latest
        all_versions = self._model.all

        is_up_to_date = current == latest
        emoji = "✅" if is_up_to_date else "⬆️"
        self.version_label.setText(f"{self.label} {current} {emoji}")

        self.update_btn.setVisible(not is_up_to_date)

        self.version_combo.blockSignals(True)
        self.version_combo.clear()
        self.version_combo.addItems(all_versions)

        if current in set(all_versions):
            self.version_combo.setCurrentText(current)

        self.version_combo.blockSignals(False)

    def _on_update_clicked(self) -> None:
        self.update_requested.emit()

    def _on_combo_changed(self) -> None:
        if not self._model:
            return

        selected = self.version_combo.currentText()
        if selected != self._model.current:
            self.switch_version_requested.emit(selected)
