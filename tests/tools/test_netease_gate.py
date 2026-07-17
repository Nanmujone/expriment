from __future__ import annotations

import json

import pytest

from tools.feasibility.netease_gate import (
    MAX_PLAYLIST_TRACKS,
    _safe_headers,
    classify_error_signal,
    parse_content_range,
    summarize_lyrics_payload,
    summarize_playlist_html,
    summarize_range_headers,
)


def _track(song_id: int, *, complete: bool = True) -> dict[str, object]:
    if not complete:
        return {"id": song_id, "name": f"song-{song_id}"}
    return {
        "id": song_id,
        "name": f"song-{song_id}",
        "dt": 180_000,
        "ar": [{"id": song_id + 10, "name": "artist"}],
        "al": {"name": "album", "picUrl": "https://example.invalid/cover.jpg"},
    }


def test_safe_headers_reject_cookie_and_authorization() -> None:
    with pytest.raises(ValueError, match="Forbidden request headers"):
        _safe_headers({"Cookie": "secret"})
    with pytest.raises(ValueError, match="Forbidden request headers"):
        _safe_headers({"Authorization": "secret"})
    assert "Cookie" not in _safe_headers()


def test_playlist_parser_limits_to_500_and_reports_completeness() -> None:
    tracks = [_track(song_id) for song_id in range(1, 502)]
    document = (
        '<meta property="og:title" content="public playlist">'
        '<meta property="og:image" content="https://example.invalid/cover.jpg">'
        f'<textarea id="song-list-pre-data">{json.dumps(tracks)}</textarea>'
    )

    summary = summarize_playlist_html(
        document,
        page_status=200,
        page_content_type="text/html",
        detail_status=200,
        detail_payload={"code": 200},
        sample_size=3,
    )

    assert summary.track_count_observed == 501
    assert summary.track_count_used == MAX_PLAYLIST_TRACKS
    assert summary.complete_track_metadata_count == MAX_PLAYLIST_TRACKS
    assert summary.test_song_ids == [1, 2, 3]
    assert summary.page_title_present is True
    assert summary.page_cover_present is True


def test_playlist_parser_falls_back_to_detail_payload() -> None:
    summary = summarize_playlist_html(
        "<title>public playlist</title>",
        page_status=200,
        page_content_type="text/html",
        detail_status=200,
        detail_payload={"code": 200, "playlist": {"tracks": [_track(42)]}},
        sample_size=5,
    )

    assert summary.track_count_used == 1
    assert summary.complete_track_metadata_count == 1
    assert summary.test_song_ids == [42]
    assert summary.detail_has_playlist is True


def test_playlist_parser_accepts_object_wrapped_predata() -> None:
    wrapped = {"tracks": [_track(7), _track(8)]}
    summary = summarize_playlist_html(
        f'<textarea id="song-list-pre-data">{json.dumps(wrapped)}</textarea>',
        page_status=200,
        page_content_type="text/html",
        detail_status=200,
        detail_payload={"code": 200},
        sample_size=5,
    )

    assert summary.predata_type == "dict"
    assert summary.predata_top_level_keys == ["tracks"]
    assert summary.test_song_ids == [7, 8]


def test_playlist_parser_extracts_only_ids_from_html_predata() -> None:
    predata = (
        '<li><a href="song?id=11">first title</a></li>'
        '<li><a href="/song?id=12">second title</a></li>'
        '<li><a href="/song?id=11">duplicate title</a></li>'
    )
    summary = summarize_playlist_html(
        f'<textarea id="song-list-pre-data">{predata}</textarea>',
        page_status=200,
        page_content_type="text/html",
        detail_status=200,
        detail_payload={"code": 20001},
        sample_size=5,
    )

    assert summary.track_count_observed == 2
    assert summary.complete_track_metadata_count == 0
    assert summary.test_song_ids == [11, 12]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("bytes 0-0/100", (0, 0, 100)),
        ("bytes 8192-8192/*", (8192, 8192, None)),
        ("bytes 2-1/100", None),
        ("bytes 100-100/100", None),
        ("not-a-range", None),
        (None, None),
    ],
)
def test_content_range_parser(
    value: str | None, expected: tuple[int, int, int | None] | None
) -> None:
    assert parse_content_range(value) == expected


def test_range_summary_proves_requested_seek_without_reading_body() -> None:
    summary = summarize_range_headers(
        status=206,
        headers={
            "content-range": "bytes 8192-8192/20000",
            "accept-ranges": "bytes",
            "content-type": "audio/mpeg",
        },
        requested_start=8192,
    )

    assert summary.content_range_valid is True
    assert summary.reported_start == 8192
    assert summary.content_type_family == "audio/mpeg"


def test_lyrics_summary_never_returns_lyric_text() -> None:
    original = "[00:01.00]first line\n[00:02.00]second line"
    translated = "[00:01.00]第一行"
    word_timed = "[1000,500](1000,200,0)first (1200,300,0)line"
    summary = summarize_lyrics_payload(
        song_id=99,
        status=200,
        payload={
            "code": 200,
            "lrc": {"lyric": original},
            "tlyric": {"lyric": translated},
            "yrc": {"lyric": word_timed},
        },
    )

    assert summary.original_line_count == 2
    assert summary.timestamped_line_count == 2
    assert summary.translated_line_count == 1
    assert summary.word_timeline_present is True
    assert summary.word_timed_entry_count == 2
    assert original not in repr(summary)
    assert translated not in repr(summary)
    assert word_timed not in repr(summary)


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"signal": "no_copyright"}, "copyright"),
        ({"signal": "geo_blocked"}, "region"),
        ({"signal": "vip_required"}, "membership"),
        ({"exception_name": "ConnectError"}, "network"),
        ({"exception_name": "ReadTimeout"}, "timeout"),
        ({"status_code": 503}, "interface"),
        ({"signal": "invalid_schema"}, "interface"),
        ({"status_code": 200}, None),
    ],
)
def test_error_classification_is_explicit_and_stable(
    kwargs: dict[str, object], expected: str | None
) -> None:
    assert classify_error_signal(**kwargs) == expected  # type: ignore[arg-type]
