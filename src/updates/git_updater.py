import sys
import time
from pathlib import Path
from shutil import copytree, copy2
from sys import platform
from subprocess import CREATE_NEW_PROCESS_GROUP, Popen

import git
import requests
from loguru import logger
from packaging.version import Version

from core import version


class GitUpdater:
    def __init__(
        self,
        repo_path: Path,
        github_owner: str,
        github_repo: str,
        portable_git_base_dir: Path,
        updater_tmp_dir: Path,
        tools_tmp_dir: Path,
    ) -> None:
        self.repo_path = repo_path
        self.github_owner = github_owner
        self.github_repo = github_repo

        self.repo: git.Repo | None = None

        self.portable_git_base_dir = portable_git_base_dir
        self.updater_tmp_dir = updater_tmp_dir
        self.tools_tmp_dir = tools_tmp_dir

        try:
            self.repo = git.Repo(repo_path, search_parent_directories=False)
            logger.info("Git-репозиторий обнаружен: {}", repo_path)
        except git.InvalidGitRepositoryError:
            logger.warning("Папка не является Git-репозиторием: {}", repo_path)

    def __str__(self) -> str:
        return "Updates"

    def __repr__(self) -> str:
        return f"'{self.__str__()}'"

    def is_git_repo(self) -> bool:
        return self.repo is not None

    def get_current_version(self) -> str:
        if not self.is_git_repo():
            return version
        try:
            return self.repo.git.describe("--tags", "--exact-match")
        except git.GitCommandError:
            try:
                return self.repo.head.commit.hexsha[:7]
            except Exception:
                return "unknown"

    def _get_latest_release(self) -> tuple[str | None, str | None]:
        url = (
            f"https://api.github.com/repos/"
            f"{self.github_owner}/{self.github_repo}/releases/latest"
        )
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return data.get("tag_name"), data.get("html_url")
        except Exception as e:
            logger.error("Ошибка при запросе последнего релиза: {}", e)
            return None, None

    def check_for_update(self) -> tuple[bool, str | None, str | None]:
        if not self.is_git_repo():
            logger.info("Обновление невозможно: папка не является Git-репозиторием")
            return False, None, None

        current = self.get_current_version()
        latest_tag, _ = self._get_latest_release()

        if not latest_tag:
            return False, current, None

        if current is None:
            return False, None, None

        if not self._is_valid_semver_tag(current):
            logger.info(
                "Текущая версия '{}' не является релизным тегом, "
                "предлагаем обновление до '{}'",
                current,
                latest_tag,
            )
            return True, current, latest_tag

        cur_ver = current.lstrip("v")
        latest_ver = latest_tag.lstrip("v")

        try:
            has_update = Version(latest_ver) > Version(cur_ver)
        except Exception:
            has_update = latest_tag != current

        new_version = latest_tag if has_update else None
        return has_update, current, new_version

    def prepare_update(self) -> Path:
        logger.debug("[{}] Prepare updates start", self)

        start = time.monotonic()

        copytree(self.portable_git_base_dir, self.tools_tmp_dir, dirs_exist_ok=True)

        update_entrypoint_file_name = "DoUpdate.ps1"
        update_entrypoint_file = self.updater_tmp_dir / update_entrypoint_file_name
        self.updater_tmp_dir.mkdir(exist_ok=True, parents=True)

        copy2(
            Path(__file__).parent / update_entrypoint_file_name,
            update_entrypoint_file,
            follow_symlinks=False,
        )

        logger.info(
            "[{}] Prepare update done at {:.2f}s.",
            self,
            time.monotonic() - start,
        )

        return update_entrypoint_file

    def perform_update(self) -> bool:
        has_update, _, new_tag = self.check_for_update()

        if not has_update:
            logger.info("Обновление не требуется")
            return True

        logger.info("Начинаю обновление до тега '{}'", new_tag)

        try:
            origin = self.repo.remotes.origin
            origin.fetch(tags=True)
            logger.debug("Теги получены")

            self.repo.git.checkout(f"tags/{new_tag}")
            logger.success("Репозиторий переключён на тег '{}'", new_tag)
            return True
        except Exception as e:
            logger.error("Ошибка при обновлении: {}", e)
            return False

    @staticmethod
    def _is_valid_semver_tag(tag: str) -> bool:
        tag = tag.lstrip("v")
        parts = tag.split(".")
        if len(parts) < 2:
            return False
        return all(p.isdigit() for p in parts)

    def launch_updater_and_exit(
        self,
        update_entrypoint_file: Path,
        target_tag: str,
    ) -> None:
        if platform == "win32":
            creationflags = CREATE_NEW_PROCESS_GROUP
        else:
            creationflags = 0

        git_bin = self.tools_tmp_dir / self.portable_git_base_dir.name / "bin" / "git.exe"
        git_lfs_bin = (
            self.tools_tmp_dir / self.portable_git_base_dir.name / "bin" / "git-lfs.exe"
        )

        Popen(
            [
                "powershell",
                "-executionpolicy",
                "bypass",
                "-file",
                update_entrypoint_file,
                "-RepoPath",
                self.repo_path,
                "-GitBin",
                git_bin,
                "-GitLfsBin",
                git_lfs_bin,
                "-TargetTag",
                target_tag,
                "-Python",
                sys.executable,
                "-MainScript",
                sys.argv[0],
            ],
            creationflags=creationflags,
            close_fds=True,
        )

        exit(0)
