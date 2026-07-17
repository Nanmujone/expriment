"""Physical model constraints and query-plan tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from english_player.infrastructure.persistence.models import (
    AnalysisVersion,
    BackgroundTask,
    Favorite,
    LyricsDocument,
    PendingCleanup,
    Playlist,
    PlaylistSong,
    QuestionAnswerMessage,
    SettingReference,
    Song,
)


def _add_playlist_and_song(session: Session) -> tuple[Playlist, Song]:
    playlist = Playlist(provider="netease", provider_playlist_id="playlist-1", name="One")
    song = Song(provider="netease", provider_song_id="song-1", title="Song")
    session.add_all([playlist, song])
    session.flush()
    return playlist, song


def test_stable_remote_ids_and_membership_are_unique(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        playlist, song = _add_playlist_and_song(session)
        session.add(PlaylistSong(playlist_id=playlist.id, song_id=song.id, position=0))
        session.commit()

        session.add(Playlist(provider="netease", provider_playlist_id="playlist-1", name="Two"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        session.add(Song(provider="netease", provider_song_id="song-1", title="Duplicate"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        session.add(PlaylistSong(playlist_id=playlist.id, song_id=song.id, position=1))
        with pytest.raises(IntegrityError):
            session.commit()


def test_foreign_keys_and_current_analysis_version_are_enforced(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add(PlaylistSong(playlist_id=999, song_id=999, position=0))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        _, song = _add_playlist_and_song(session)
        lyrics = LyricsDocument(
            song_id=song.id,
            source="local_lrc",
            raw_text="Hello",
            capability="line",
            version=1,
            is_current=True,
        )
        session.add(lyrics)
        session.flush()
        session.add_all(
            [
                AnalysisVersion(
                    song_id=song.id,
                    lyrics_document_id=lyrics.id,
                    lyrics_version=1,
                    lyrics_content_hash="a" * 64,
                    model="test",
                    prompt_version="1",
                    status="complete",
                    is_current=True,
                ),
                AnalysisVersion(
                    song_id=song.id,
                    lyrics_document_id=lyrics.id,
                    lyrics_version=1,
                    lyrics_content_hash="a" * 64,
                    model="test",
                    prompt_version="2",
                    status="complete",
                    is_current=True,
                ),
            ]
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_all_first_version_entities_are_persistable(
    session_factory: sessionmaker[Session],
) -> None:
    now = datetime.now(UTC)
    with session_factory() as session:
        _, song = _add_playlist_and_song(session)
        session.add_all(
            [
                Favorite(
                    song_id=song.id,
                    phrase="hold on",
                    normalized_phrase="hold on",
                    explanation="坚持",
                    normalized_explanation="坚持",
                    source_line="Hold on",
                    created_at=now,
                ),
                QuestionAnswerMessage(
                    song_id=song.id,
                    conversation_id="conversation-1",
                    lyrics_document_id=None,
                    lyrics_content_hash=None,
                    role="user",
                    content="What does it mean?",
                    created_at=now,
                ),
                PendingCleanup(
                    target_type="song",
                    target_id=str(song.id),
                    created_at=now,
                    purge_after=now + timedelta(days=30),
                    status="pending",
                ),
                SettingReference(key="ai.default", value_type="credential_ref", value="profile-1"),
                BackgroundTask(
                    task_type="refresh_playlist",
                    status="pending",
                    trace_id="trace-1",
                ),
            ]
        )
        session.commit()
        assert session.scalar(select(func.count(Favorite.id))) == 1
        assert session.scalar(select(func.count(QuestionAnswerMessage.id))) == 1
        assert session.scalar(select(func.count(PendingCleanup.id))) == 1
        assert session.scalar(select(func.count(SettingReference.id))) == 1
        assert session.scalar(select(func.count(BackgroundTask.id))) == 1


@pytest.mark.parametrize(
    ("sql", "expected_index"),
    [
        (
            "SELECT song_id FROM playlist_song WHERE playlist_id = 1 ORDER BY position",
            "ix_playlist_song_playlist_position",
        ),
        (
            "SELECT id FROM favorite ORDER BY created_at DESC",
            "ix_favorite_created_at",
        ),
        (
            "SELECT id FROM favorite WHERE normalized_phrase = 'hold on'",
            "ix_favorite_normalized_phrase",
        ),
        (
            "SELECT id FROM pending_cleanup WHERE status = 'pending' AND purge_after <= '2100-01-01'",
            "ix_pending_cleanup_status_purge_after",
        ),
        (
            "SELECT id FROM qa_message WHERE song_id = 1 ORDER BY created_at",
            "ix_qa_message_song_created_at",
        ),
    ],
)
def test_query_plans_use_required_indexes(engine: Engine, sql: str, expected_index: str) -> None:
    with engine.connect() as connection:
        plan = connection.execute(text(f"EXPLAIN QUERY PLAN {sql}")).all()
    assert expected_index in " ".join(str(column) for row in plan for column in row)
