import pytest
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

from apps.core.security.secret_codec import SecretCodec


@pytest.fixture(autouse=True)
def _encryption_key(monkeypatch):
    monkeypatch.setattr(settings, "SCRAPER_ENCRYPTION_KEY", Fernet.generate_key(), raising=False)
    yield


def test_secret_codec_encrypt_decrypt_roundtrip():
    codec = SecretCodec()
    enc = codec.encrypt("hello")
    assert enc.startswith(codec.prefix)
    assert codec.decrypt(enc) == "hello"


def test_secret_codec_encrypt_is_idempotent():
    codec = SecretCodec()
    enc = codec.encrypt("hello")
    assert codec.encrypt(enc) == enc


def test_secret_codec_try_decrypt_invalid_token_raises_when_debug_false(monkeypatch):
    codec = SecretCodec()
    monkeypatch.setattr(settings, "DEBUG", False, raising=False)
    with pytest.raises((InvalidToken, ValueError)):
        codec.try_decrypt(codec.prefix + "not-base64")
