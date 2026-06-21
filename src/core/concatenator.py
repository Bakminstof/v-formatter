from __future__ import annotations

from pathlib import Path
from re import compile as re_compile

from loguru import logger
from pydantic import BaseModel

from core.process import ManagedProcess


class VideoDestinationInfoModel(BaseModel):
    destination: Path
    files: dict = {}


class VideosStructureModel(BaseModel):
    data: dict = {}


class VideoConcatenator:
    def __init__(
        self,
        ffmpeg: Path,
        source_list_filename: str,
        encoding: str,
        ignore: set[str] | None = None,
    ) -> None:
        self.ffmpeg = ffmpeg
        self.source_list_filename = source_list_filename
        self.encoding = encoding
        self.ignore = ignore or set()

    def collect_data_dirs(
        self,
        source: Path,
        destination: Path,
        target_suffix: str,
    ) -> VideosStructureModel:
        videos_structure = VideosStructureModel()
        index_pattern = re_compile(rf"^(\d+).*\.{target_suffix}")

        for item in source.rglob("**/*"):
            if item.is_dir():
                continue
            match = index_pattern.match(item.name)
            if not match or item.name in self.ignore:
                logger.debug("Skipping: {}", item.absolute().as_posix())
                continue

            index = int(match.group(1))
            parent = item.parent

            if parent not in videos_structure.data:
                videos_structure.data[parent] = VideoDestinationInfoModel(
                    destination=destination / parent.name, files={}
                )
            videos_structure.data[parent].files[index] = item

        return videos_structure

    def make_source_list_file(
        self,
        source: Path,
        source_files: list[Path],
    ) -> Path:
        source_list_path = source / self.source_list_filename
        lines = [f"file '{f.name}'\n" for f in source_files]

        with source_list_path.open(mode="w", encoding=self.encoding) as f:
            f.writelines(lines)

        logger.info(
            "Written source list file: {}",
            source_list_path.absolute().as_posix(),
        )
        return source_list_path

    def concat_files(
        self,
        source: Path,
        source_list_file: Path,
        destination: Path,
        target_suffix: str,
        *,
        process: ManagedProcess | None = None,
    ) -> Path:
        result_filename = f"{source.name}.{target_suffix}"
        result_file = destination / result_filename
        result_file.unlink(missing_ok=True)

        ffmpeg_args = [
            self.ffmpeg,
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            source_list_file,
            "-c:v",
            "copy",
            result_file,
        ]

        title = f"FFMpeg|Current: {source.name}"
        if process is None:
            process = ManagedProcess(title, ffmpeg_args)
        else:
            process.command = ffmpeg_args
            process.title = title

        process.run()
        return result_file

    def process_directory(
        self,
        source: Path,
        source_files: dict[int, Path],
        destination: Path,
        target_suffix: str,
        *,
        process: ManagedProcess | None = None,
    ) -> None:
        if not source_files:
            return

        sorted_indices = sorted(source_files.keys())
        sorted_files = [source_files[idx] for idx in sorted_indices]

        list_file = self.make_source_list_file(source, sorted_files)
        self.concat_files(
            source,
            list_file,
            destination,
            target_suffix,
            process=process,
        )

    def run(
        self,
        source: Path,
        source_files: dict[int, Path],
        destination: Path,
        target_suffix: str,
        *,
        process: ManagedProcess | None = None,
    ) -> None:
        if not source.is_dir():
            raise NotADirectoryError(source)

        destination.mkdir(parents=True, exist_ok=True)

        try:
            self.process_directory(
                source,
                source_files,
                destination,
                target_suffix,
                process=process,
            )
        except KeyboardInterrupt:
            logger.warning("[User] Interrupt")
