from functools import cached_property
from pathlib import Path
from tempfile import gettempdir

from pydantic import BaseModel, ConfigDict, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from core import version
from core.models import AppInfoModel
from ui.models import Lang

APP_NAME = "VFormatter"
DEFAULT_ENCODING = "utf-8"

BASE_DIR = Path(__file__).parent.parent.resolve()

LOGS_DIR = BASE_DIR.parent / "logs"
BINARIES_DIR = BASE_DIR.parent / "binaries"
MEDIA_DATA_DIR = BASE_DIR.parent / "media"
TOOLS_DIR = BASE_DIR.parent / "tools"
TMP_DIR = Path(gettempdir()).resolve(True) / APP_NAME
TMP_DIR.mkdir(exist_ok=True, parents=True)

LOCAL_DATA_DIR = BASE_DIR.parent / "local"
DB_DIR = LOCAL_DATA_DIR / "db"


class LoggingSettings(BaseModel):
    model_config = ConfigDict(validate_default=True)

    rotation: str = "10 MB"
    retention: str = "30 days"
    compression: str = "gz"

    console_format: str = "<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}"

    file_path: Path = LOGS_DIR / "contact.log"

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

    path: Path = DB_DIR / "registry.db"

    @field_validator("path")
    @classmethod
    def db_path_validator(cls, v: Path) -> Path:
        if not v.parent.exists():
            v.parent.mkdir(parents=True)

        return v


class I18nSettings(BaseModel):
    locales_dir: Path = BASE_DIR.parent / "locales"

    default_locale: Lang = Lang.ru_RU


class LocalSettings(BaseModel):
    meta_file_path: Path = LOCAL_DATA_DIR / "meta.json"


class UISettings(BaseModel):
    icon_path: Path = MEDIA_DATA_DIR / "icon.png"


class UpdatesSettings(BaseModel):
    updater_tmp_dir: Path = TMP_DIR / "updates"

    tools_tmp_dir: Path = TMP_DIR / "tools"


class ToolsSettings(BaseModel):
    portable_git_base_dir: Path = TOOLS_DIR / "PortableGit"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="app.",
        env_file=(f"{BASE_DIR / '.env'}",),
        case_sensitive=False,
        arbitrary_types_allowed=True,
        env_nested_delimiter="__",
        env_file_encoding=DEFAULT_ENCODING,
    )

    # ======================================|Main|====================================== #
    @computed_field
    @cached_property
    def app_info(self) -> AppInfoModel:
        return AppInfoModel(
            name=APP_NAME,
            version=version,
        )

    default_encoding: str = DEFAULT_ENCODING

    default_temp_dir: Path = TMP_DIR

    source_list_filename: str = "list.txt"
    ignore: set[str] = {".gitkeep"}

    ffmpeg: Path = BINARIES_DIR / "ffmpeg.exe"
    ffprobe: Path = BINARIES_DIR / "ffprobe.exe"

    logging: LoggingSettings = LoggingSettings()
    local: LocalSettings = LocalSettings()
    i18n: I18nSettings = I18nSettings()
    ui: UISettings = UISettings()
    db: DBSettings = DBSettings()
    tools: ToolsSettings = ToolsSettings()
    updates: UpdatesSettings = UpdatesSettings()


settings = Settings()
