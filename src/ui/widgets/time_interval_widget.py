from typing import Callable

from PySide6.QtCore import QTime, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QTimeEdit,
    QWidget,
)

from core.models import MetadataModel


class TimeIntervalWidget(QWidget):
    time_changed = Signal()

    def __init__(
        self,
        label: str,
        from_label: str,
        to_label: str,
        checked: bool = True,
        on_time_changed: Callable[[], None] | None = None,
        on_checked: Callable[[bool], None] | None = None,
    ) -> None:
        super().__init__()

        self._on_time_changed = on_time_changed
        self._on_checked = on_checked

        self.checkbox = QCheckBox(label)
        self.checkbox.setChecked(checked)
        self.checkbox.toggled.connect(self.on_checkbox_toggled)

        self.from_label = QLabel(from_label)
        self.from_time = QTimeEdit()
        self.from_time.setDisplayFormat("HH:mm")
        self.from_time.setTime(QTime(0, 0))

        self.to_label = QLabel(to_label)
        self.to_time = QTimeEdit()
        self.to_time.setDisplayFormat("HH:mm")
        self.to_time.setTime(QTime(23, 59))

        self.from_time.editingFinished.connect(self._on_editing_finished)
        self.to_time.editingFinished.connect(self._on_editing_finished)

        self.on_checkbox_toggled(checked)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self.checkbox)
        layout.addWidget(self.from_label)
        layout.addWidget(self.from_time)
        layout.addWidget(self.to_label)
        layout.addWidget(self.to_time)
        layout.addStretch(1)

        self.setLayout(layout)

    def on_checkbox_toggled(self, checked: bool) -> None:
        self.from_label.setEnabled(checked)
        self.from_time.setEnabled(checked)
        self.to_label.setEnabled(checked)
        self.to_time.setEnabled(checked)

        if self._on_checked:
            self._on_checked(checked)

    def _on_editing_finished(self) -> None:
        if self._on_time_changed:
            self._on_time_changed()

        self.time_changed.emit()

    def is_enabled(self) -> bool:
        return self.checkbox.isChecked()

    def set_current_times(self, from_time: str, to_time: str) -> None:
        from_time = from_time.split(":")
        to_time = to_time.split(":")

        self.from_time.blockSignals(True)
        self.to_time.blockSignals(True)

        self.from_time.setTime(QTime(int(from_time[0]), int(from_time[1])))
        self.to_time.setTime(QTime(int(to_time[0]), int(to_time[1])))

        self.from_time.blockSignals(False)
        self.to_time.blockSignals(False)

    @property
    def time_range(self) -> tuple[str, str] | None:
        if not self.is_enabled():
            return None

        return (
            self.from_time.time().toString("HH:mm"),
            self.to_time.time().toString("HH:mm"),
        )


class TimeIntervalManager:
    def __init__(
        self,
        metadata_cache_getter: Callable[[], MetadataModel],
        label: str,
        from_label: str,
        to_label: str,
        checked: bool = True,
    ) -> None:
        self.__metadata_cache = metadata_cache_getter

        self.widget = TimeIntervalWidget(
            label,
            from_label,
            to_label,
            checked,
            self.__on_change,
            self.__on_checked,
        )

    def startup(self) -> None:
        time_from: str = self.__metadata_cache().filters.time.time_from
        time_to: str = self.__metadata_cache().filters.time.time_to
        enabled = self.__metadata_cache().filters.time.enabled

        self.widget.on_checkbox_toggled(enabled)
        self.widget.checkbox.setChecked(enabled)

        self.widget.set_current_times(
            time_from,
            time_to,
        )

    def __on_checked(self, checked: bool) -> None:
        self.__metadata_cache().filters.time.enabled = checked

    def __on_change(self) -> None:
        if not self.widget.is_enabled():
            return

        time_from, time_to = self.widget.time_range

        self.__metadata_cache().filters.time.time_from = time_from
        self.__metadata_cache().filters.time.time_to = time_to
