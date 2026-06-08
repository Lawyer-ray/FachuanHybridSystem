"""Tests for core security modules: secret_codec and scrub."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.security.scrub import (
    fingerprint_sha256,
    is_sensitive_key_name,
    looks_like_token,
    mask_secret,
    mask_value_for_key,
    scrub_for_storage,
    scrub_obj,
    scrub_text,
)


# ---------------------------------------------------------------------------
# scrub module
# ---------------------------------------------------------------------------


class TestMaskSecret:
    def test_short_secret(self) -> None:
        assert mask_secret("abc") == "***"

    def test_six_chars(self) -> None:
        assert mask_secret("abcdef") == "***"

    def test_long_secret(self) -> None:
        result = mask_secret("abcdefghijklmnop")
        assert result == "ab***op"

    def test_empty(self) -> None:
        assert mask_secret("") == "***"


class TestIsSensitiveKeyName:
    def test_token(self) -> None:
        assert is_sensitive_key_name("token") is True

    def test_access_token(self) -> None:
        assert is_sensitive_key_name("access_token") is True

    def test_api_key(self) -> None:
        assert is_sensitive_key_name("api_key") is True

    def test_password(self) -> None:
        assert is_sensitive_key_name("password") is True

    def test_secret(self) -> None:
        assert is_sensitive_key_name("secret") is True

    def test_camel_case(self) -> None:
        assert is_sensitive_key_name("accessToken") is True

    def test_non_sensitive(self) -> None:
        assert is_sensitive_key_name("name") is False
        assert is_sensitive_key_name("email") is False

    def test_empty(self) -> None:
        assert is_sensitive_key_name("") is False
        assert is_sensitive_key_name(None) is False  # type: ignore[arg-type]

    def test_app_secret_key(self) -> None:
        assert is_sensitive_key_name("appSecretKey") is True


class TestLooksLikeToken:
    def test_sk_prefix(self) -> None:
        assert looks_like_token("sk-abc123def456ghi") is True

    def test_long_alphanumeric(self) -> None:
        assert looks_like_token("ABCDEFGHIJKLMNOPQRSTUVWXYZ") is True

    def test_short_string(self) -> None:
        assert looks_like_token("short") is False

    def test_normal_text(self) -> None:
        assert looks_like_token("hello world this is normal text") is False


class TestMaskValueForKey:
    def test_string_value(self) -> None:
        result = mask_value_for_key("token", "my-secret-token-value")
        assert "***" in result

    def test_non_string_value(self) -> None:
        result = mask_value_for_key("token", 42)
        assert result == 42

    def test_none_value(self) -> None:
        result = mask_value_for_key("token", None)
        assert result is None


class TestFingerprintSha256:
    def test_basic(self) -> None:
        result = fingerprint_sha256("test")
        assert len(result) == 64  # sha256 hex

    def test_empty(self) -> None:
        result = fingerprint_sha256("")
        assert len(result) == 64

    def test_deterministic(self) -> None:
        assert fingerprint_sha256("test") == fingerprint_sha256("test")

    def test_different_inputs(self) -> None:
        assert fingerprint_sha256("a") != fingerprint_sha256("b")


class TestScrubText:
    def test_masks_api_key_pattern(self) -> None:
        result = scrub_text("Bearer sk-abc123def456ghi789jkl")
        assert "Bearer" in result
        assert "***" in result

    def test_masks_bearer_token(self) -> None:
        result = scrub_text("Bearer abc123def456ghi789jkl")
        assert "Bearer" in result
        assert "***" in result

    def test_masks_password(self) -> None:
        result = scrub_text("password = mysecretpassword123")
        assert "password" in result
        assert "***" in result

    def test_clean_text_unchanged(self) -> None:
        text = "This is a normal message with no secrets"
        assert scrub_text(text) == text


class TestScrubObj:
    def test_none(self) -> None:
        assert scrub_obj(None) is None

    def test_string_token(self) -> None:
        result = scrub_obj("sk-abc123def456ghi789")
        assert "***" in result

    def test_string_normal(self) -> None:
        result = scrub_obj("hello world")
        assert result == "hello world"

    def test_dict_with_sensitive_key(self) -> None:
        result = scrub_obj({"name": "test", "token": "secret-value"})
        assert result["name"] == "test"
        assert "***" in result["token"]

    def test_dict_with_nested(self) -> None:
        result = scrub_obj({"data": {"password": "secret123", "user": "admin"}})
        assert "***" in result["data"]["password"]
        assert result["data"]["user"] == "admin"

    def test_list(self) -> None:
        result = scrub_obj(["normal", "sk-abc123def456ghi789"])
        assert result[0] == "normal"
        assert "***" in result[1]

    def test_tuple(self) -> None:
        result = scrub_obj(("normal",))
        assert isinstance(result, tuple)

    def test_depth_limit(self) -> None:
        deep = {"a": {"b": {"c": {"d": {"e": {"f": {"g": "secret"}}}}}}}
        result = scrub_obj(deep)
        # At depth 6, should return as-is
        assert result is not None

    def test_non_sensitive_type(self) -> None:
        assert scrub_obj(42) == 42
        assert scrub_obj(True) is True


class TestScrubForStorage:
    def test_basic(self) -> None:
        result = scrub_for_storage({"token": "secret123", "name": "test"})
        assert "***" in result["token"]
        assert result["name"] == "test"


# ---------------------------------------------------------------------------
# secret_codec module
# ---------------------------------------------------------------------------


class TestSecretCodec:
    @patch("apps.core.security.secret_codec.settings")
    def test_is_encrypted_true(self, mock_settings: MagicMock) -> None:
        from apps.core.security.secret_codec import SecretCodec

        codec = SecretCodec()
        assert codec.is_encrypted("enc:v1:somevalue") is True

    @patch("apps.core.security.secret_codec.settings")
    def test_is_encrypted_false(self, mock_settings: MagicMock) -> None:
        from apps.core.security.secret_codec import SecretCodec

        codec = SecretCodec()
        assert codec.is_encrypted("plaintext") is False

    @patch("apps.core.security.secret_codec.settings")
    def test_is_encrypted_none(self, mock_settings: MagicMock) -> None:
        from apps.core.security.secret_codec import SecretCodec

        codec = SecretCodec()
        assert codec.is_encrypted(None) is False

    @patch("apps.core.security.secret_codec.settings")
    def test_is_encrypted_empty(self, mock_settings: MagicMock) -> None:
        from apps.core.security.secret_codec import SecretCodec

        codec = SecretCodec()
        assert codec.is_encrypted("") is False

    @patch("apps.core.security.secret_codec.settings")
    def test_encrypt_decrypt_roundtrip(self, mock_settings: MagicMock) -> None:
        from cryptography.fernet import Fernet

        from apps.core.security.secret_codec import SecretCodec

        key = Fernet.generate_key().decode()
        mock_settings.CREDENTIAL_ENCRYPTION_KEY = key
        codec = SecretCodec()
        encrypted = codec.encrypt("hello world")
        assert encrypted.startswith("enc:v1:")
        decrypted = codec.decrypt(encrypted)
        assert decrypted == "hello world"

    @patch("apps.core.security.secret_codec.settings")
    def test_encrypt_already_encrypted(self, mock_settings: MagicMock) -> None:
        from apps.core.security.secret_codec import SecretCodec

        codec = SecretCodec()
        result = codec.encrypt("enc:v1:already")
        assert result == "enc:v1:already"

    @patch("apps.core.security.secret_codec.settings")
    def test_decrypt_not_encrypted(self, mock_settings: MagicMock) -> None:
        from apps.core.security.secret_codec import SecretCodec

        codec = SecretCodec()
        result = codec.decrypt("plaintext")
        assert result == "plaintext"

    @patch("apps.core.security.secret_codec.settings")
    def test_try_decrypt_success(self, mock_settings: MagicMock) -> None:
        from cryptography.fernet import Fernet

        from apps.core.security.secret_codec import SecretCodec

        key = Fernet.generate_key().decode()
        mock_settings.CREDENTIAL_ENCRYPTION_KEY = key
        mock_settings.DEBUG = False
        codec = SecretCodec()
        encrypted = codec.encrypt("test")
        assert codec.try_decrypt(encrypted) == "test"

    @patch("apps.core.security.secret_codec.settings")
    def test_try_decrypt_invalid_token_debug(self, mock_settings: MagicMock) -> None:
        from apps.core.security.secret_codec import SecretCodec

        mock_settings.CREDENTIAL_ENCRYPTION_KEY = None
        mock_settings.SCRAPER_ENCRYPTION_KEY = "invalid-key-not-base64!!!"
        mock_settings.DEBUG = True
        codec = SecretCodec()
        # In DEBUG mode with invalid token, returns the value as-is
        result = codec.try_decrypt("enc:v1:invalidtoken")
        assert isinstance(result, str)

    @patch("apps.core.security.secret_codec.settings")
    def test_get_cipher_no_key_raises(self, mock_settings: MagicMock) -> None:
        from apps.core.security.secret_codec import SecretCodec

        mock_settings.CREDENTIAL_ENCRYPTION_KEY = None
        mock_settings.SCRAPER_ENCRYPTION_KEY = None
        codec = SecretCodec()
        with pytest.raises(RuntimeError, match="missing encryption key"):
            codec.encrypt("test")
