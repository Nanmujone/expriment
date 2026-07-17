"""SQLite persistence and guarded schema migration support.

Repository adapters are intentionally absent until their owning domain modules publish
repository ports.  This package provides the SQLAlchemy mapping and transaction foundation
without defining domain interfaces in the infrastructure layer.
"""

from english_player.infrastructure.persistence.database import create_sqlite_engine
from english_player.infrastructure.persistence.models import Base
from english_player.infrastructure.persistence.uow import UnitOfWork

__all__ = ["Base", "UnitOfWork", "create_sqlite_engine"]
