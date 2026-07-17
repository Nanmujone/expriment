"""Persistence test fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from english_player.infrastructure.persistence.database import create_sqlite_engine
from english_player.infrastructure.persistence.models import Base


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "player.sqlite3"


@pytest.fixture
def engine(database_path: Path) -> Iterator[Engine]:
    value = create_sqlite_engine(database_path)
    Base.metadata.create_all(value)
    yield value
    value.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
