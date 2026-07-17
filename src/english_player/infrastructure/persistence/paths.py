"""Windows user data locations with installation-directory write protection."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_cache_path, user_data_path

APP_NAME = "EnglishSongLearningPlayer"
APP_AUTHOR = "Nanmujone"


class InstallDirectoryWriteError(ValueError):
    """Raised when runtime data would be written beneath the installation directory."""


@dataclass(frozen=True, slots=True)
class UserDataPaths:
    data_directory: Path
    cache_directory: Path
    database_path: Path


def _is_within(candidate: Path, parent: Path) -> bool:
    return candidate == parent or parent in candidate.parents


def prepare_user_data_paths(
    *,
    install_directory: Path,
    data_root: Path | None = None,
    cache_root: Path | None = None,
) -> UserDataPaths:
    """Resolve and create profile-owned runtime directories outside the installation."""

    install = install_directory.expanduser().resolve()
    data = (data_root or user_data_path(APP_NAME, APP_AUTHOR)).expanduser().resolve()
    cache = (cache_root or user_cache_path(APP_NAME, APP_AUTHOR)).expanduser().resolve()
    if _is_within(data, install) or _is_within(cache, install):
        raise InstallDirectoryWriteError("database and cache must be outside the installation")
    data.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    return UserDataPaths(
        data_directory=data,
        cache_directory=cache,
        database_path=data / "english_player.sqlite3",
    )


def default_user_data_paths() -> UserDataPaths:
    """Return the current user's production data locations."""

    return prepare_user_data_paths(install_directory=Path(sys.executable).resolve().parent)
