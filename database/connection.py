"""SQLite connection management with async support."""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from .models import Base

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, url: str):
        self.url = url
        self._engine: Engine | None = None
        self._session_maker = None

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            if self.url.startswith("sqlite"):
                db_path = self.url.replace("sqlite:///", "", 1)
                db_path = db_path.replace("sqlite://", "", 1)
                path = Path(db_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                self._engine = create_engine(
                    f"sqlite:///{path}",
                    future=True,
                    connect_args={"check_same_thread": False, "timeout": 30},
                    pool_pre_ping=True,
                    echo=False,
                )

                @event.listens_for(self._engine, "connect")
                def _configure_sqlite_connection(dbapi_connection, _connection_record):
                    cursor = dbapi_connection.cursor()
                    try:
                        cursor.execute("PRAGMA journal_mode=WAL")
                        cursor.execute("PRAGMA synchronous=NORMAL")
                        cursor.execute("PRAGMA busy_timeout=30000")
                        cursor.execute("PRAGMA foreign_keys=ON")
                    finally:
                        cursor.close()
            else:
                self._engine = create_engine(self.url, future=True)
        return self._engine

    def session_maker(self):
        if self._session_maker is None:
            self._session_maker = sessionmaker(bind=self.engine, expire_on_commit=False)
        return self._session_maker

    def init_db(self) -> None:
        Base.metadata.create_all(self.engine)
        logger.info("Database initialized at %s", self.url)

    def integrity_check(self) -> str:
        if self.engine.dialect.name != "sqlite":
            raise RuntimeError("Database integrity checks require SQLite.")
        with self.engine.connect() as connection:
            return str(connection.exec_driver_sql("PRAGMA integrity_check").scalar_one())

    def health(self) -> dict:
        try:
            insp = inspect(self.engine)
            tables = insp.get_table_names()
            return {"status": "ok", "tables": len(tables), "url": self.url}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def close(self) -> None:
        """Dispose of the engine to release file locks."""
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
            self._session_maker = None


# Module-level session maker for synchronous use in learning modules
_db_instance = None


def get_session_maker():
    """Get or create the database session maker."""
    global _db_instance
    if _db_instance is None:
        from config import DATABASE_URL
        _db_instance = Database(DATABASE_URL)
        _db_instance.init_db()
    return _db_instance.session_maker()