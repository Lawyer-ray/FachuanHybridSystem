"""apps/core/admin/forms/system_config_admin_form.py 单元测试。

回归背景：clean_value() 里 is_secret 恒为 None（字段声明顺序在其后），
secret 明文落库；加密逻辑已移到表单级 clean()。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet

from apps.core.admin.forms import SystemConfigAdminForm


def _form_data(*, value: str, is_secret: bool) -> dict[str, str]:
    return {
        "key": "TEST_FORM_SECRET_KEY",
        "value": value,  # pragma: allowlist secret
        "category": "general",
        "description": "",
        "is_secret": "on" if is_secret else "",  # pragma: allowlist secret
        "is_active": "on",
    }


class TestSystemConfigAdminFormClean:
    """表单级 clean() 的 secret 加密行为。"""

    @pytest.mark.django_db
    @patch("apps.core.security.secret_codec.settings")
    def test_secret_value_encrypted(self, mock_settings: MagicMock) -> None:
        """is_secret=True 时 value 应被加密为 enc:v1: 前缀密文。"""
        mock_settings.CREDENTIAL_ENCRYPTION_KEY = Fernet.generate_key().decode()
        mock_settings.SCRAPER_ENCRYPTION_KEY = None
        mock_settings.DEBUG = False

        form = SystemConfigAdminForm(data=_form_data(value="plain-secret-123", is_secret=True))
        assert form.is_valid(), form.errors
        cleaned_value = form.cleaned_data["value"]
        assert cleaned_value.startswith("enc:v1:")
        assert "plain-secret-123" not in cleaned_value

        from apps.core.security.secret_codec import SecretCodec

        assert SecretCodec().decrypt(cleaned_value) == "plain-secret-123"

    @pytest.mark.django_db
    @patch("apps.core.security.secret_codec.settings")
    def test_non_secret_value_kept_plain(self, mock_settings: MagicMock) -> None:
        """is_secret=False 时 value 应原样保留。"""
        key = Fernet.generate_key().decode()
        mock_settings.CREDENTIAL_ENCRYPTION_KEY = key
        mock_settings.SCRAPER_ENCRYPTION_KEY = None
        mock_settings.DEBUG = False

        form = SystemConfigAdminForm(data=_form_data(value="plain-value", is_secret=False))
        assert form.is_valid(), form.errors
        assert form.cleaned_data["value"] == "plain-value"
        assert form.cleaned_data["is_secret"] is False

    @pytest.mark.django_db
    @patch("apps.core.security.secret_codec.settings")
    def test_missing_encryption_key_raises_validation_error(self, mock_settings: MagicMock) -> None:
        """缺少加密密钥时保存 secret 应报 ValidationError，而非明文落库。"""
        mock_settings.CREDENTIAL_ENCRYPTION_KEY = None
        mock_settings.SCRAPER_ENCRYPTION_KEY = None
        mock_settings.DEBUG = False

        form = SystemConfigAdminForm(data=_form_data(value="plain-secret-123", is_secret=True))
        assert not form.is_valid()
        assert any("缺少敏感配置加密密钥" in str(err) for err in form.non_field_errors())


class TestSystemConfigAdminSecretEcho:
    """安全审计：secret 值不再回显明文，留空=不修改。"""

    @pytest.mark.django_db
    @patch("apps.core.security.secret_codec.settings")
    def test_edit_form_does_not_echo_secret_plaintext(self, mock_settings: MagicMock) -> None:
        """编辑既有 secret 配置：initial 不回填解密后的明文。"""
        from apps.core.models import SystemConfig
        from apps.core.security.secret_codec import SecretCodec

        mock_settings.CREDENTIAL_ENCRYPTION_KEY = Fernet.generate_key().decode()
        mock_settings.SCRAPER_ENCRYPTION_KEY = None
        mock_settings.DEBUG = False

        ciphertext = SecretCodec().encrypt("echo-secret-123")  # pragma: allowlist secret
        config = SystemConfig.objects.create(key="TEST_ECHO_SECRET", value=ciphertext, is_secret=True, is_active=True)

        form = SystemConfigAdminForm(instance=config)

        assert form.initial.get("value") == ""
        rendered = form.as_p()
        assert "echo-secret-123" not in rendered
        assert ciphertext not in rendered

    @pytest.mark.django_db
    @patch("apps.core.security.secret_codec.settings")
    def test_blank_submit_keeps_saved_ciphertext(self, mock_settings: MagicMock) -> None:
        """编辑 secret 配置留空提交 → 保留库中密文原值。"""
        from apps.core.models import SystemConfig
        from apps.core.security.secret_codec import SecretCodec

        mock_settings.CREDENTIAL_ENCRYPTION_KEY = Fernet.generate_key().decode()
        mock_settings.SCRAPER_ENCRYPTION_KEY = None
        mock_settings.DEBUG = False

        ciphertext = SecretCodec().encrypt("keep-secret-123")  # pragma: allowlist secret
        config = SystemConfig.objects.create(key="TEST_KEEP_SECRET", value=ciphertext, is_secret=True, is_active=True)

        form = SystemConfigAdminForm(data=_form_data(value="", is_secret=True), instance=config)
        assert form.is_valid(), form.errors
        assert form.cleaned_data["value"] == ciphertext
        form.save()
        config.refresh_from_db()
        assert config.value == ciphertext
        assert SecretCodec().try_decrypt(config.value) == "keep-secret-123"  # pragma: allowlist secret

    @pytest.mark.django_db
    @patch("apps.core.security.secret_codec.settings")
    def test_non_blank_submit_updates_encrypted_value(self, mock_settings: MagicMock) -> None:
        """编辑 secret 配置填新值 → 加密更新。"""
        from apps.core.models import SystemConfig
        from apps.core.security.secret_codec import SecretCodec

        mock_settings.CREDENTIAL_ENCRYPTION_KEY = Fernet.generate_key().decode()
        mock_settings.SCRAPER_ENCRYPTION_KEY = None
        mock_settings.DEBUG = False

        old_ciphertext = SecretCodec().encrypt("old-secret-123")  # pragma: allowlist secret
        config = SystemConfig.objects.create(
            key="TEST_UPDATE_SECRET", value=old_ciphertext, is_secret=True, is_active=True
        )

        form = SystemConfigAdminForm(data=_form_data(value="new-secret-456", is_secret=True), instance=config)
        assert form.is_valid(), form.errors
        assert form.cleaned_data["value"].startswith("enc:v1:")
        form.save()
        config.refresh_from_db()
        assert SecretCodec().try_decrypt(config.value) == "new-secret-456"  # pragma: allowlist secret
