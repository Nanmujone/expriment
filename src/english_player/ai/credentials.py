from __future__ import annotations

import keyring


class CredentialStore:
    SERVICE = "english-song-learning-player"
    ACCOUNT = "ai-api-key"

    def __init__(self, provider: str = "openai") -> None:
        self.account = self.ACCOUNT if provider == "openai" else f"{self.ACCOUNT}-{provider}"

    def save(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("API 密钥不能为空")
        keyring.set_password(self.SERVICE, self.account, api_key)

    def load(self) -> str | None:
        return keyring.get_password(self.SERVICE, self.account)

    def delete(self) -> None:
        try:
            keyring.delete_password(self.SERVICE, self.account)
        except keyring.errors.PasswordDeleteError:
            return
