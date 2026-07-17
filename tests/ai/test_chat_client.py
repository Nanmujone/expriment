import json

import httpx
import pytest

from english_player.ai import AIConfig, OpenAIChatClient


def test_config_requires_https_except_loopback() -> None:
    with pytest.raises(ValueError):
        AIConfig("http://example.com/v1", "gpt-5.6-terra")
    assert AIConfig("http://127.0.0.1:8080/v1", "local-model").model == "local-model"


def test_chat_client_sends_lyrics_and_parses_strict_json() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        content = json.dumps({"summary_zh": "歌曲表达坚持", "language_notes": ["hold on 表示坚持"]})
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    client = OpenAIChatClient(
        AIConfig("https://api.example.com/v1", "gpt-5.6-terra"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = client.analyze("Hold on", "secret-test-key")

    assert result.summary_zh == "歌曲表达坚持"
    assert result.language_notes == ("hold on 表示坚持",)
    assert captured[0].url == httpx.URL("https://api.example.com/v1/chat/completions")
    assert captured[0].headers["authorization"] == "Bearer secret-test-key"
    body = json.loads(captured[0].content)
    assert body["model"] == "gpt-5.6-terra"
    assert body["messages"][0]["role"] == "developer"
    assert "Hold on" in body["messages"][1]["content"]


def test_invalid_or_missing_content_returns_safe_error() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, json={"choices": [{"message": {"content": "no"}}]})
    )
    client = OpenAIChatClient(
        AIConfig("https://api.example.com/v1", "model"),
        http_client=httpx.Client(transport=transport),
    )

    with pytest.raises(ValueError, match="AI 返回格式无效"):
        client.analyze("lyrics", "key")
