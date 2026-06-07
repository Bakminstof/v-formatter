from pathlib import Path

from PySide6.QtCore import QThread, Signal

from updates.git_updater import GitUpdater


class PrepareUpdateWorker(QThread):
    finished = Signal(Path)
    error = Signal(str)

    def __init__(self, git_updater: GitUpdater) -> None:
        super().__init__()
        self.git_updater = git_updater

    def run(self) -> None:
        try:
            entrypoint = self.git_updater.prepare_update()
            self.finished.emit(entrypoint)
        except Exception as e:
            self.error.emit(str(e))
