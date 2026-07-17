"""SQLAlchemy engine configuration for the local SQLite database."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlalchemy import Engine, create_engine, event


def _configure_sqlite(connection: sqlite3.Connection, _record: object) -> None:
    cursor = connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=50")
    finally:
        cursor.close()


def create_sqlite_engine(database_path: Path, *, echo: bool = False) -> Engine:
    """Create an engine with foreign keys enabled on every SQLite connection."""

    resolved = database_path.expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{resolved.as_posix()}",
        echo=echo,
        connect_args={"timeout": 0.05},
    )
    event.listen(engine, "connect", _configure_sqlite)
    return engine
