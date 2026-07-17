from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SavedSong:
    audio_path: str
    title: str
    lyrics_path: str | None = None


@dataclass(frozen=True, slots=True)
class SavedAISettings:
    provider: str = "deepseek"
    endpoint: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-flash"


class AppStateStore:
    """Persist non-secret first-release settings and local media references."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load_songs(self) -> tuple[SavedSong, ...]:
        values = self._read().get("songs", [])
        songs: list[SavedSong] = []
        if not isinstance(values, list):
            return ()
        for value in values:
            if not isinstance(value, dict):
                continue
            try:
                songs.append(
                    SavedSong(
                        audio_path=str(value["audio_path"]),
                        title=str(value["title"]),
                        lyrics_path=(
                            str(value["lyrics_path"]) if value.get("lyrics_path") else None
                        ),
                    )
                )
            except KeyError:
                continue
        return tuple(songs)

    def save_song(self, song: SavedSong) -> tuple[SavedSong, ...]:
        songs = list(self.load_songs())
        normalized = str(Path(song.audio_path).resolve()).casefold()
        songs = [
            existing
            for existing in songs
            if str(Path(existing.audio_path).resolve()).casefold() != normalized
        ]
        songs.append(song)
        data = self._read()
        data["songs"] = [asdict(value) for value in songs]
        self._write(data)
        return tuple(songs)

    def load_ai_settings(self) -> SavedAISettings:
        value = self._read().get("ai")
        if not isinstance(value, dict):
            return SavedAISettings()
        return SavedAISettings(
            provider=str(value.get("provider") or "deepseek"),
            endpoint=str(value.get("endpoint") or "https://api.deepseek.com"),
            model=str(value.get("model") or "deepseek-v4-flash"),
        )

    def save_ai_settings(self, settings: SavedAISettings) -> None:
        data = self._read()
        data["ai"] = asdict(settings)
        self._write(data)

    def _read(self) -> dict[str, object]:
        if not self.path.is_file():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def _write(self, data: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)
