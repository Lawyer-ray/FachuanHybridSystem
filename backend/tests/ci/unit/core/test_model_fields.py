"""测试 core.model_fields.encrypted 模块

覆盖: EncryptedTextField 加解密逻辑
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestEncryptedTextField:
    """测试 EncryptedTextField"""

    def _make_field(self):
        from apps.core.model_fields.encrypted import EncryptedTextField

        return EncryptedTextField()

    def _make_field_with_key(self):
        """创建带有效加密密钥的字段"""
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        return self._make_field(), key

    @patch("apps.core.model_fields.encrypted.settings")
    def test_encrypt_decrypt_roundtrip(self, mock_settings: MagicMock) -> None:
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        mock_settings.CREDENTIAL_ENCRYPTION_KEY = key
        mock_settings.CREDENTIAL_ENCRYPTION_KEY_PREVIOUS = None
        mock_settings.SCRAPER_ENCRYPTION_KEY = None
        mock_settings.SCRAPER_ENCRYPTION_KEY_PREVIOUS = None
        mock_settings.DEBUG = False

        field = self._make_field()
        encrypted = field._encrypt("hello world")
        assert encrypted.startswith("enc:v1:")
        decrypted = field._decrypt(encrypted)
        assert decrypted == "hello world"

    @patch("apps.core.model_fields.encrypted.settings")
    def test_get_prep_value_none(self, mock_settings: MagicMock) -> None:
        field = self._make_field()
        assert field.get_prep_value(None) is None

    @patch("apps.core.model_fields.encrypted.settings")
    def test_get_prep_value_empty(self, mock_settings: MagicMock) -> None:
        field = self._make_field()
        assert field.get_prep_value("") == ""

    @patch("apps.core.model_fields.encrypted.settings")
    def test_get_prep_value_already_encrypted(self, mock_settings: MagicMock) -> None:
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        mock_settings.CREDENTIAL_ENCRYPTION_KEY = key
        mock_settings.CREDENTIAL_ENCRYPTION_KEY_PREVIOUS = None
        mock_settings.SCRAPER_ENCRYPTION_KEY = None
        mock_settings.SCRAPER_ENCRYPTION_KEY_PREVIOUS = None
        mock_settings.DEBUG = False

        field = self._make_field()
        encrypted = field._encrypt("test")
        # get_prep_value 对已加密值应跳过再次加密（前缀匹配）
        result = field.get_prep_value(encrypted)
        assert result.startswith("enc:v1:")

    @patch("apps.core.model_fields.encrypted.settings")
    def test_get_prep_value_plaintext(self, mock_settings: MagicMock) -> None:
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        mock_settings.CREDENTIAL_ENCRYPTION_KEY = key
        mock_settings.CREDENTIAL_ENCRYPTION_KEY_PREVIOUS = None
        mock_settings.SCRAPER_ENCRYPTION_KEY = None
        mock_settings.SCRAPER_ENCRYPTION_KEY_PREVIOUS = None
        mock_settings.DEBUG = False

        field = self._make_field()
        result = field.get_prep_value("plaintext secret")
        assert result.startswith("enc:v1:")

    @patch("apps.core.model_fields.encrypted.settings")
    def test_to_python_none(self, mock_settings: MagicMock) -> None:
        field = self._make_field()
        assert field.to_python(None) is None
        assert field.to_python("") == ""

    @patch("apps.core.model_fields.encrypted.settings")
    def test_to_python_plaintext_passthrough(self, mock_settings: MagicMock) -> None:
        field = self._make_field()
        assert field.to_python("not encrypted") == "not encrypted"

    @patch("apps.core.model_fields.encrypted.settings")
    def test_to_python_decrypt(self, mock_settings: MagicMock) -> None:
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        mock_settings.CREDENTIAL_ENCRYPTION_KEY = key
        mock_settings.CREDENTIAL_ENCRYPTION_KEY_PREVIOUS = None
        mock_settings.SCRAPER_ENCRYPTION_KEY = None
        mock_settings.SCRAPER_ENCRYPTION_KEY_PREVIOUS = None
        mock_settings.DEBUG = False

        field = self._make_field()
        encrypted = field._encrypt("secret data")
        assert field.to_python(encrypted) == "secret data"

    @patch("apps.core.model_fields.encrypted.settings")
    def test_to_python_invalid_token_debug_mode(self, mock_settings: MagicMock) -> None:
        mock_settings.CREDENTIAL_ENCRYPTION_KEY = "test"
        mock_settings.CREDENTIAL_ENCRYPTION_KEY_PREVIOUS = None
        mock_settings.SCRAPER_ENCRYPTION_KEY = None
        mock_settings.SCRAPER_ENCRYPTION_KEY_PREVIOUS = None
        mock_settings.DEBUG = True

        field = self._make_field()
        # 无效加密值在 DEBUG 模式下返回原始值
        result = field.to_python("enc:v1:invalidbase64!!!")
        assert result == "enc:v1:invalidbase64!!!"

    @patch("apps.core.model_fields.encrypted.settings")
    def test_missing_key_raises(self, mock_settings: MagicMock) -> None:
        mock_settings.CREDENTIAL_ENCRYPTION_KEY = None
        mock_settings.CREDENTIAL_ENCRYPTION_KEY_PREVIOUS = None
        mock_settings.SCRAPER_ENCRYPTION_KEY = None
        mock_settings.SCRAPER_ENCRYPTION_KEY_PREVIOUS = None
        mock_settings.DEBUG = False

        field = self._make_field()
        with pytest.raises(RuntimeError, match="missing encryption key"):
            field._encrypt("test")

    @patch("apps.core.model_fields.encrypted.settings")
    def test_key_rotation_with_previous_key(self, mock_settings: MagicMock) -> None:
        """测试密钥轮换：用旧密钥加密的数据可以用新密钥解密"""
        from cryptography.fernet import Fernet

        old_key = Fernet.generate_key()
        new_key = Fernet.generate_key()

        # 先用旧密钥加密
        old_cipher = Fernet(old_key)
        token = old_cipher.encrypt(b"rotation test")
        encrypted = f"enc:v1:{__import__('base64').urlsafe_b64encode(token).decode()}"

        # 设置新密钥为主密钥，旧密钥为 previous
        mock_settings.CREDENTIAL_ENCRYPTION_KEY = new_key.decode()
        mock_settings.CREDENTIAL_ENCRYPTION_KEY_PREVIOUS = old_key.decode()
        mock_settings.SCRAPER_ENCRYPTION_KEY = None
        mock_settings.SCRAPER_ENCRYPTION_KEY_PREVIOUS = None
        mock_settings.DEBUG = False

        field = self._make_field()
        # 应该能用旧密钥解密
        assert field.to_python(encrypted) == "rotation test"

    @patch("apps.core.model_fields.encrypted.settings")
    def test_from_db_value(self, mock_settings: MagicMock) -> None:
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        mock_settings.CREDENTIAL_ENCRYPTION_KEY = key
        mock_settings.CREDENTIAL_ENCRYPTION_KEY_PREVIOUS = None
        mock_settings.SCRAPER_ENCRYPTION_KEY = None
        mock_settings.SCRAPER_ENCRYPTION_KEY_PREVIOUS = None
        mock_settings.DEBUG = False

        field = self._make_field()
        encrypted = field._encrypt("from_db")
        assert field.from_db_value(encrypted, None, None) == "from_db"
