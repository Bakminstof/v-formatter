from PySide6.QtCore import QThread, Signal

from core.models import VersionsInfoModel
from updates.git_updater import GitUpdater


class VersionCheckWorker(QThread):
    finished = Signal(VersionsInfoModel)
    error = Signal(str)

    def __init__(self, git_updater: GitUpdater) -> None:
        super().__init__()
        self.git_updater = git_updater

    def run(self) -> None:
        try:
            self.git_updater.startup()
            model = self.git_updater.versions_data
            self.finished.emit(model)
        except Exception as e:
            self.error.emit(str(e))
