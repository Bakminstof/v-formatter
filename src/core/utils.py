from argparse import ArgumentParser
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import humanize

from core.logs import setup_logging
from core.models import ArgsModel, VideoFormat
from processes import ManagedProcess
from ui.i18n import get_windows_ui_language
from ui.models import Lang


def get_supported_formats(ffmpeg: Path) -> list[VideoFormat]:
    res = ManagedProcess(
        f"FFMpeg",
        [ffmpeg, "-formats"],
        error_flags=frozenset(),
        log_level="DEBUG",
        capture_output=True,
    ).run()

    formats_list = []

    start_parsing = False

    for line in res.stdout:
        if "---" in line:
            start_parsing = True
            continue

        if not start_parsing or not line.strip():
            continue

        flags = set(line.strip().split(maxsplit=1)[0])

        content = line[4:].strip().split(maxsplit=1)

        if content:
            fmt_name = content[0]
            description = content[1] if len(content) > 1 else ""

            formats_list.append(
                VideoFormat(
                    extension=fmt_name,
                    description=description,
                    demuxing="D" in flags,
                    muxing="E" in flags,
                    device="d" in flags,
                )
            )

    return formats_list


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
