from argparse import ArgumentParser
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import humanize

from core.logs import setup_logging
from core.models import ArgsModel
from ui.i18n import get_windows_ui_language
from ui.models import Lang


def local_to_utc_time(local_time_str: str) -> str:
    try:
        local_tz = ZoneInfo("localtime")
    except Exception:
        now = datetime.now()
        utc_offset = now.astimezone().utcoffset()
        local_tz = timezone(utc_offset)

    hours, minutes = map(int, local_time_str.split(":"))

    today_local = datetime.now(local_tz).replace(
        hour=hours,
        minute=minutes,
        second=0,
        microsecond=0,
    )

    utc_time = today_local.astimezone(timezone.utc)
    return utc_time.strftime("%H:%M")


def parse_args() -> ArgsModel:
    parser = ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    return ArgsModel.model_validate(vars(args))


def startup(
    default_locale: Lang,
    rotation: str,
    retention: str,
    compression: str,
    file_format: str,
    encoding: str,
    console_format: str,
    verbose: bool = False,
    log_file: str | None = None,
) -> None:
    humanize.i18n.activate(get_windows_ui_language(default_locale))

    setup_logging(
        rotation,
        retention,
        compression,
        file_format,
        encoding,
        console_format,
        verbose,
        log_file,
    )
