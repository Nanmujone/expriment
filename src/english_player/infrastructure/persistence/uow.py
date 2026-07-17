"""Explicit-commit, short-lived SQLAlchemy unit of work."""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.orm import Session, sessionmaker


class UnitOfWork:
    """Own one session and rollback unless the caller explicitly commits."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None
        self._committed = False

    @property
    def session(self) -> Session:
        if self._session is None:
            raise RuntimeError("UnitOfWork has not been entered")
        return self._session

    def __enter__(self) -> UnitOfWork:
        if self._session is not None:
            raise RuntimeError("UnitOfWork cannot be entered twice")
        self._session = self._session_factory()
        return self

    def commit(self) -> None:
        self.session.commit()
        self._committed = True

    def rollback(self) -> None:
        self.session.rollback()
        self._committed = False

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exception, traceback
        session = self.session
        try:
            if exception_type is not None or not self._committed:
                session.rollback()
        finally:
            session.close()
            self._session = None
            self._committed = False
