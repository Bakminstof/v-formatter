from pathlib import Path
from re import compile as re_compile
from shutil import rmtree
from uuid import uuid4

from loguru import logger
from pydantic import BaseModel

from core.process import ManagedProcess

type SourcePath = Path
type Index = int
type DestinationPath = Path


class VideoDestinationInfoModel(BaseModel):
    destination: DestinationPath
    files: dict[Index, Path] = {}


class VideosStructureModel(BaseModel):
    data: dict[SourcePath, VideoDestinationInfoModel] = {}


class VideoConcatenator:
    def __init__(
        self,
        tmp_dir: Path,
        ffmpeg: Path,
        source_list_filename: str,
        encoding: str,
        ignore: set[str] | None = None,
    ) -> None:
        self.tmp_dir = tmp_dir / uuid4().hex
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
        target_suffix_parts = f"({"|".join(target_suffix.split(','))})"
        index_pattern = re_compile(rf"^(\d+).*\.{target_suffix_parts}")

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
                    destination=destination / parent.name,
                    files={},
                )
            videos_structure.data[parent].files[index] = item

        return videos_structure

    def make_source_list_file(
        self,
        source: Path,
        source_files: list[Path],
    ) -> Path:
        source_list_dir = self.tmp_dir / source.name
        source_list_dir.mkdir(parents=True, exist_ok=True)
        source_list_path = source_list_dir / self.source_list_filename

        with source_list_path.open(mode="w", encoding=self.encoding) as f:
            f.writelines([f"file '{f.absolute().as_posix()}'\n" for f in source_files])

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
    ) -> tuple[int, Path]:
        result_filename = f"{source.name}{target_suffix}"
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

        res = process.run()
        rmtree(self.tmp_dir)
        return res.exit_code, result_file

    def process_directory(
        self,
        source: Path,
        source_files: dict[int, Path],
        destination: Path,
        *,
        process: ManagedProcess | None = None,
    ) -> tuple[int, Path | None]:
        if not source_files:
            return -1, None

        sorted_indices = sorted(source_files.keys())
        sorted_files = [source_files[idx] for idx in sorted_indices]
        target_suffix = sorted_files[0].suffixes[-1]

        list_file = self.make_source_list_file(source, sorted_files)
        return self.concat_files(
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
        *,
        process: ManagedProcess | None = None,
    ) -> tuple[int, Path | None]:
        if not source.is_dir():
            raise NotADirectoryError(source)

        destination.mkdir(parents=True, exist_ok=True)

        try:
            return self.process_directory(
                source,
                source_files,
                destination,
                process=process,
            )
        except KeyboardInterrupt:
            logger.warning("[User] Interrupt")
            return -1, None
