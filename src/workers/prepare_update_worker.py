from PySide6.QtCore import QThread, Signal

from updates.git_updater import GitUpdater


class PrepareUpdateWorker(QThread):
    finished = Signal()
    error = Signal(str)

    def __init__(
        self,
        git_updater: GitUpdater,
        version_tag: str,
    ) -> None:
        super().__init__()

        self.git_updater = git_updater

        self.version = version_tag

    def run(self) -> None:
        try:
            self.git_updater.prepare_update()
            self.git_updater.cleanup()
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))
