"""Module for encrypted."""

from __future__ import annotations

import base64
import logging
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models

logger = logging.getLogger(__name__)


class EncryptedTextField(models.TextField):
    prefix: str = "enc:v1:"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._ciphers: list[Fernet] | None = None

    def _resolve_keys(self) -> list[bytes]:
        primary = getattr(settings, "CREDENTIAL_ENCRYPTION_KEY", None) or getattr(
            settings, "SCRAPER_ENCRYPTION_KEY", None
        )
        previous = getattr(settings, "CREDENTIAL_ENCRYPTION_KEY_PREVIOUS", None) or getattr(
            settings, "SCRAPER_ENCRYPTION_KEY_PREVIOUS", None
        )
        keys: list[bytes] = []
        for k in (primary, previous):
            if not k:
                continue
            if isinstance(k, str):
                k = k.encode()
            keys.append(k)
        return keys

    def _get_ciphers(self) -> list[Fernet]:
        if self._ciphers is not None:
            return self._ciphers
        keys = self._resolve_keys()
        if not keys:
            raise RuntimeError("missing encryption key")
        self._ciphers = [Fernet(k) for k in keys]
        return self._ciphers

    def _encrypt(self, plain_text: str) -> str:
        cipher = self._get_ciphers()[0]
        token = cipher.encrypt(plain_text.encode())
        return f"{self.prefix}{base64.urlsafe_b64encode(token).decode()}"

    def _decrypt(self, encrypted_value: str) -> str:
        token_b64 = encrypted_value[len(self.prefix) :]
        token = base64.urlsafe_b64decode(token_b64.encode())
        last_error: Exception | None = None
        for cipher in self._get_ciphers():
            try:
                decrypted: bytes = cipher.decrypt(token)
                return decrypted.decode()
            except Exception as e:
                logger.exception("操作失败")
                last_error = e
                continue
        if last_error:
            raise last_error
        raise InvalidToken()

    def get_prep_value(self, value: Any) -> Any:
        plain_value = super().get_prep_value(value)
        if plain_value is None or plain_value == "":
            return plain_value
        if isinstance(plain_value, str) and plain_value.startswith(self.prefix):
            return plain_value
        if not isinstance(plain_value, str):
            plain_value = str(plain_value)
        return self._encrypt(plain_value)

    def to_python(self, value: Any) -> Any:
        if value is None or value == "":
            return value
        if not isinstance(value, str):
            value = str(value)
        if not value.startswith(self.prefix):
            return value
        try:
            return self._decrypt(value)
        except (InvalidToken, ValueError):
            if getattr(settings, "DEBUG", False):
                return value
            raise

    def from_db_value(self, value: Any, expression: Any, connection: Any) -> Any:
        return self.to_python(value)
