from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QSizePolicy, QWidget

from core.models import VIDEO_FORMATS, MetadataModel, VideoFormat


class FormatSelectorWidget(QWidget):
    def __init__(
        self,
        label: str,
        on_change: Callable[[str], None] | None = None,
        formats: tuple[VideoFormat, ...] = VIDEO_FORMATS,
    ) -> None:
        super().__init__()

        self._on_change = on_change

        label_widget = QLabel(label)
        self.combo = QComboBox()

        for fmt in formats:
            self.combo.addItem(fmt.label, fmt.extension)

        self.combo.setCurrentIndex(0)
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

    def set_current_value(self, value: str) -> None:
        index = self.combo.findData(value)
        if index >= 0:
            self.combo.setCurrentIndex(index)

    def _emit_change(self) -> None:
        if self._on_change:
            self._on_change(self.current_value)

    @property
    def current_value(self) -> str:
        return self.combo.currentData()


class FormatSelectorManager:
    def __init__(
        self,
        metadata_cache_getter: Callable[[], MetadataModel],
        label: str,
        formats: tuple[VideoFormat, ...] = VIDEO_FORMATS,
    ) -> None:
        self.__metadata_cache = metadata_cache_getter

        self.widget = FormatSelectorWidget(label, self.__on_change, formats)

    def startup(self) -> None:
        self.widget.set_current_value(self.__metadata_cache().video_format)

    def __on_change(self, fmt: str) -> None:
        self.__metadata_cache().video_format = fmt
