"""Safe, read-only probe for the NetEase Cloud Music online feasibility gate.

The probe intentionally uses no login, Cookie, Authorization header, encrypted
request emulation, protected-content bypass, or alternate media source. It
prints only aggregate response facts. Lyric text, audio bytes, redirect URLs,
and response Cookie values never enter the report.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Final, Literal, cast
from urllib.parse import unquote, urljoin, urlsplit

import httpx

TARGET_PLAYLIST_URL: Final = "https://music.163.com/playlist?id=5243040566"
TARGET_PLAYLIST_ID: Final = "5243040566"
PLAYLIST_DETAIL_URL: Final = "https://music.163.com/api/playlist/detail?id=5243040566&n=500&s=0"
TERMS_URL: Final = "https://st.music.163.com/official-terms/service"
ARCHIVED_REFERENCE_URL: Final = "https://github.com/Binaryify/NeteaseCloudMusicApi"
USER_AGENT: Final = "english-player-feasibility-probe/0.1 (read-only; no-cookie)"
MAX_PLAYLIST_TRACKS: Final = 500
MAX_HTML_BYTES: Final = 2_000_000
MAX_JSON_BYTES: Final = 2_000_000

ErrorCategory = Literal[
    "copyright",
    "region",
    "membership",
    "network",
    "timeout",
    "interface",
]


@dataclass(frozen=True)
class PlaylistSummary:
    page_status: int
    page_content_type: str | None
    page_title_present: bool
    page_cover_present: bool
    predata_element_present: bool
    predata_payload_length: int
    predata_parse_error: str | None
    predata_href_count: int
    predata_song_token_count: int
    predata_type: str
    predata_top_level_keys: list[str]
    track_count_observed: int
    track_count_used: int
    complete_track_metadata_count: int
    test_song_ids: list[int]
    detail_status: int
    detail_top_level_keys: list[str]
    detail_code: int | None
    detail_has_playlist: bool


@dataclass(frozen=True)
class RangeSummary:
    requested_start: int
    status: int
    content_type_family: str | None
    accept_ranges_bytes: bool
    content_range_valid: bool
    reported_start: int | None


@dataclass(frozen=True)
class AudioSummary:
    song_id: int
    redirect_status: int
    redirect_present: bool
    redirect_target_scheme: str | None
    redirect_target_host: str | None
    first_range: RangeSummary | None
    seek_range: RangeSummary | None


@dataclass(frozen=True)
class LyricsSummary:
    song_id: int
    status: int
    top_level_keys: list[str]
    source_code: int | None
    original_line_count: int
    timestamped_line_count: int
    translated_line_count: int
    word_timeline_present: bool
    word_timed_entry_count: int


@dataclass(frozen=True)
class TermsSummary:
    status: int
    content_type: str | None
    page_title_present: bool
    unauthorized_third_party_clause_present: bool
    copyright_terms_present: bool


@dataclass(frozen=True)
class ProbeReport:
    schema_version: str
    tested_at_utc: str
    target_playlist_url: str
    target_playlist_id: str
    sent_cookie: bool
    sent_authorization: bool
    stored_audio_bytes: bool
    stored_lyric_text: bool
    playlist: PlaylistSummary | None
    audio: list[AudioSummary]
    lyrics: list[LyricsSummary]
    terms: TermsSummary | None
    probe_errors: list[dict[str, str]]
    observed_error_categories: list[ErrorCategory]
    supported_error_categories: list[ErrorCategory]
    legal_authorization_confirmed: bool
    recommended_gate_state: Literal["PARTIAL_OFFLINE"]
    stop_reason: str
    sources: list[str]


class ResponseTooLargeError(RuntimeError):
    """Raised before a response larger than the probe's safe bound is retained."""


def _safe_headers(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "identity"}
    if extra:
        headers.update(extra)
    forbidden = {name.lower() for name in headers} & {"cookie", "authorization"}
    if forbidden:
        raise ValueError(f"Forbidden request headers: {sorted(forbidden)}")
    return headers


