from loguru import logger
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QWidget,
)

from core.models import UNKNOWN_VERSION, VersionsInfoModel
from threads.workers.prepare_update_worker import PrepareUpdateWorker
from ui.i18n import I18n
from ui.models import VersionStatus
from updates.git_updater import GitUpdater


class VersionWidget(QWidget):
    update_requested = Signal()
    switch_version_requested = Signal(str)

    def __init__(
        self,
        label: str,
        update_button_label: str,
        all_versions_label: str,
        unknown_version_label: str = UNKNOWN_VERSION,
    ) -> None:
        super().__init__()

        self.unknown_version_label = unknown_version_label

        self.label = label
        self.update_button_label = update_button_label
        self.all_versions_label = all_versions_label

        self._model: VersionsInfoModel | None = None

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.version_label = QLabel(f"{self.label}: {self.unknown_version_label}")
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
        self.update_btn.blockSignals(True)
        self.refresh(model)
        self._model = model
        self.update_btn.blockSignals(False)

    def refresh(self, model: VersionsInfoModel) -> None:
        current = model.current
        latest = model.latest
        all_versions = model.all

        if current == latest:
            status = VersionStatus.actual
            update_btn_visible = False
        elif latest == UNKNOWN_VERSION:
            status = VersionStatus.cant_check
            update_btn_visible = False
        else:
            status = VersionStatus.need_update
            update_btn_visible = True

        self.version_label.setText(f"{self.label} {current} {status}")

        self.update_btn.setVisible(update_btn_visible)

        self.version_combo.blockSignals(True)
        self.version_combo.clear()
        self.version_combo.addItems(all_versions)

        if current in set(all_versions):
            self.version_combo.setCurrentText(current)

        self.version_combo.blockSignals(False)

    def _on_update_clicked(self) -> None:
        if not self._model:
            return

        self.update_requested.emit()

    def _on_combo_changed(self) -> None:
        if not self._model:
            return

        selected = self.version_combo.currentText()
        if selected != self._model.current:
            self.switch_version_requested.emit(selected)


class VersionManager:
    def __init__(
        self,
        parent: QWidget,
        git_updater: GitUpdater,
        i18n: I18n,
        label: str,
        update_button_label: str,
        all_versions_label: str,
        unknown_version_label: str = UNKNOWN_VERSION,
    ) -> None:
        self.__parent = parent
        self.__git_updater = git_updater
        self._i18n = i18n
        self._prepare_worker: PrepareUpdateWorker

        self.widget = VersionWidget(
            label,
            update_button_label,
            all_versions_label,
            unknown_version_label,
        )
        self.widget.update_requested.connect(self._on_update_requested)
        self.widget.switch_version_requested.connect(self._on_switch_version_requested)

    def startup(self) -> None:
        self.__git_updater.startup()
        self.widget.set_model(self.__git_updater.versions_data)

    def prepare_update(self) -> None:
        self.__git_updater.prepare_update()

    def _on_update_requested(self) -> None:
        latest = self.__git_updater.versions_data.latest

        if latest == UNKNOWN_VERSION:
            logger.warning(self._i18n.t("version.log.update_not_found"))
            QMessageBox.warning(
                self.__parent,
                self._i18n.t("version.error.title"),
                self._i18n.t("version.error.update_not_found"),
            )
            return

        self._launch_updater(latest)

    def _on_switch_version_requested(self, version_tag: str) -> None:
        reply = QMessageBox.question(
            self.__parent,
            self._i18n.t("version.switch.title"),
            self._i18n.t("version.switch.message", version_tag),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._launch_updater(version_tag)

    def _on_update_prepared(self) -> None:
        self._progress_dialog.close()
        self.__git_updater.launch_updater(
            self._prepare_worker.version,
        )
        self.__parent.close()

    def _on_update_prepare_error(self, error_msg: str) -> None:
        self._progress_dialog.close()
        logger.error(self._i18n.t("version.log.prepare_error", error_msg))
        QMessageBox.critical(
            self.__parent,
            self._i18n.t("version.error.title"),
            self._i18n.t("version.error.prepare_failed", error_msg),
        )

    def _cancel_update_preparation(self) -> None:
        self._progress_dialog.close()

    def _launch_updater(self, version_tag: str) -> None:
        self._progress_dialog = QProgressDialog(
            self._i18n.t("version.progress.preparing_update"),
            self._i18n.t("version.progress.cancel"),
            0,
            0,
            self.__parent,
        )
        self._progress_dialog.setWindowTitle(self._i18n.t("version.progress.title"))
        self._progress_dialog.setWindowModality(Qt.WindowModal)
        self._progress_dialog.setMinimumDuration(0)
        self._progress_dialog.setValue(0)
        self._progress_dialog.canceled.connect(self._cancel_update_preparation)
        self._progress_dialog.show()

        self._prepare_worker = PrepareUpdateWorker(self.__git_updater, version_tag)
        self._prepare_worker.finished.connect(self._on_update_prepared)
        self._prepare_worker.error.connect(self._on_update_prepare_error)

        self._prepare_worker.start()

        QApplication.processEvents()
