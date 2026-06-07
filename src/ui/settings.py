from pathlib import Path

from loguru import logger

from ui.models import LocalMetaModel


def load_local_meta(
    file_path: Path,
    *,
    encoding: str,
) -> LocalMetaModel:
    if not file_path.exists():
        logger.debug("Local meta not found, use default {}", file_path.name)

        return LocalMetaModel()

    try:
        with file_path.open("r", encoding=encoding) as f:
            data = f.read()

            logger.debug("Loaded local meta {}", file_path.name)
            return LocalMetaModel.model_validate_json(data)

    except Exception as e:
        logger.warning(
            "Local meta load failed: path={}. Exception: {}",
            file_path.absolute().as_posix(),
            str(e),
        )
        return LocalMetaModel()


def save_local_meta(
    data: LocalMetaModel,
    file_path: Path,
    *,
    encoding: str,
    indent: int = 4,
) -> None:
    if not file_path.parent.exists():
        file_path.parent.mkdir(parents=True, exist_ok=True)
        logger.debug(
            "Created local dir: {}".format(file_path.parent.absolute().as_posix())
        )

    try:
        with file_path.open("w", encoding=encoding) as f:
            f.write(data.model_dump_json(indent=indent))

            logger.debug("Saved {}", file_path.name)

    except Exception as e:
        logger.warning(
            "Local meta save failed: path={}. Exception: {}",
            file_path.absolute().as_posix(),
            str(e),
        )
