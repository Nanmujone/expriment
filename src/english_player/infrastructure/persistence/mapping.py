"""Infrastructure DTO mapping primitives for future domain-owned repository ports."""

from __future__ import annotations

from dataclasses import dataclass

from english_player.infrastructure.persistence.models import Song


@dataclass(frozen=True, slots=True)
class SongData:
    """Detached song data that cannot expose SQLAlchemy session behavior upward."""

    id: int
    provider: str
    provider_song_id: str
    title: str
    artist: str | None
    album: str | None
    duration_ms: int | None
    cover_url: str | None


def song_to_data(model: Song) -> SongData:
    """Copy an ORM row into an immutable transport object."""

    return SongData(
        id=model.id,
        provider=model.provider,
        provider_song_id=model.provider_song_id,
        title=model.title,
        artist=model.artist,
        album=model.album,
        duration_ms=model.duration_ms,
        cover_url=model.cover_url,
    )
