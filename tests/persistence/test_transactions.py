"""Unit-of-work, write coordination, and failure classification tests."""

from __future__ import annotations

import errno
from collections.abc import Callable, Sequence

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from english_player.infrastructure.persistence.errors import PersistenceError
from english_player.infrastructure.persistence.models import Song
from english_player.infrastructure.persistence.uow import UnitOfWork
from english_player.infrastructure.persistence.writes import (
    TransactionalWriter,
    ValidatedBatchWriter,
    WriteCoordinator,
)


def test_unit_of_work_requires_explicit_commit_and_rolls_back_exceptions(
    session_factory: sessionmaker[Session],
) -> None:
    with UnitOfWork(session_factory) as uow:
        uow.session.add(Song(provider="local", provider_song_id="no-commit", title="Discard"))

    with session_factory() as session:
        assert session.scalar(select(Song).where(Song.provider_song_id == "no-commit")) is None

    with pytest.raises(RuntimeError, match="boom"):
        with UnitOfWork(session_factory) as uow:
            uow.session.add(Song(provider="local", provider_song_id="exception", title="Discard"))
            raise RuntimeError("boom")

    with session_factory() as session:
        assert session.scalar(select(Song).where(Song.provider_song_id == "exception")) is None


def test_unit_of_work_commits_and_always_closes_session(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    closed = False
    original_close = Session.close

    def tracked_close(session: Session) -> None:
        nonlocal closed
        closed = True
        original_close(session)

    monkeypatch.setattr(Session, "close", tracked_close)
    with UnitOfWork(session_factory) as uow:
        uow.session.add(Song(provider="local", provider_song_id="committed", title="Keep"))
        uow.commit()

    assert closed
    with session_factory() as session:
        assert session.scalar(select(Song).where(Song.provider_song_id == "committed")) is not None


def test_single_writer_serializes_operations() -> None:
    coordinator = WriteCoordinator()
    observed: list[str] = []

    def operation() -> str:
        observed.append("write")
        return "done"

    assert coordinator.execute(operation) == "done"
    assert observed == ["write"]


def test_sqlite_lock_is_classified_as_retryable(engine: Engine) -> None:
    second_engine = engine
    first = engine.connect()
    transaction = first.begin()
    first.execute(text("INSERT INTO song (provider, provider_song_id, title) VALUES ('x', 'one', 'One')"))
    try:
        with pytest.raises(PersistenceError) as caught:
            WriteCoordinator().execute(
                lambda: second_engine.connect().execute(
                    text(
                        "INSERT INTO song (provider, provider_song_id, title) "
                        "VALUES ('x', 'two', 'Two')"
                    )
                )
            )
        assert caught.value.code == "database_locked"
        assert caught.value.retryable is True
    finally:
        transaction.rollback()
        first.close()


def test_validation_happens_before_transaction_and_batch_is_atomic(
    session_factory: sessionmaker[Session],
) -> None:
    phases: list[str] = []

    def validate(values: Sequence[str]) -> list[str]:
        phases.append("validate")
        return [value.strip() for value in values]

    def persist(session: Session, values: Sequence[str]) -> None:
        phases.append("persist")
        session.add_all(
            Song(provider="local", provider_song_id=value, title=value) for value in values
        )

    writer = ValidatedBatchWriter(lambda: UnitOfWork(session_factory))
    writer.write([" one ", " two "], validate=validate, persist=persist)
    assert phases == ["validate", "persist"]

    with session_factory() as session:
        assert session.scalars(select(Song.provider_song_id).order_by(Song.id)).all() == ["one", "two"]


@pytest.mark.parametrize("operation", ["insert", "update", "batch"])
def test_disk_full_rolls_back_write_and_is_not_retried(
    session_factory: sessionmaker[Session], operation: str
) -> None:
    attempts = 0

    with session_factory() as session:
        existing = Song(provider="local", provider_song_id="existing", title="Original")
        session.add(existing)
        session.commit()
        existing_id = existing.id

    def fail_before_commit() -> None:
        nonlocal attempts
        attempts += 1
        raise OSError(errno.ENOSPC, "No space left on device")

    if operation == "batch":
        batch_writer = ValidatedBatchWriter(
            lambda: UnitOfWork(session_factory), before_commit=fail_before_commit
        )
        action: Callable[[], object] = lambda: batch_writer.write(
            ["new-1", "new-2"],
            validate=list,
            persist=lambda session, values: session.add_all(
                Song(provider="local", provider_song_id=value, title=value) for value in values
            ),
        )
    else:
        writer = TransactionalWriter(
            lambda: UnitOfWork(session_factory), before_commit=fail_before_commit
        )

        def write_action(session: Session) -> None:
            if operation == "insert":
                session.add(Song(provider="local", provider_song_id="new", title="New"))
            else:
                song = session.get(Song, existing_id)
                assert song is not None
                song.title = "Changed"

        action = lambda: writer.write(write_action)

    with pytest.raises(PersistenceError) as caught:
        action()
    assert caught.value.code == "disk_full"
    assert caught.value.retryable is False
    assert caught.value.cleanup_action == "open_cache_cleanup"
    assert caught.value.required_bytes is not None
    assert attempts == 1

    with session_factory() as session:
        assert session.scalar(select(Song.title).where(Song.id == existing_id)) == "Original"
        assert session.scalar(select(Song).where(Song.provider_song_id.like("new%"))) is None
