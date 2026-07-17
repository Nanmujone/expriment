"""SQLAlchemy 2 physical data model for the first application schema."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Declarative metadata root."""


class Playlist(Base):
    __tablename__ = "playlist"
    __table_args__ = (
        UniqueConstraint("provider", "provider_playlist_id", name="uq_playlist_provider_remote_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_playlist_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    cover_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class Song(Base):
    __tablename__ = "song"
    __table_args__ = (
        UniqueConstraint("provider", "provider_song_id", name="uq_song_provider_remote_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_song_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    artist: Mapped[str | None] = mapped_column(String(512))
    album: Mapped[str | None] = mapped_column(String(512))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    cover_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class PlaylistSong(Base):
    __tablename__ = "playlist_song"
    __table_args__ = (
        UniqueConstraint("playlist_id", "position", name="uq_playlist_song_position"),
        Index("ix_playlist_song_playlist_position", "playlist_id", "position"),
    )

    playlist_id: Mapped[int] = mapped_column(ForeignKey("playlist.id"), primary_key=True)
    song_id: Mapped[int] = mapped_column(ForeignKey("song.id"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    availability: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)


class AudioSource(Base):
    __tablename__ = "audio_source"
    __table_args__ = (
        UniqueConstraint("song_id", "source_type", name="uq_audio_source_song_type"),
        CheckConstraint(
            "source_type IN ('local_mp3', 'local_lrc')", name="ck_audio_source_local_only"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    song_id: Mapped[int] = mapped_column(ForeignKey("song.id"), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    local_path: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(512))
    content_fingerprint: Mapped[str | None] = mapped_column(String(128))
    availability: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LyricsDocument(Base):
    __tablename__ = "lyrics_document"
    __table_args__ = (
        UniqueConstraint("song_id", "version", name="uq_lyrics_document_song_version"),
        UniqueConstraint("id", "version", name="uq_lyrics_document_id_version"),
        CheckConstraint("capability IN ('plain', 'line', 'word')", name="ck_lyrics_capability"),
        Index(
            "uq_lyrics_document_current_song",
            "song_id",
            unique=True,
            sqlite_where=text("is_current = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    song_id: Mapped[int] = mapped_column(ForeignKey("song.id"), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    capability: Mapped[str] = mapped_column(String(16), nullable=False)
    offset_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="valid", nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class LyricsLine(Base):
    __tablename__ = "lyrics_line"
    __table_args__ = (
        UniqueConstraint("lyrics_document_id", "stable_line_id", name="uq_lyrics_line_stable_id"),
        UniqueConstraint("lyrics_document_id", "position", name="uq_lyrics_line_position"),
        CheckConstraint(
            "end_ms IS NULL OR (start_ms IS NOT NULL AND end_ms >= start_ms)",
            name="ck_lyrics_line_time_order",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lyrics_document_id: Mapped[int] = mapped_column(
        ForeignKey("lyrics_document.id"), nullable=False
    )
    stable_line_id: Mapped[str] = mapped_column(String(128), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    start_ms: Mapped[int | None] = mapped_column(Integer)
    end_ms: Mapped[int | None] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class WordTiming(Base):
    __tablename__ = "word_timing"
    __table_args__ = (
        UniqueConstraint("lyrics_line_id", "position", name="uq_word_timing_position"),
        CheckConstraint("end_ms >= start_ms", name="ck_word_timing_time_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lyrics_line_id: Mapped[int] = mapped_column(ForeignKey("lyrics_line.id"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class AnalysisVersion(Base):
    __tablename__ = "analysis_version"
    __table_args__ = (
        ForeignKeyConstraint(
            ["lyrics_document_id", "lyrics_version"],
            ["lyrics_document.id", "lyrics_document.version"],
            name="fk_analysis_lyrics_version",
        ),
        CheckConstraint("status = 'complete'", name="ck_analysis_complete_only"),
        Index(
            "uq_analysis_version_current_song",
            "song_id",
            unique=True,
            sqlite_where=text("is_current = 1"),
        ),
        Index("ix_analysis_version_lyrics_version", "lyrics_document_id", "lyrics_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    song_id: Mapped[int] = mapped_column(ForeignKey("song.id"), nullable=False)
    lyrics_document_id: Mapped[int] = mapped_column(Integer, nullable=False)
    lyrics_version: Mapped[int] = mapped_column(Integer, nullable=False)
    lyrics_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class LineAnalysis(Base):
    __tablename__ = "line_analysis"
    __table_args__ = (
        UniqueConstraint("analysis_version_id", "lyrics_line_id", name="uq_line_analysis_line"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_version_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_version.id"), nullable=False
    )
    lyrics_line_id: Mapped[int] = mapped_column(ForeignKey("lyrics_line.id"), nullable=False)
    translation: Mapped[str] = mapped_column(Text, nullable=False)
    surface_meaning: Mapped[str] = mapped_column(Text, nullable=False)
    contextual_meaning: Mapped[str] = mapped_column(Text, nullable=False)
    slang_notes: Mapped[str] = mapped_column(Text, nullable=False)
    user_modified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class QuestionAnswerMessage(Base):
    __tablename__ = "qa_message"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="ck_qa_message_role"),
        CheckConstraint(
            "(lyrics_document_id IS NULL AND lyrics_content_hash IS NULL) OR "
            "(lyrics_document_id IS NOT NULL AND lyrics_content_hash IS NOT NULL)",
            name="ck_qa_lyrics_binding",
        ),
        Index("ix_qa_message_song_created_at", "song_id", "created_at"),
        Index("ix_qa_message_conversation_created_at", "conversation_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    song_id: Mapped[int] = mapped_column(ForeignKey("song.id"), nullable=False)
    conversation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    lyrics_document_id: Mapped[int | None] = mapped_column(ForeignKey("lyrics_document.id"))
    lyrics_content_hash: Mapped[str | None] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    related_line_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class Favorite(Base):
    __tablename__ = "favorite"
    __table_args__ = (
        Index("ix_favorite_created_at", "created_at"),
        Index("ix_favorite_normalized_phrase", "normalized_phrase"),
        Index("ix_favorite_normalized_explanation", "normalized_explanation"),
        Index("ix_favorite_song_created_at", "song_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    song_id: Mapped[int] = mapped_column(ForeignKey("song.id"), nullable=False)
    phrase: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_phrase: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    source_line: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class PlaybackPreference(Base):
    __tablename__ = "playback_preference"
    __table_args__ = (
        CheckConstraint(
            "source_preference IN ('online', 'local')", name="ck_playback_source_preference"
        ),
    )

    song_id: Mapped[int] = mapped_column(ForeignKey("song.id"), primary_key=True)
    lyrics_offset_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_preference: Mapped[str] = mapped_column(String(16), default="online", nullable=False)


class SettingReference(Base):
    __tablename__ = "setting_reference"
    __table_args__ = (
        CheckConstraint(
            "value_type IN ('string', 'integer', 'boolean', 'credential_ref')",
            name="ck_setting_reference_value_type",
        ),
    )

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value_type: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class BackgroundTask(Base):
    __tablename__ = "background_task"
    __table_args__ = (
        UniqueConstraint("trace_id", name="uq_background_task_trace_id"),
        Index("ix_background_task_status_created_at", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False)
    error_category: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(128))
    related_song_id: Mapped[int | None] = mapped_column(ForeignKey("song.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class PendingCleanup(Base):
    __tablename__ = "pending_cleanup"
    __table_args__ = (
        UniqueConstraint("target_type", "target_id", name="uq_pending_cleanup_target"),
        CheckConstraint(
            "status IN ('pending', 'restored', 'awaiting_purge_confirmation')",
            name="ck_pending_cleanup_status",
        ),
        Index("ix_pending_cleanup_status_purge_after", "status", "purge_after"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    purge_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    restored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    confirmation_batch: Mapped[str | None] = mapped_column(String(128))
