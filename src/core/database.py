from pathlib import Path
from sqlite3 import Connection, Row, connect
from threading import local as threading_local
from typing import Generator

from loguru import logger

from core.models import VideoMetaModel
from core.utils import local_to_utc_time


class VideoRegistry:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._local = threading_local()
        self._table_name = "videos"

    def __str__(self) -> str:
        return self.__class__.__name__

    def __repr__(self) -> str:
        return f"'{self}'"

    def _get_conn(self) -> Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = connect(self.db_path)
            conn.row_factory = Row
            conn.execute("PRAGMA journal_mode=WAL;")
            self._local.conn = conn

        return self._local.conn

    def init_db(self) -> None:
        conn = self._get_conn()
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self._table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL UNIQUE,
                mtime REAL,
                size INTEGER,
                start_datetime TEXT,
                end_datetime TEXT,
                duration REAL,
                error TEXT,
                processed_at TEXT DEFAULT (datetime('now'))
            );
        """
        )
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_videos_path ON {self._table_name}(file_path);"
        )
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_videos_start ON {self._table_name}(start_datetime);"
        )
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_videos_end ON {self._table_name}(end_datetime);"
        )
        conn.commit()
        logger.info("[{}] Database initialized: {}", self, self.db_path.as_posix())

    def close(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
            logger.info("[{}] Connection closed for thread", self)

    def get_by_path(self, file_path: Path) -> VideoMetaModel | None:
        conn = self._get_conn()
        row = conn.execute(
            f"SELECT * FROM {self._table_name} WHERE file_path = ?",
            (file_path.as_posix(),),
        ).fetchone()

        if row:
            return VideoMetaModel.model_validate(dict(row))

        return None

    def search_by_time_interval(
        self,
        folder: Path,
        start_time: str,
        end_time: str,
    ) -> Generator[VideoMetaModel, None, None]:
        folder_escaped = folder.as_posix().replace("%", "\\%").replace("_", "\\_")

        conn = self._get_conn()
        rows = conn.execute(
            f"""
            SELECT * FROM {self._table_name}
            WHERE file_path LIKE ?
              AND strftime('%H:%M', start_datetime) <= ?
              AND strftime('%H:%M', end_datetime) >= ?
            ORDER BY start_datetime
            """,
            (
                folder_escaped + "/%",
                local_to_utc_time(end_time),
                local_to_utc_time(start_time),
            ),
        )

        for row in rows.fetchall():
            yield VideoMetaModel.model_validate(dict(row))

    def upsert(self, record: VideoMetaModel) -> None:
        conn = self._get_conn()
        data = record.model_dump(mode="json")
        data["file_path"] = record.file_path.as_posix()

        conn.execute(
            f"""
            INSERT INTO {self._table_name} (
                file_path, mtime, size, start_datetime, end_datetime,
                duration, error, processed_at
            ) VALUES (
                :file_path, :mtime, :size, :start_datetime, :end_datetime,
                :duration, :error, :processed_at
            )
            ON CONFLICT(file_path) DO UPDATE SET
                mtime = excluded.mtime,
                size = excluded.size,
                start_datetime = excluded.start_datetime,
                end_datetime = excluded.end_datetime,
                duration = excluded.duration,
                error = excluded.error,
                processed_at = excluded.processed_at;
        """,
            data,
        )
        conn.commit()

        logger.info("[{}] Updated: {}", self, record.file_path.as_posix())
