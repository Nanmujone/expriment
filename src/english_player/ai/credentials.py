from __future__ import annotations

import keyring


class CredentialStore:
    SERVICE = "english-song-learning-player"
    ACCOUNT = "ai-api-key"

    def save(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("API 密钥不能为空")
        keyring.set_password(self.SERVICE, self.ACCOUNT, api_key)

    def load(self) -> str | None:
        return keyring.get_password(self.SERVICE, self.ACCOUNT)

    def delete(self) -> None:
        try:
            keyring.delete_password(self.SERVICE, self.ACCOUNT)
        except keyring.errors.PasswordDeleteError:
            return
