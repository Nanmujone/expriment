"""User-data-directory safety tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from english_player.infrastructure.persistence.paths import (
    InstallDirectoryWriteError,
    prepare_user_data_paths,
)


def test_database_and_cache_are_created_outside_install_directory(tmp_path: Path) -> None:
    install = tmp_path / "install"
    data_root = tmp_path / "profile" / "data"
    cache_root = tmp_path / "profile" / "cache"
    install.mkdir()

    paths = prepare_user_data_paths(
        install_directory=install,
        data_root=data_root,
        cache_root=cache_root,
    )

    assert paths.database_path.parent == data_root.resolve()
    assert paths.cache_directory == cache_root.resolve()
    assert paths.database_path.parent.is_dir()
    assert paths.cache_directory.is_dir()


def test_install_directory_targets_are_rejected(tmp_path: Path) -> None:
    install = tmp_path / "install"
    install.mkdir()
    with pytest.raises(InstallDirectoryWriteError):
        prepare_user_data_paths(
            install_directory=install,
            data_root=install / "data",
            cache_root=tmp_path / "cache",
        )
