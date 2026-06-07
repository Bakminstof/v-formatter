from os import environ as env
from pathlib import Path
from sys import argv, path

ROOT_DIR = Path(__file__).parent.resolve()

REPOSITORY_ROOT = ROOT_DIR.parent
ROOT_DIR_PATH_STR = ROOT_DIR.absolute().as_posix()

GIT_PYTHON_GIT_EXECUTABLE_STR = (
    (REPOSITORY_ROOT / "tools" / "PortableGit" / "bin" / "git.exe")
    .resolve(True)
    .absolute()
    .as_posix()
)

env["GIT_PYTHON_GIT_EXECUTABLE"] = GIT_PYTHON_GIT_EXECUTABLE_STR

path.append(ROOT_DIR_PATH_STR)

from loguru import logger
from PySide6.QtWidgets import QApplication

from core.concatenator import VideoConcatenator
from core.database import VideoRegistry
from core.meta import VideoMetaProcessor
from core.settings import settings
from core.utils import parse_args, startup
from ui.main_window import MainWindow
from updates.git_updater import GitUpdater


def main() -> None:
    args = parse_args()

    startup(
        settings.i18n.default_locale,
        rotation=settings.logging.rotation,
        retention=settings.logging.retention,
        compression=settings.logging.compression,
        file_format=settings.logging.file_format,
        encoding=settings.default_encoding,
        console_format=settings.logging.console_format,
        verbose=args.verbose,
        log_file=settings.logging.file_path,
    )

    registry = VideoRegistry(settings.db.path)
    registry.init_db()

    meta_processor = VideoMetaProcessor(settings.ffprobe, registry)
    video_concatenator = VideoConcatenator(
        settings.ffmpeg,
        settings.source_list_filename,
        settings.default_encoding,
        settings.ignore,
    )
    updater = GitUpdater(
        repo_path=REPOSITORY_ROOT,
        github_owner="Bakminstof",
        github_repo="v-formatter",
        portable_git_base_dir=settings.tools.portable_git_base_dir,
        updater_tmp_dir=settings.updates.updater_tmp_dir,
        tools_tmp_dir=settings.updates.tools_tmp_dir,
    )

    app = QApplication(argv)

    window = MainWindow(
        settings.ui.icon_path,
        settings.default_temp_dir,
        settings.default_encoding,
        settings.i18n.default_locale,
        settings.i18n.locales_dir,
        settings.local.meta_file_path,
        app_info=settings.app_info,
        video_concatenator=video_concatenator,
        meta_processor=meta_processor,
        registry=registry,
        git_updater=updater,
    )
    window.show()

    exit_code = app.exec()

    if exit_code != 0:
        logger.error("Application exited with code {d}", exit_code)
    else:
        logger.info("Application exited successfully")

    registry.close()

    exit(exit_code)


if __name__ == "__main__":
    main()