def _bounded_get(url: str, *, maximum_bytes: int) -> httpx.Response:
    # A new client per request ensures response cookies cannot be replayed later.
    with (
        httpx.Client(
            timeout=httpx.Timeout(20.0, connect=10.0),
            follow_redirects=False,
            headers=_safe_headers(),
        ) as client,
        client.stream("GET", url) as response,
    ):
        declared = response.headers.get("Content-Length")
        if declared and declared.isdigit() and int(declared) > maximum_bytes:
            raise ResponseTooLargeError(f"Response exceeds {maximum_bytes} bytes")
        chunks: list[bytes] = []
        observed = 0
        for chunk in response.iter_bytes():
            observed += len(chunk)
            if observed > maximum_bytes:
                raise ResponseTooLargeError(f"Response exceeds {maximum_bytes} bytes")
            chunks.append(chunk)
        return httpx.Response(
            status_code=response.status_code,
            headers=response.headers,
            content=b"".join(chunks),
            request=response.request,
        )


def _as_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _as_list(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _json_object(response: httpx.Response) -> dict[str, object]:
    try:
        return _as_object(cast(object, response.json()))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _textarea_text(document: str, element_id: str) -> str | None:
    pattern = re.compile(
        rf"<textarea\b[^>]*\bid=[\"']{re.escape(element_id)}[\"'][^>]*>(.*?)</textarea>",
        flags=re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(document)
    if not match:
        return None
    return html.unescape(match.group(1)).strip()


def _textarea_json(document: str, element_id: str) -> object:
    text = _textarea_text(document, element_id)
    if text is None:
        return None
    try:
        return cast(object, json.loads(text))
    except json.JSONDecodeError:
        decoded = unquote(text)
        if decoded == text:
            return None
        try:
            return cast(object, json.loads(decoded))
        except json.JSONDecodeError:
            return None


def _meta_content_present(document: str, property_name: str) -> bool:
    patterns = (
        rf"<meta\b[^>]*(?:property|name)=[\"']{re.escape(property_name)}[\"'][^>]*content=[\"'][^\"']+[\"']",
        rf"<meta\b[^>]*content=[\"'][^\"']+[\"'][^>]*(?:property|name)=[\"']{re.escape(property_name)}[\"']",
    )
    return any(re.search(pattern, document, flags=re.IGNORECASE) for pattern in patterns)


def _track_is_complete(track: Mapping[str, object]) -> bool:
    song_id = _as_int(track.get("id"))
    name = track.get("name")
    duration = _as_int(track.get("dt")) or _as_int(track.get("duration"))
    artists = _as_list(track.get("ar")) or _as_list(track.get("artists"))
    album = _as_object(track.get("al")) or _as_object(track.get("album"))
    album_name = album.get("name")
    cover = album.get("picUrl") or album.get("blurPicUrl")
    return bool(song_id and name and duration and artists and album_name and cover)


def summarize_playlist_html(
    document: str,
    *,
    page_status: int,
    page_content_type: str | None,
    detail_status: int,
    detail_payload: Mapping[str, object],
    sample_size: int,
) -> PlaylistSummary:
    predata_text = _textarea_text(document, "song-list-pre-data")
    tracks_value = _textarea_json(document, "song-list-pre-data")
    predata_error: str | None = None
    if predata_text is not None and tracks_value is None:
        try:
            json.loads(unquote(predata_text))
        except json.JSONDecodeError as exc:
            predata_error = f"{exc.msg}; line={exc.lineno}; column={exc.colno}"
    predata = _as_object(tracks_value)
    track_items = (
        _as_list(tracks_value) or _as_list(predata.get("tracks")) or _as_list(predata.get("songs"))
    )
    tracks = [_as_object(item) for item in track_items]

    if not tracks:
        seen_ids: set[int] = set()
        for matched_id in re.findall(r"(?:/)?song\?id=(\d+)", document):
            song_id = int(matched_id)
            if song_id not in seen_ids:
                tracks.append({"id": song_id})
                seen_ids.add(song_id)

    if not tracks:
        playlist = _as_object(detail_payload.get("playlist"))
        tracks = [_as_object(item) for item in _as_list(playlist.get("tracks"))]

    observed = len(tracks)
    limited = tracks[:MAX_PLAYLIST_TRACKS]
    song_ids: list[int] = []
    for track in limited:
        parsed_song_id = _as_int(track.get("id"))
        if parsed_song_id is not None:
            song_ids.append(parsed_song_id)
    return PlaylistSummary(
        page_status=page_status,
        page_content_type=page_content_type,
        page_title_present=_meta_content_present(document, "og:title")
        or bool(re.search(r"<title>\s*[^<]+\s*</title>", document, flags=re.IGNORECASE)),
        page_cover_present=_meta_content_present(document, "og:image"),
        predata_element_present=predata_text is not None,
        predata_payload_length=len(predata_text) if predata_text is not None else 0,
        predata_parse_error=predata_error,
        predata_href_count=len(re.findall(r"\bhref=", predata_text or "", flags=re.IGNORECASE)),
        predata_song_token_count=len(re.findall(r"song", predata_text or "", flags=re.IGNORECASE)),
        predata_type=type(tracks_value).__name__,
        predata_top_level_keys=sorted(predata),
        track_count_observed=observed,
        track_count_used=len(limited),
        complete_track_metadata_count=sum(_track_is_complete(track) for track in limited),
        test_song_ids=song_ids[:sample_size],
        detail_status=detail_status,
        detail_top_level_keys=sorted(detail_payload),
        detail_code=_as_int(detail_payload.get("code")),
        detail_has_playlist=bool(_as_object(detail_payload.get("playlist"))),
    )


def parse_content_range(value: str | None) -> tuple[int, int, int | None] | None:
    if not value:
        return None
    match = re.fullmatch(r"bytes\s+(\d+)-(\d+)/(\d+|\*)", value.strip())
    if not match:
        return None
    start = int(match.group(1))
    end = int(match.group(2))
    total = None if match.group(3) == "*" else int(match.group(3))
    if end < start or (total is not None and end >= total):
        return None
    return start, end, total


def summarize_range_headers(
    *, status: int, headers: Mapping[str, str], requested_start: int
) -> RangeSummary:
    parsed = parse_content_range(headers.get("content-range"))
    content_type = headers.get("content-type")
    family = content_type.split(";", maxsplit=1)[0] if content_type else None
    return RangeSummary(
        requested_start=requested_start,
        status=status,
        content_type_family=family,
        accept_ranges_bytes=headers.get("accept-ranges", "").lower() == "bytes",
        content_range_valid=parsed is not None and parsed[0] == requested_start,
        reported_start=parsed[0] if parsed else None,
    )


def _stream_headers_only(url: str, *, requested_start: int) -> RangeSummary:
    # Do not iterate the body. Closing the stream after headers prevents the probe
    # from becoming an audio downloader while still validating HTTP Range/seek.
    headers = _safe_headers({"Range": f"bytes={requested_start}-{requested_start}"})
    with (
        httpx.Client(
            timeout=httpx.Timeout(20.0, connect=10.0),
            follow_redirects=False,
            headers=headers,
        ) as client,
        client.stream("GET", url) as response,
    ):
        return summarize_range_headers(
            status=response.status_code,
            headers=response.headers,
            requested_start=requested_start,
        )


def _audio_redirect(song_id: int) -> tuple[int, str | None]:
    outer_url = f"https://music.163.com/song/media/outer/url?id={song_id}.mp3"
    with (
        httpx.Client(
            timeout=httpx.Timeout(20.0, connect=10.0),
            follow_redirects=False,
            headers=_safe_headers({"Range": "bytes=0-0"}),
        ) as client,
        client.stream("GET", outer_url) as response,
    ):
        location = response.headers.get("Location")
        return response.status_code, urljoin(outer_url, location) if location else None


def probe_audio(song_id: int) -> AudioSummary:
    redirect_status, target = _audio_redirect(song_id)
    if target is None:
        return AudioSummary(song_id, redirect_status, False, None, None, None, None)
    parsed = urlsplit(target)
    if parsed.username or parsed.password or parsed.scheme != "https" or not parsed.hostname:
        return AudioSummary(
            song_id,
            redirect_status,
            True,
            parsed.scheme or None,
            parsed.hostname,
            None,
            None,
        )
    return AudioSummary(
        song_id=song_id,
        redirect_status=redirect_status,
        redirect_present=True,
        redirect_target_scheme=parsed.scheme,
        redirect_target_host=parsed.hostname,
        first_range=_stream_headers_only(target, requested_start=0),
        seek_range=_stream_headers_only(target, requested_start=8192),
    )


def _lyric_text(payload: Mapping[str, object], key: str) -> str:
    section = _as_object(payload.get(key))
    value = section.get("lyric")
    return value if isinstance(value, str) else ""


def summarize_lyrics_payload(
    *, song_id: int, status: int, payload: Mapping[str, object]
) -> LyricsSummary:
    original = _lyric_text(payload, "lrc")
    translated = _lyric_text(payload, "tlyric")
    word_text = _lyric_text(payload, "yrc") or _lyric_text(payload, "klyric")
    original_lines = [line for line in original.splitlines() if line.strip()]
    translated_lines = [line for line in translated.splitlines() if line.strip()]
    timestamp = re.compile(r"\[\d{1,3}:\d{1,2}(?:[.:]\d{1,3})?]")
    word_token = re.compile(r"\(\d+,\d+(?:,\d+)?\)")
    word_entries = word_token.findall(word_text)
    return LyricsSummary(
        song_id=song_id,
        status=status,
        top_level_keys=sorted(payload),
        source_code=_as_int(payload.get("code")),
        original_line_count=len(original_lines),
        timestamped_line_count=sum(bool(timestamp.search(line)) for line in original_lines),
        translated_line_count=len(translated_lines),
        word_timeline_present=bool(word_entries),
        word_timed_entry_count=len(word_entries),
    )


def probe_lyrics(song_id: int) -> LyricsSummary:
    url = f"https://music.163.com/api/song/lyric?id={song_id}&lv=-1&kv=-1&tv=-1"
    response = _bounded_get(url, maximum_bytes=MAX_JSON_BYTES)
    return summarize_lyrics_payload(
        song_id=song_id,
        status=response.status_code,
        payload=_json_object(response),
    )


def classify_error_signal(
    *,
    signal: str | None = None,
    status_code: int | None = None,
    exception_name: str | None = None,
) -> ErrorCategory | None:
    normalized = signal.lower().strip() if signal else ""
    explicit: dict[str, ErrorCategory] = {
        "copyright": "copyright",
        "no_copyright": "copyright",
        "license_restricted": "copyright",
        "region": "region",
        "geo_blocked": "region",
        "membership": "membership",
        "vip_required": "membership",
        "fee_required": "membership",
    }
    if normalized in explicit:
        return explicit[normalized]
    if exception_name:
        lowered = exception_name.lower()
        if "timeout" in lowered:
            return "timeout"
        if any(token in lowered for token in ("connect", "network", "dns", "socket")):
            return "network"
    if status_code is not None and (status_code >= 400 or status_code < 200):
        return "interface"
    if normalized in {"invalid_json", "invalid_schema", "missing_required_field"}:
        return "interface"
    return None


def _probe_playlist(sample_size: int) -> PlaylistSummary:
    page = _bounded_get(TARGET_PLAYLIST_URL, maximum_bytes=MAX_HTML_BYTES)
    detail = _bounded_get(PLAYLIST_DETAIL_URL, maximum_bytes=MAX_JSON_BYTES)
    return summarize_playlist_html(
        page.text,
        page_status=page.status_code,
        page_content_type=page.headers.get("Content-Type"),
        detail_status=detail.status_code,
        detail_payload=_json_object(detail),
        sample_size=sample_size,
    )


def _probe_terms() -> TermsSummary:
    response = _bounded_get(TERMS_URL, maximum_bytes=MAX_HTML_BYTES)
    compact_text = re.sub(r"\s+", "", response.text)
    return TermsSummary(
        status=response.status_code,
        content_type=response.headers.get("Content-Type"),
        page_title_present=bool(
            re.search(r"<title>\s*[^<]+\s*</title>", response.text, flags=re.IGNORECASE)
        ),
        unauthorized_third_party_clause_present=(
            "非网易公司开发、授权或认可的第三方兼容软件" in compact_text
        ),
        copyright_terms_present="版权" in compact_text or "著作权" in compact_text,
    )


def run_probe(*, sample_size: int) -> ProbeReport:
    playlist: PlaylistSummary | None = None
    audio: list[AudioSummary] = []
    lyrics: list[LyricsSummary] = []
    terms: TermsSummary | None = None
    errors: list[dict[str, str]] = []
    observed_categories: set[ErrorCategory] = set()

    try:
        playlist = _probe_playlist(sample_size)
        if playlist.detail_code != 200 or not playlist.detail_has_playlist:
            observed_categories.add("interface")
            errors.append(
                {
                    "stage": "playlist_detail",
                    "category": "interface",
                    "type": f"upstream_code_{playlist.detail_code}",
                }
            )
    except (httpx.HTTPError, ResponseTooLargeError) as exc:
        category = classify_error_signal(exception_name=type(exc).__name__) or "interface"
        observed_categories.add(category)
        errors.append({"stage": "playlist", "category": category, "type": type(exc).__name__})

    song_ids = playlist.test_song_ids if playlist else []
    for song_id in song_ids[:2]:
        try:
            audio.append(probe_audio(song_id))
        except (httpx.HTTPError, ResponseTooLargeError) as exc:
            category = classify_error_signal(exception_name=type(exc).__name__) or "interface"
            observed_categories.add(category)
            errors.append({"stage": "audio", "category": category, "type": type(exc).__name__})

    for song_id in song_ids:
        try:
            lyrics.append(probe_lyrics(song_id))
        except (httpx.HTTPError, ResponseTooLargeError) as exc:
            category = classify_error_signal(exception_name=type(exc).__name__) or "interface"
            observed_categories.add(category)
            errors.append({"stage": "lyrics", "category": category, "type": type(exc).__name__})

    try:
        terms = _probe_terms()
    except (httpx.HTTPError, ResponseTooLargeError) as exc:
        category = classify_error_signal(exception_name=type(exc).__name__) or "interface"
        observed_categories.add(category)
        errors.append({"stage": "terms", "category": category, "type": type(exc).__name__})

    # A successful technical observation is not authorization to ship an
    # undocumented third-party API. The archived reference explicitly stopped
    # maintenance for copyright protection, and no public official API license
    # for these playback/lyrics surfaces is established by this probe.
    return ProbeReport(
        schema_version="1",
        tested_at_utc=datetime.now(UTC).isoformat(timespec="seconds"),
        target_playlist_url=TARGET_PLAYLIST_URL,
        target_playlist_id=TARGET_PLAYLIST_ID,
        sent_cookie=False,
        sent_authorization=False,
        stored_audio_bytes=False,
        stored_lyric_text=False,
        playlist=playlist,
        audio=audio,
        lyrics=lyrics,
        terms=terms,
        probe_errors=errors,
        observed_error_categories=sorted(observed_categories),
        supported_error_categories=[
            "copyright",
            "region",
            "membership",
            "network",
            "timeout",
            "interface",
        ],
        legal_authorization_confirmed=False,
        recommended_gate_state="PARTIAL_OFFLINE",
        stop_reason="no_public_official_api_authorization_and_no_stability_contract",
        sources=[TARGET_PLAYLIST_URL, TERMS_URL, ARCHIVED_REFERENCE_URL],
    )


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sample-size",
        type=int,
        default=5,
        help="Number of public-playlist songs whose lyric response structure is summarized (1-10).",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.sample_size <= 10:
        parser.error("--sample-size must be between 1 and 10")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = run_probe(sample_size=cast(int, args.sample_size))
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
