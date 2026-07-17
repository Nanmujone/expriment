from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError


@dataclass(frozen=True, slots=True)
class AIConfig:
    endpoint: str
    model: str
    timeout_seconds: float = 60.0
    provider: str = "openai"

    def __post_init__(self) -> None:
        parsed = urlsplit(self.endpoint)
        if parsed.username or parsed.password:
            raise ValueError("AI 地址不得包含凭据")
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("AI 地址无效")
        if parsed.scheme != "https" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("非本机 AI 地址必须使用 HTTPS")
        if not self.model.strip():
            raise ValueError("AI 模型不能为空")
        if not 1 <= self.timeout_seconds <= 300:
            raise ValueError("AI 超时必须在 1 到 300 秒之间")
        if self.provider not in {"openai", "deepseek"}:
            raise ValueError("不支持的 AI 服务商")


@dataclass(frozen=True, slots=True)
class SongAnalysis:
    summary_zh: str
    language_notes: tuple[str, ...]

    def to_plain_text(self) -> str:
        notes = "\n".join(f"- {note}" for note in self.language_notes)
        return f"中文概述\n{self.summary_zh}\n\n语言要点\n{notes}"


class _AnalysisPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary_zh: str
    language_notes: list[str]


class OpenAIChatClient:
    def __init__(self, config: AIConfig, http_client: httpx.Client | None = None) -> None:
        self.config = config
        self._http = http_client or httpx.Client(
            timeout=httpx.Timeout(config.timeout_seconds), follow_redirects=False
        )

    def analyze(self, lyrics: str, api_key: str) -> SongAnalysis:
        if not lyrics.strip():
            raise ValueError("没有可发送的歌词")
        if not api_key:
            raise ValueError("尚未配置 AI API 密钥")
        if len(lyrics) > 100_000:
            raise ValueError("歌词过长, 无法安全发送")

        system_prompt = (
            "你是英语歌曲学习助手。只返回 JSON, 不要添加 Markdown 代码块。"
            '输出示例: {"summary_zh":"歌曲概述",'
            '"language_notes":["短语解释"]}。'
            "用中文概述歌曲表达, 并列出简洁的英语语境、短语或语法要点。"
        )
        body: dict[str, object] = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请解析以下歌词:\n\n{lyrics}"},
            ],
        }
        if self.config.provider == "deepseek":
            body["response_format"] = {"type": "json_object"}
        else:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "song_analysis",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "summary_zh": {"type": "string"},
                            "language_notes": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["summary_zh", "language_notes"],
                        "additionalProperties": False,
                    },
                },
            }
        try:
            response = self._http.post(
                f"{self.config.endpoint.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=body,
            )
            provider_name = "DeepSeek" if self.config.provider == "deepseek" else "AI 服务"
            if response.status_code == 401:
                raise ValueError(f"{provider_name} API 密钥无效, 请在设置中重新填写")
            if response.status_code == 402:
                raise ValueError(f"{provider_name} API 余额不足, 请充值后重试")
            if response.status_code == 429:
                raise ValueError(f"{provider_name}请求过于频繁, 请稍后重试")
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            payload = _AnalysisPayload.model_validate(json.loads(content))
        except (
            httpx.HTTPError,
            KeyError,
            IndexError,
            TypeError,
            json.JSONDecodeError,
            ValidationError,
        ) as error:
            raise ValueError("AI 返回格式无效或请求失败, 请检查服务地址、模型和权限") from error
        return SongAnalysis(payload.summary_zh, tuple(payload.language_notes))
