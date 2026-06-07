from PySide6.QtCore import QTime
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QTimeEdit,
    QWidget,
)


class TimeIntervalWidget(QWidget):
    def __init__(
        self,
        label: str,
        from_label: str,
        from_time: str,
        to_label: str,
        to_time: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.checkbox = QCheckBox(label)
        self.checkbox.setChecked(False)
        self.checkbox.toggled.connect(self._on_checkbox_toggled)

        from_time = from_time.split(":")
        self.from_label = QLabel(from_label)
        self.from_time = QTimeEdit()
        self.from_time.setDisplayFormat("HH:mm")
        self.from_time.setTime(QTime(int(from_time[0]), int(from_time[1])))

        to_time = to_time.split(":")
        self.to_label = QLabel(to_label)
        self.to_time = QTimeEdit()
        self.to_time.setDisplayFormat("HH:mm")
        self.to_time.setTime(QTime(int(to_time[0]), int(to_time[1])))

        self._on_checkbox_toggled(False)

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

    def _on_checkbox_toggled(self, checked: bool) -> None:
        self.from_label.setEnabled(checked)
        self.from_time.setEnabled(checked)
        self.to_label.setEnabled(checked)
        self.to_time.setEnabled(checked)

    def is_enabled(self) -> bool:
        return self.checkbox.isChecked()

    @property
    def time_range(self) -> tuple[str | None, str | None]:
        if not self.is_enabled():
            return None, None

        return (
            self.from_time.time().toString("HH:mm"),
            self.to_time.time().toString("HH:mm"),
        )
