from typing import Callable, Iterable

from PySide6.QtCore import QSortFilterProxyModel, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QWidget,
)

from core.context import AppContext
from core.models import VideoFormat


class FormatSelectorWidget(QWidget):
    def __init__(
        self,
        label: str,
        on_change: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__()

        self._on_change = on_change

        label_widget = QLabel(label)
        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.setInsertPolicy(QComboBox.NoInsert)

        self.combo.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        self.combo.setMinimumWidth(180)
        self.combo.setMaximumWidth(300)

        self._proxy = QSortFilterProxyModel()
        self._proxy.setSourceModel(self.combo.model())
        self._proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self._proxy.setFilterKeyColumn(0)

        self._completer = QCompleter(self._proxy, self.combo)
        self._completer.setCompletionMode(QCompleter.PopupCompletion)
        self._completer.setFilterMode(Qt.MatchContains)
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.combo.setCompleter(self._completer)

        self.combo.lineEdit().textChanged.connect(self._on_text_changed)

        self._completer.activated.connect(self._on_completer_activated)

        self.combo.currentIndexChanged.connect(self._emit_change)

        layout = QHBoxLayout()
        layout.addWidget(label_widget)
        layout.addWidget(self.combo)
        layout.addStretch(1)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

    def fill(self, formats: Iterable[VideoFormat]) -> None:
        self.combo.clear()

        for fmt in formats:
            self.combo.addItem(
                f"({fmt.extension}) -- {fmt.description}",
                fmt.extension,
            )

    def set_current_value(self, value: str) -> None:
        self._proxy.setFilterFixedString("")
        index = self.combo.findData(value)
        if index >= 0:
            self.combo.setCurrentIndex(index)

    def _on_text_changed(self, text: str) -> None:
        self._proxy.setFilterFixedString(text)

    def _on_completer_activated(self, text: str) -> None:
        for i in range(self.combo.count()):
            if self.combo.itemText(i) == text:
                self.combo.setCurrentIndex(i)
                return

    def _emit_change(self) -> None:
        if self._on_change:
            self._on_change(self.current_value)

    @property
    def current_value(self) -> str:
        return self.combo.currentData()


class FormatSelectorManager:
    def __init__(
        self,
        context: AppContext,
        label: str,
    ) -> None:
        self.context = context

        self.widget = FormatSelectorWidget(label, self.__on_change)

    def startup(self) -> None:
        self.widget.set_current_value(self.context.metadata.video_format)

    def __on_change(self, fmt: str) -> None:
        self.context.metadata.video_format = fmt
