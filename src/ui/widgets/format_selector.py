from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QSizePolicy, QWidget

from ui.models import VIDEO_FORMATS


class FormatSelectorWidget(QWidget):
    def __init__(
        self,
        label: str,
        initial_value: str,
        on_change: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__()

        self._on_change = on_change

        label_widget = QLabel(label)
        self.combo = QComboBox()

        for fmt in VIDEO_FORMATS:
            self.combo.addItem(fmt.label, fmt.extension)

        index = self.combo.findData(initial_value)
        if index >= 0:
            self.combo.setCurrentIndex(index)

        self.combo.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        self.combo.setMinimumWidth(140)
        self.combo.setMaximumWidth(200)

        self.combo.currentIndexChanged.connect(self._emit_change)

        layout = QHBoxLayout()
        layout.addWidget(label_widget)
        layout.addWidget(self.combo)
        layout.addStretch(1)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.setContentsMargins(0, 0, 0, 0)

        self.setLayout(layout)

    def _emit_change(self) -> None:
        if self._on_change:
            self._on_change(self.current_value)

    @property
    def current_value(self) -> str:
        return self.combo.currentData()
