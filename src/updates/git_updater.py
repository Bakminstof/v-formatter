import sys
import time
from pathlib import Path
from re import search as re_search
from shutil import copy2
from subprocess import CREATE_NEW_PROCESS_GROUP, Popen
from sys import platform

import git
import humanize
import requests
from git import RemoteProgress
from loguru import logger
from packaging.version import InvalidVersion, Version

from core.models import UNKNOWN_VERSION, VersionsInfoModel
from core.process import ManagedProcess


class GitUpdater:
    _prepared: bool = False

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

            self.convert_origin_to_https()

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
            current_version = UNKNOWN_VERSION
            all_versions = [current_version]

        self._versions_data = VersionsInfoModel(
            current=current_version,
            latest=latest_version or UNKNOWN_VERSION,
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
            return UNKNOWN_VERSION

        try:
            return self.repo.git.describe("--tags", "--exact-match")
        except git.GitCommandError:
            try:
                return self.repo.head.commit.hexsha[:7]
            except Exception:
                return UNKNOWN_VERSION

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

    def fetch(self) -> bool:
        try:
            logger.info("[{}] Fetching updates", self)

            self.repo.remote("origin").fetch(
                tags=True,
                prune=True,
                prune_tags=True,
                progress=FetchProgress(),
            )
            self.run_lfs_with_progress()

            logger.success("[{}] Fetch updates done", self)
            return True
        except Exception as e:
            logger.error("[{}] Fetch updates failed: {}", self, str(e))
            return False

    def prepare_update(self) -> Path:
        update_entrypoint_file_name = "DoUpdate.ps1"
        update_entrypoint_file = self.updater_tmp_dir / update_entrypoint_file_name

        if self._prepared:
            return update_entrypoint_file

        logger.debug("[{}] Prepare updates start", self)

        start = time.monotonic()

        ManagedProcess(
            "Delivery Tools",
            [
                "robocopy",
                "/mir",
                self.portable_git_base_dir,
                self.tools_tmp_dir / self.portable_git_base_dir.name,
            ],
            error_flags=(),
            shell=True,
            output_log_level="DEBUG",
        ).run()

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

        self.fetch()

        self._prepared = True

        return update_entrypoint_file

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

        Popen(args, shell=True, creationflags=creationflags, close_fds=True)

        exit(0)

    def convert_origin_to_https(self) -> None:
        origin = self.repo.remote(name="origin")
        current_url = origin.url

        if current_url.startswith("git@") or "://" not in current_url:
            match = re_search(r"(?:ssh://)?git@([^:/]+)[:/](.+)$", current_url)

            if match:
                domain = match.group(1)
                path = match.group(2)
                new_url = f"https://{domain}/{path}"

                origin.set_url(new_url)

                logger.debug("[{}] origin url update to: {}", self, new_url)

    def run_lfs_with_progress(self) -> None:
        lfs_env = {"GIT_LFS_PROGRESS": "1"}

        logger.info("[{}] Starting Git LFS Fetch", self)

        proc = self.repo.git.execute(
            ["git", "lfs", "fetch"],
            as_process=True,
            env=lfs_env,
            universal_newlines=True,
        )

        for line in proc.stdout:
            logger.info("[{}|LFS Fetch] {}", self, line.strip(), end="\r")

        proc.wait()
        logger.info("[{}|LFS Fetch] Done!", self)

        logger.info("Starting Git LFS Prune")
        proc_prune = self.repo.git.execute(
            ["git", "lfs", "prune"],
            as_process=True,
            universal_newlines=True,
        )

        for line in proc_prune.stdout:
            logger.info("[{}|LFS Prune] {}", self, line.strip(), end="\r")

        proc_prune.wait()
        logger.info("[{}|LFS Prune] Done!", self)


class FetchProgress(RemoteProgress):
    def update(
        self,
        op_code: int,
        cur_count: str | float,
        max_count: str | float | None = None,
        message: str = "",
    ) -> None:
        total = max_count if max_count else "?"

        op_name = self._get_op_name(op_code)

        logger.info(f"[{op_name}] Progress: {cur_count}/{total} {message}", end="\r")

    @staticmethod
    def _get_op_name(op_code):
        if op_code & RemoteProgress.COUNTING:
            return "Counting objects"
        if op_code & RemoteProgress.COMPRESSING:
            return "Compressing objects"
        if op_code & RemoteProgress.WRITING:
            return "Writing objects"
        if op_code & RemoteProgress.RECEIVING:
            return "Receiving objects"

        return "Processing"
