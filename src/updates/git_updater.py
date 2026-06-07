import sys
import time
from pathlib import Path
from shutil import copy2, copytree
from subprocess import CREATE_NEW_PROCESS_GROUP, Popen
from sys import platform

import git
import humanize
import requests
from loguru import logger
from packaging.version import InvalidVersion, Version

from core import version
from core.models import VersionsInfoModel


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

        self._versions_data: VersionsInfoModel | None = None

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

    def startup(self) -> None:
        latest_version = None

        if self.is_git_repo():
            current_version = self.get_current_version()
            all_versions = self.get_all_version_tags()
            latest_version, _ = self._get_latest_release()
        else:
            current_version = version
            all_versions = [version]

        self._versions_data = VersionsInfoModel(
            current=current_version,
            latest=latest_version or "unknown",
            all=all_versions,
        )

    @property
    def versions_data(self) -> VersionsInfoModel | None:
        return self._versions_data

    def get_all_version_tags(self) -> list[str]:
        if not self.is_git_repo():
            return []

        all_tags = [tag.name for tag in self.repo.tags]
        version_tags = []

        for tag in all_tags:
            clean = tag.lstrip("v")
            try:
                Version(clean)
                version_tags.append(tag)
            except InvalidVersion:
                continue

        return sorted(
            version_tags,
            key=lambda t: Version(t.lstrip("v")),
            reverse=True,
        )

    def get_current_version(self) -> str:
        if not self.is_git_repo():
            return version

        try:
            return self.repo.git.describe("--tags", "--exact-match")
        except git.GitCommandError:
            try:
                return self.repo.head.commit.hexsha[:7]
            except Exception:
                return version

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

        current = self._versions_data.current
        latest_tag = self._versions_data.latest

        if not latest_tag:
            return False, current, None

        if current is None:
            return False, None, None

        if not self._is_valid_semver_tag(current):
            logger.info(
                "Текущая версия '{}' не является релизным тегом, " "предлагаем обновление до '{}'",
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

        elapsed = time.monotonic() - start

        logger.info(
            "[{}] Prepare update done at {}",
            self,
            humanize.precisedelta(elapsed),
        )

        return update_entrypoint_file

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
        switch_only: bool = False,
    ) -> None:
        if platform == "win32":
            creationflags = CREATE_NEW_PROCESS_GROUP
        else:
            creationflags = 0

        git_bin = self.tools_tmp_dir / self.portable_git_base_dir.name / "bin" / "git.exe"
        git_lfs_bin = self.tools_tmp_dir / self.portable_git_base_dir.name / "bin" / "git-lfs.exe"

        args = [
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
        ]

        if switch_only:
            args.append("-SwitchOnly")

        if len(sys.argv) > 1:
            args.append("--")
            args.extend(sys.argv[1:])

        Popen(
            args,
            shell=True,
            creationflags=creationflags,
            close_fds=True,
        )

        exit(0)
