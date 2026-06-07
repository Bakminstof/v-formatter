from pathlib import Path

import git
import requests
from loguru import logger
from packaging.version import Version


class GitUpdater:
    def __init__(
        self,
        repo_path: Path,
        github_owner: str,
        github_repo: str,
    ) -> None:
        self.repo_path = repo_path
        self.github_owner = github_owner
        self.github_repo = github_repo

        self.repo: git.Repo | None = None

        try:
            self.repo = git.Repo(repo_path, search_parent_directories=False)
            logger.info("Git-репозиторий обнаружен: {}", repo_path)
        except git.InvalidGitRepositoryError:
            logger.warning("Папка не является Git-репозиторием: {}", repo_path)

    def is_git_repo(self) -> bool:
        return self.repo is not None

    def get_current_version(self) -> str | None:
        if not self.is_git_repo():
            return None
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
