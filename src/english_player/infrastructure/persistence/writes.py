"""Single-writer coordination and validate-then-write transaction patterns."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from threading import Lock
from typing import TypeVar

from sqlalchemy.orm import Session

from english_player.infrastructure.persistence.errors import (
    PersistenceError,
    classify_persistence_error,
)
from english_player.infrastructure.persistence.uow import UnitOfWork

ResultT = TypeVar("ResultT")
InputT = TypeVar("InputT")
ValidatedT = TypeVar("ValidatedT")


class WriteCoordinator:
    """Serialize in-process SQLite writes and standardize expected storage errors."""

    def __init__(self) -> None:
        self._lock = Lock()

    def execute(self, operation: Callable[[], ResultT]) -> ResultT:
        with self._lock:
            try:
                return operation()
            except PersistenceError:
                raise
            except BaseException as error:
                classified = classify_persistence_error(error)
                if classified is None:
                    raise
                raise classified from error


class TransactionalWriter:
    """Execute a database-only callback in one short, explicit transaction."""

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        *,
        coordinator: WriteCoordinator | None = None,
        before_commit: Callable[[], None] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._coordinator = coordinator or WriteCoordinator()
        self._before_commit = before_commit

    def write(self, operation: Callable[[Session], ResultT]) -> ResultT:
        def transaction() -> ResultT:
            with self._uow_factory() as uow:
                result = operation(uow.session)
                if self._before_commit is not None:
                    self._before_commit()
                uow.commit()
                return result

        return self._coordinator.execute(transaction)


class ValidatedBatchWriter[InputT, ValidatedT]:
    """Validate external inputs before opening a transaction, then persist atomically."""

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        *,
        coordinator: WriteCoordinator | None = None,
        before_commit: Callable[[], None] | None = None,
    ) -> None:
        self._writer = TransactionalWriter(
            uow_factory,
            coordinator=coordinator,
            before_commit=before_commit,
        )

    def write(
        self,
        values: Sequence[InputT],
        *,
        validate: Callable[[Sequence[InputT]], Sequence[ValidatedT]],
        persist: Callable[[Session, Sequence[ValidatedT]], None],
    ) -> None:
        validated = validate(values)
        self._writer.write(lambda session: persist(session, validated))
