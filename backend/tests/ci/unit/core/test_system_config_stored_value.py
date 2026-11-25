"""「已存值」展示层 + Admin 查看页。

回归背景：v27.3.0 安全审计把 secret 明文从编辑页拿掉之后，管理员**完全看不到**自己存了什么
（连存了几个 Key 都无从确认）。这里补的是「掩码常驻 + 明文按需显式查看」：

- 编辑页只渲染掩码与计数，任何时刻不含明文；
- 明文只在 `stored-value` 页的 POST 响应里出现，响应头 no-store，且写审计日志（不含明文）。
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet

from apps.core.security.secret_display import (
    SecretValueUndecryptable,
    count_segments,
    describe_stored_value,
    mask_summary,
    reveal_stored_value,
)

pytestmark = pytest.mark.django_db


LEASE_PLAIN = "sk-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1"  # pragma: allowlist secret
SECOND_PLAIN = "sk-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb2"  # pragma: allowlist secret
THIRD_PLAIN = "sk-ccccccccccccccccccccccccccccccccccc3"  # pragma: allowlist secret


@pytest.fixture()
def encryption_settings() -> Any:
    """固定一把主密钥，使加密/解密在用例内可复现。"""
    with patch("apps.core.security.secret_codec.settings") as mock_settings:
        mock_settings.CREDENTIAL_ENCRYPTION_KEY = Fernet.generate_key().decode()
        mock_settings.SCRAPER_ENCRYPTION_KEY = None
        mock_settings.DEBUG = False
        yield mock_settings


def _encrypt(plain: str) -> str:
    from apps.core.security.secret_codec import SecretCodec

    return SecretCodec().encrypt(plain)


class TestDescribeStoredValue:
    """掩码快照：不含完整明文，计数与长度要准。"""

    def test_single_secret_is_masked_with_head_and_tail(self, encryption_settings: Any) -> None:
        desc = describe_stored_value(_encrypt(LEASE_PLAIN), is_secret=True)

        assert desc.decrypt_failed is False
        assert desc.segment_count == 1
        assert desc.plain_length == len(LEASE_PLAIN)
        assert desc.segments[0].startswith(LEASE_PLAIN[:4])
        assert desc.segments[0].endswith(LEASE_PLAIN[-4:])
        assert LEASE_PLAIN not in desc.segments[0]
        assert "长度" in desc.summary

    def test_multi_secret_counts_each_line(self, encryption_settings: Any) -> None:
        raw = _encrypt("\n".join([LEASE_PLAIN, SECOND_PLAIN, THIRD_PLAIN]))

        desc = describe_stored_value(raw, is_secret=True)

        assert desc.segment_count == 3
        assert desc.segment_lengths == (len(LEASE_PLAIN), len(SECOND_PLAIN), len(THIRD_PLAIN))
        assert desc.display == "已配置 3 个值"
        assert mask_summary(raw) == "已配置 3 个值"
        assert all(plain not in " ".join(desc.segments) for plain in (LEASE_PLAIN, SECOND_PLAIN, THIRD_PLAIN))

    def test_comma_and_semicolon_are_also_separators(self, encryption_settings: Any) -> None:
        raw = _encrypt(f"{LEASE_PLAIN},{SECOND_PLAIN};{THIRD_PLAIN}")

        assert count_segments(raw) == 3

    def test_empty_value(self) -> None:
        desc = describe_stored_value("", is_secret=True)

        assert desc.segment_count == 0
        assert desc.display == "未设置"
        assert count_segments(None) == 0

    def test_wrong_key_marks_decrypt_failed(self, encryption_settings: Any) -> None:
        ciphertext = _encrypt(LEASE_PLAIN)
        encryption_settings.CREDENTIAL_ENCRYPTION_KEY = Fernet.generate_key().decode()

        desc = describe_stored_value(ciphertext, is_secret=True)

        assert desc.decrypt_failed is True
        assert desc.failure_reason == "bad_cipher"
        assert "主密钥" in desc.failure_message
        assert desc.segments == ()

    def test_missing_key_reason_is_distinct(self) -> None:
        from apps.core.security.secret_codec import SecretCodec

        with patch("apps.core.security.secret_codec.settings") as mock_settings:
            mock_settings.CREDENTIAL_ENCRYPTION_KEY = Fernet.generate_key().decode()
            mock_settings.SCRAPER_ENCRYPTION_KEY = None
            mock_settings.DEBUG = False
            ciphertext = SecretCodec().encrypt(LEASE_PLAIN)

        with patch("apps.core.security.secret_codec.settings") as mock_settings:
            mock_settings.CREDENTIAL_ENCRYPTION_KEY = None
            mock_settings.SCRAPER_ENCRYPTION_KEY = None
            mock_settings.DEBUG = False
            desc = describe_stored_value(ciphertext, is_secret=True)

        assert desc.failure_reason == "missing_key"
        assert "CREDENTIAL_ENCRYPTION_KEY" in desc.failure_message

    def test_non_secret_value_is_shown_as_is(self) -> None:
        desc = describe_stored_value("paddleocr_api", is_secret=False)

        assert desc.segments == ("paddleocr_api",)
        assert desc.display == "paddleocr_api"


class TestRevealStoredValue:
    """明文解密：只在显式调用时返回，失败要抛可展示的异常。"""

    def test_returns_plaintext(self, encryption_settings: Any) -> None:
        assert reveal_stored_value(_encrypt(LEASE_PLAIN)) == LEASE_PLAIN

    def test_plaintext_passthrough_for_legacy_rows(self) -> None:
        assert reveal_stored_value(LEASE_PLAIN) == LEASE_PLAIN
        assert reveal_stored_value("") == ""

    def test_raises_on_wrong_key(self, encryption_settings: Any) -> None:
        ciphertext = _encrypt(LEASE_PLAIN)
        encryption_settings.CREDENTIAL_ENCRYPTION_KEY = Fernet.generate_key().decode()

        with pytest.raises(SecretValueUndecryptable) as excinfo:
            reveal_stored_value(ciphertext)

        assert excinfo.value.reason == "bad_cipher"


class TestStoredValueAdminPage:
    """Admin 查看页：GET 无明文、POST 才出明文、不缓存、有权限门禁。"""

    @pytest.fixture()
    def config(self, encryption_settings: Any) -> Any:
        from apps.core.models import SystemConfig

        return SystemConfig.objects.create(
            key="TEST_PADDLEOCR_API_TOKEN",
            value=_encrypt("\n".join([LEASE_PLAIN, SECOND_PLAIN, THIRD_PLAIN])),
            category="ocr",
            is_secret=True,
            is_active=True,
        )

    def _url(self, config: Any) -> str:
        return f"/admin/core/systemconfig/{config.pk}/stored-value/"

    def test_change_form_shows_mask_only(self, client: Any, admin_user: Any, config: Any) -> None:
        client.force_login(admin_user)
        response = client.get(f"/admin/core/systemconfig/{config.pk}/change/")

        assert response.status_code == 200
        body = response.content.decode()
        assert "已存值" in body
        assert "共 3 个值" in body
        for plain in (LEASE_PLAIN, SECOND_PLAIN, THIRD_PLAIN):
            assert plain not in body
        assert config.value not in body

    @pytest.mark.parametrize("url_suffix", ["stored-value/"])
    def test_get_page_has_no_plaintext(
        self, client: Any, admin_user: Any, config: Any, url_suffix: str
    ) -> None:
        client.force_login(admin_user)
        response = client.get(self._url(config))

        assert response.status_code == 200
        body = response.content.decode()
        assert "显示明文" in body
        for plain in (LEASE_PLAIN, SECOND_PLAIN, THIRD_PLAIN):
            assert plain not in body
        assert response["Cache-Control"].startswith("no-store")

    def test_post_reveals_plaintext_once(self, client: Any, admin_user: Any, config: Any) -> None:
        client.force_login(admin_user)
        response = client.post(self._url(config), data={"action": "reveal"})

        assert response.status_code == 200
        body = response.content.decode()
        for plain in (LEASE_PLAIN, SECOND_PLAIN, THIRD_PLAIN):
            assert plain in body
        assert response["Cache-Control"].startswith("no-store")

    def test_post_logs_audit_without_plaintext(
        self, client: Any, admin_user: Any, config: Any, caplog: Any
    ) -> None:
        client.force_login(admin_user)

        with caplog.at_level(logging.INFO, logger="apps.core.admin.system_config_admin"):
            client.post(self._url(config), data={"action": "reveal"})

        records = [r for r in caplog.records if "stored_value_revealed" in r.getMessage()]
        assert records, "查看明文必须留审计日志"
        message = records[0].getMessage()
        assert config.key in message
        assert str(admin_user.get_username()) in message
        for plain in (LEASE_PLAIN, SECOND_PLAIN, THIRD_PLAIN):
            assert plain not in message

    def test_other_post_action_does_not_reveal(self, client: Any, admin_user: Any, config: Any) -> None:
        client.force_login(admin_user)
        response = client.post(self._url(config), data={"action": "noop"}, follow=True)

        assert response.status_code == 200
        assert LEASE_PLAIN not in response.content.decode()

    def test_staff_without_permission_is_forbidden(self, client: Any, config: Any) -> None:
        from apps.organization.models import Lawyer

        staff = Lawyer.objects.create_user(
            username="stored_value_staff_no_perm",
            password="testpass1234!",  # pragma: allowlist secret
            is_staff=True,
        )
        client.force_login(staff)
        response = client.get(self._url(config))

        assert response.status_code == 403

    def test_decrypt_failure_is_reported_not_crashed(
        self, client: Any, admin_user: Any, config: Any, encryption_settings: Any
    ) -> None:
        client.force_login(admin_user)
        encryption_settings.CREDENTIAL_ENCRYPTION_KEY = Fernet.generate_key().decode()

        page = client.get(self._url(config))
        assert page.status_code == 200
        assert "无法解密" in page.content.decode()

        posted = client.post(self._url(config), data={"action": "reveal"})
        assert posted.status_code == 200
        assert "主密钥" in posted.content.decode()
