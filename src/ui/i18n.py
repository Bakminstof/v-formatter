from __future__ import annotations

import ctypes
import locale
from functools import lru_cache
from json import loads
from pathlib import Path

from ui.models import Lang


@lru_cache
def get_windows_ui_language(default: Lang) -> Lang:
    kernel32 = ctypes.windll.kernel32
    lang_id = kernel32.GetUserDefaultUILanguage()
    lang = locale.windows_locale.get(lang_id)

    if lang not in Lang:
        return default

    return Lang(lang)


class I18n:
    def __init__(
        self,
        lang: Lang,
        encoding: str,
        locales_dir: Path,
    ) -> None:
        path = locales_dir / f"{lang}.json"
        self.data: dict[str, str] = loads(path.read_text(encoding=encoding))

    def t(self, key: str) -> str:
        return self.data.get(key, key)
