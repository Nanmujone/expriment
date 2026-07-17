"""ORM-to-DTO boundary tests used by future domain repository adapters."""

from __future__ import annotations

from english_player.infrastructure.persistence.mapping import SongData, song_to_data
from english_player.infrastructure.persistence.models import Song


def test_song_mapping_returns_immutable_data_instead_of_orm_model() -> None:
    model = Song(
        id=7,
        provider="netease",
        provider_song_id="remote-7",
        title="Mapped",
        artist="Artist",
        album="Album",
        duration_ms=1234,
        cover_url=None,
    )

    result = song_to_data(model)

    assert result == SongData(
        id=7,
        provider="netease",
        provider_song_id="remote-7",
        title="Mapped",
        artist="Artist",
        album="Album",
        duration_ms=1234,
        cover_url=None,
    )
    assert not isinstance(result, Song)
