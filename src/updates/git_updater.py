import sys
import time
from pathlib import Path
from re import search as re_search
from subprocess import Popen

import git
import humanize
import requests
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

        self._versions_data = VersionsInfoModel()

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

    def startup(self) -> VersionsInfoModel:
        latest_version = None

        if self.is_git_repo():
            current_version = self.get_current_version()
            all_versions = self.get_all_version_tags()
            latest_version, _ = self._get_latest_release()
        else:
            current_version = UNKNOWN_VERSION
            all_versions = [current_version]

        self._versions_data.current = current_version
        self._versions_data.latest = latest_version or UNKNOWN_VERSION
        self._versions_data.all = all_versions

        return self._versions_data

    @property
    def versions_data(self) -> VersionsInfoModel:
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
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            return data.get("tag_name"), data.get("html_url")
        except Exception as e:
            logger.error("Ошибка при запросе последнего релиза: {}", str(e))
            return None, None

    def cleanup(self) -> bool:
        logger.info("[{}] Cleanup start", self)

        start = time.monotonic()

        try:
            # ManagedProcess(
            #     f"{self}|Clean",
            #     [self.repo.git.GIT_PYTHON_GIT_EXECUTABLE, "clean", "-fd"],
            #     error_flags=(),
            # ).run()
            #
            # ManagedProcess(
            #     f"{self}|Reset",
            #     [self.repo.git.GIT_PYTHON_GIT_EXECUTABLE, "reset", "--hard"],
            #     error_flags=(),
            # ).run()

            elapsed = time.monotonic() - start

            logger.success(
                "[{}] Cleanup success at {}",
                self,
                humanize.precisedelta(elapsed),
            )

            return True
        except Exception as e:
            logger.error("[{}] Cleanup  failed: {}", self, str(e))
            return False

    def fetch(self) -> bool:
        logger.info("[{}] Fetching updates", self)

        start = time.monotonic()

        try:
            ManagedProcess(
                f"{self}|Fetch",
                [
                    self.repo.git.GIT_PYTHON_GIT_EXECUTABLE,
                    "fetch",
                    "--tags",
                    "--prune",
                    "--prune-tags",
                    "--progress",
                ],
                error_flags=(),
            ).run()

            logger.info("[{}|LFS Fetch] Starting fetch", self)

            ManagedProcess(
                f"{self}|LFS Fetch",
                [self.repo.git.GIT_PYTHON_GIT_EXECUTABLE, "lfs", "fetch"],
                error_flags=(),
            ).run()

            logger.info("[{}|LFS Fetch] Done!", self)

            elapsed = time.monotonic() - start

            logger.success(
                "[{}] Fetch updates done at {}",
                self,
                humanize.precisedelta(elapsed),
            )

            return True
        except Exception as e:
            logger.error("[{}] Fetch updates failed: {}", self, str(e))
            return False

    def prepare_update(self) -> None:
        if self._prepared:
            return

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

        elapsed = time.monotonic() - start

        logger.info(
            "[{}] Prepare update done at {}",
            self,
            humanize.precisedelta(elapsed),
        )

        self.fetch()
        self.cleanup()

        self._prepared = True

    def launch_updater(self, target_tag: str) -> None:
        git_bin = self.tools_tmp_dir / self.portable_git_base_dir.name / "bin" / "git.exe"

        args = [
            git_bin,
            "switch",
            "--progress",
            "-fqd",
            target_tag,
            "&&",
            sys.executable,
            *sys.argv,
        ]

        logger.info("[{}] Launch updater: {}", self, " ".join(map(str, args)))

        Popen(
            args,
            encoding="utf-8",
            errors="replace",
            start_new_session=True,
            cwd=self.repo_path,
            shell=True,
        )

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
