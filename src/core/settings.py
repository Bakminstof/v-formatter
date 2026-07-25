from functools import cached_property
from os import getenv
from pathlib import Path
from tempfile import gettempdir

from pydantic import BaseModel, ConfigDict, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.models import AppInfoModel
from ui.models import Lang

APP_NAME = "VFormatter"
DEFAULT_ENCODING = "utf-8"

BASE_DIR = Path(__file__).parent.parent.resolve()

LOGS_DIR = BASE_DIR.parent / "logs"
BINARIES_DIR = BASE_DIR.parent / "binaries"
MEDIA_DATA_DIR = BASE_DIR.parent / "media"
DB_DIR = BASE_DIR.parent / "db"
TOOLS_DIR = BASE_DIR.parent / "tools"

TMP_DIR = Path(gettempdir()).resolve(True) / APP_NAME
TMP_DIR.mkdir(exist_ok=True, parents=True)

XDG_DATA_HOME = getenv("XDG_DATA_HOME")

if XDG_DATA_HOME:
    LOCAL_DATA_PATH = Path(XDG_DATA_HOME)
else:
    LOCAL_DATA_PATH = Path.home() / ".local" / "share"

APP_DATA_PATH = LOCAL_DATA_PATH / APP_NAME

GITHUB_BASE_URL = "https://github.com"


class LoggingSettings(BaseModel):
    model_config = ConfigDict(validate_default=True)

    rotation: str = "10 MB"
    retention: str = "30 days"
    compression: str = "gz"

    console_format: str = "<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}"

    file_path: Path = LOGS_DIR / f"{APP_NAME}.log"

    @field_validator("file_path")
    @classmethod
    def file_path_validator(cls, v: Path) -> Path:
        if not v.parent.exists():
            v.parent.mkdir(parents=True)
        return v

    file_format: str = (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
        "{level: <8} | "
        "{name}:{function}:{line} | "
        "{message}"
    )

    encoding: str = DEFAULT_ENCODING


class DBSettings(BaseModel):
    model_config = ConfigDict(validate_default=True)

    path: Path = DB_DIR / "local.db"

    @field_validator("path")
    @classmethod
    def db_path_validator(cls, v: Path) -> Path:
        if not v.parent.exists():
            v.parent.mkdir(parents=True)

        return v


class I18nSettings(BaseModel):
    locales_dir: Path = BASE_DIR.parent / "locales"

    default_locale: Lang = Lang.ru_RU


class UpdatesSettings(BaseModel):
    fetch_interval_s: int = 600

    updater_dir: Path = APP_DATA_PATH / "updates"
    tools_dir: Path = APP_DATA_PATH / "tools"

    insecure: bool = False


class ToolsSettings(BaseModel):
    portable_git_base_dir: Path = TOOLS_DIR / "PortableGit"


class OriginSettings(BaseModel):
    @computed_field
    @cached_property
    def owner(self) -> str:
        return "Bakminstof"

    @computed_field
    @cached_property
    def repo(self) -> str:
        return "v-formatter"

    @computed_field
    @cached_property
    def feedback_url(self) -> str:
        return f"{GITHUB_BASE_URL}/{self.owner}/{self.repo}/issues/new/choose"

    @computed_field
    @cached_property
    def url(self) -> str:
        return f"{GITHUB_BASE_URL}/{self.owner}/{self.repo}"


class IconsSettings(BaseModel):
    main_icon_path: Path = MEDIA_DATA_DIR / "icons" / "icon.png"
    origin_icon_path: Path = MEDIA_DATA_DIR / "icons" / "github.png"


class MediaSettings(BaseModel):
    icons: IconsSettings = IconsSettings()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="app.",
        env_file=(f"{BASE_DIR.parent / '.env'}",),
        case_sensitive=False,
        arbitrary_types_allowed=True,
        env_nested_delimiter="__",
        env_file_encoding=DEFAULT_ENCODING,
    )

    # ======================================|Main|====================================== #
    default_encoding: str = DEFAULT_ENCODING

    source_list_filename: str = "list.txt"
    ignore: set[str] = {".gitkeep"}

    ffmpeg: Path = BINARIES_DIR / "ffmpeg.exe"
    ffprobe: Path = BINARIES_DIR / "ffprobe.exe"

    logging: LoggingSettings = LoggingSettings()
    i18n: I18nSettings = I18nSettings()
    db: DBSettings = DBSettings()
    tools: ToolsSettings = ToolsSettings()
    updates: UpdatesSettings = UpdatesSettings()
    origin: OriginSettings = OriginSettings()
    media: MediaSettings = MediaSettings()

    @computed_field
    @cached_property
    def app_info(self) -> AppInfoModel:
        return AppInfoModel(
            name=APP_NAME,
            orign_url=self.origin.url,
            feedback_url=self.origin.feedback_url,
        )

    @computed_field
    @cached_property
    def tmp_dir(self) -> Path:
        return TMP_DIR


settings = Settings()
