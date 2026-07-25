from os import environ as env
from pathlib import Path
from shutil import rmtree
from sys import argv, path

ROOT_DIR = Path(__file__).parent.resolve()

REPOSITORY_ROOT = ROOT_DIR.parent
ROOT_DIR_PATH_STR = ROOT_DIR.absolute().as_posix()

GIT_DIR = REPOSITORY_ROOT / "tools" / "PortableGit" / "cmd"
GIT_DIR_STR = GIT_DIR.absolute().as_posix()

env["GIT_PYTHON_GIT_EXECUTABLE"] = (GIT_DIR / "git.exe").resolve(True).absolute().as_posix()
env["QT_FATAL_WARNINGS"] = "1"

path.extend([GIT_DIR_STR, ROOT_DIR_PATH_STR])

from loguru import logger
from PySide6.QtWidgets import QApplication

from core.concatenator import VideoConcatenator
from core.database import FormatRegistry, MetadataRegistry, Registry, VideoRegistry
from core.meta import VideoMetaProcessor
from core.settings import settings
from core.utils import parse_args, startup
from ui.i18n import I18n, get_windows_ui_language
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

    registry = Registry(
        settings.db.path,
        VideoRegistry,
        MetadataRegistry,
        FormatRegistry,
    )
    registry.init()

    meta_processor = VideoMetaProcessor(
        settings.ffprobe,
        getattr(
            registry,
            VideoRegistry.__table_name__,
        ),
    )
    video_concatenator = VideoConcatenator(
        settings.tmp_dir / "concat",
        settings.ffmpeg,
        settings.source_list_filename,
        settings.default_encoding,
        settings.ignore,
    )
    updater = GitUpdater(
        repo_path=REPOSITORY_ROOT,
        github_owner=settings.origin.owner,
        github_repo=settings.origin.repo,
        portable_git_base_dir=settings.tools.portable_git_base_dir,
        updater_tmp_dir=settings.updates.updater_dir,
        tools_tmp_dir=settings.updates.tools_dir,
    )
    i18n = I18n(
        get_windows_ui_language(settings.i18n.default_locale),
        settings.i18n.locales_dir,
    )

    app = QApplication(argv)

    window = MainWindow(
        settings.ffmpeg,
        settings.media.icons.main_icon_path,
        settings.media.icons.origin_icon_path,
        i18n,
        settings.app_info,
        updater,
        video_concatenator,
        meta_processor,
        registry,
        log_level="DEBUG" if args.verbose else "INFO",
    )
    window.show()

    exit_code = app.exec()

    if exit_code != 0:
        logger.error("Application exited with code {d}", exit_code)
    else:
        logger.info("Application exited successfully")

    registry.close()
    rmtree(settings.tmp_dir)

    exit(exit_code)


if __name__ == "__main__":
    main()
