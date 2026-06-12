from contextlib import suppress
from pathlib import Path
from sqlite3 import Connection, connect
from threading import Lock
from threading import local as threading_local

from loguru import logger

from core.models import MetadataModel, VideoMetaModel
from core.utils import local_to_utc_time


class TableRegistry:
    __table_name__: str

    def __init__(self, registry: "Registry") -> None:
        self.registry = registry
        self.write_lock = Lock()

    def __str__(self) -> str:
        return f"TableRegistry(table={self.__table_name__})"

    def __repr__(self) -> str:
        return f"'{self.__str__()}'"

    @property
    def con(self) -> Connection:
        return self.registry.connection

    def on_startup(self, con: Connection) -> None:
        raise NotImplementedError("Must be implemented by subclass")


class Registry:
    __initialized = False
    __closed = False

    def __init__(self, db_path: Path, *tables: type[TableRegistry]) -> None:
        self._db_path = db_path
        self._db_path_str = self._db_path.absolute().as_posix()
        self._local = threading_local()
        self._connections: set[Connection] = set()
        self.__tables = tables

    def __str__(self) -> str:
        return f"Database({self._db_path_str})"

    def __repr__(self) -> str:
        return f"'{self}'"

    @property
    def connection(self) -> Connection:
        if self.__closed:
            raise RuntimeError("Registry is closed")

        if not hasattr(self._local, "con"):
            con = connect(self._db_path, check_same_thread=True)
            self._connections.add(con)
            self._local.con = con
        return self._local.con

    def init(self) -> None:
        if self.__initialized:
            raise RuntimeError("Registry is already initialized")

        init_con = connect(self._db_path)
        init_con.execute("PRAGMA journal_mode=WAL;")

        try:
            for table_factory in self.__tables:
                table_instance = table_factory(self)
                setattr(self, table_factory.__table_name__, table_instance)
                table_instance.on_startup(init_con)
            init_con.commit()
        finally:
            init_con.close()

        self.__initialized = True
        self.__closed = False

        logger.success("[{}] Connected", self)

    def close(self) -> None:
        if self.__closed:
            raise RuntimeError("Registry is already closed")

        self.__closed = True

        for con in self._connections:
            with suppress(Exception):
                con.close()

        self._connections.clear()

        logger.info("[{}] Closed", self)


class VideoRegistry(TableRegistry):
    __table_name__ = "videos"

    def on_startup(self, con: Connection) -> None:
        con.execute(
            f"""
                CREATE TABLE IF NOT EXISTS {self.__table_name__} (
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
        con.execute(
            f"CREATE INDEX IF NOT EXISTS idx_videos_path ON {self.__table_name__}(file_path);"
        )
        con.execute(
            f"CREATE INDEX IF NOT EXISTS idx_videos_start ON {self.__table_name__}(start_datetime);"
        )
        con.execute(
            f"CREATE INDEX IF NOT EXISTS idx_videos_end ON {self.__table_name__}(end_datetime);"
        )
        logger.info("[{}] Initialized", self)

    def get_by_path(self, file_path: Path) -> VideoMetaModel | None:
        res = self.con.execute(
            f"SELECT * FROM {self.__table_name__} WHERE file_path = ?",
            (file_path.as_posix(),),
        )
        row = res.fetchone()
        if not row:
            return None
        return VideoMetaModel.from_row(row)

    def search_by_time_interval(
        self,
        folder: Path,
        start_time: str,
        end_time: str,
    ) -> list[VideoMetaModel]:
        folder_escaped = folder.as_posix().replace("%", "\\%").replace("_", "\\_")
        res = self.con.execute(
            f"""
            SELECT * FROM {self.__table_name__}
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
        return [VideoMetaModel.from_row(row) for row in res.fetchall()]

    def upsert(self, record: VideoMetaModel) -> None:
        data = record.model_dump(mode="json")
        data["file_path"] = record.file_path.as_posix()

        with self.write_lock:
            self.con.execute(
                f"""
                INSERT INTO {self.__table_name__} (
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
            self.con.commit()

        logger.info("[{}] Updated: {}", self, record.file_path.as_posix())


class MetadataRegistry(TableRegistry):
    __table_name__ = "metadata"
    __metadata_key__ = "metadata"

    def on_startup(self, con: Connection) -> None:
        con.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.__table_name__} (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        con.execute(f"CREATE INDEX IF NOT EXISTS idx_key ON {self.__table_name__}(key);")
        logger.info("[{}] Initialized", self)

    def save(self, metadata: MetadataModel) -> None:
        json_str = metadata.model_dump_json()
        with self.write_lock:
            self.con.execute(
                f"""
                INSERT INTO {self.__table_name__} (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (self.__metadata_key__, json_str),
            )
            self.con.commit()
        logger.debug("[{}] Metadata saved", self)

    def load(self) -> MetadataModel:
        res = self.con.execute(
            f"SELECT value FROM {self.__table_name__} WHERE key = ?",
            (self.__metadata_key__,),
        )
        row = res.fetchone()
        if row is None:
            logger.debug("[{}] No saved metadata, using defaults", self)
            return MetadataModel()
        try:
            return MetadataModel.model_validate_json(row[0])
        except Exception as e:
            logger.exception(
                "[{}] Failed to parse metadata JSON, falling back to defaults",
                self,
                exc_info=e,
            )
            return MetadataModel()
