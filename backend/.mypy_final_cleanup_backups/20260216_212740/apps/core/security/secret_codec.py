"""Module for secret codec."""
from __future__ import annotations



import base64
from dataclasses import dataclass
from typing import cast, Any

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


@dataclass(frozen=True)
class SecretCodec:
    prefix: str = "enc:v1:"

    def _get_cipher(self) -> Fernet:
        key = getattr(settings, "CREDENTIAL_ENCRYPTION_KEY", None) or getattr(settings, "SCRAPER_ENCRYPTION_KEY", None)
        if not key:
            raise RuntimeError("missing encryption key")
        if isinstance(key, str):
            key = key.encode()
        return Fernet(key)

    def is_encrypted(self, value: str | None) -> bool:
        return bool(value) and str(value).startswith(self.prefix)

    def encrypt(self, plain_text: str) -> str:
        if plain_text.startswith(self.prefix):
            return plain_text
        token = self._get_cipher().encrypt(plain_text.encode())
        return f"{self.prefix}{base64.urlsafe_b64encode(token).decode()}"

    def decrypt(self, encrypted_value: str) -> str:
        if not encrypted_value.startswith(self.prefix):
            return encrypted_value
        token_b64 = encrypted_value[len(self.prefix) :]
        token = base64.urlsafe_b64decode(token_b64.encode())
        plain = cast(bytes, self._get_cipher().decrypt(token))
        return plain.decode()

    def try_decrypt(self, value: str) -> str:
        try:
            return self.decrypt(value)
        except (InvalidToken, ValueError):
            if getattr(settings, "DEBUG", False):
                return value
            raise
