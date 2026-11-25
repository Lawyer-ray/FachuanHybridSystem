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


class TestChangeFormStoredValue:
    """编辑页直接显示明文（只读块），没有额外页面、没有二次确认按钮。"""

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

    def _change_url(self, config: Any) -> str:
        return f"/admin/core/systemconfig/{config.pk}/change/"

    def test_change_form_shows_plaintext_directly(self, client: Any, admin_user: Any, config: Any) -> None:
        """核心诉求：打开编辑页就能看到结果，不需要点任何按钮。"""
        client.force_login(admin_user)
        response = client.get(self._change_url(config))

        assert response.status_code == 200
        body = response.content.decode()
        for plain in (LEASE_PLAIN, SECOND_PLAIN, THIRD_PLAIN):
            assert plain in body
        assert "当前值（明文）" in body
        assert "共 3 个值" in body

    def test_no_extra_page_or_reveal_button(self, client: Any, admin_user: Any, config: Any) -> None:
        """不该再有「查看已存值」二级页与二次确认按钮。"""
        client.force_login(admin_user)
        body = client.get(self._change_url(config)).content.decode()

        assert "stored-value" not in body
        assert "查看已存值" not in body
        assert "显示明文" not in body

    def test_editable_value_field_stays_empty(self, client: Any, admin_user: Any, config: Any) -> None:
        """输入框仍留空（留空=不修改），明文只在只读块里，不会被误提交回去。"""
        from apps.core.models import SystemConfig

        client.force_login(admin_user)
        response = client.post(
            self._change_url(config),
            data={
                "key": config.key,
                "value": "",
                "category": config.category,
                "description": "",
                "is_secret": "on",  # pragma: allowlist secret
                "is_active": "on",
            },
            follow=True,
        )

        assert response.status_code == 200
        config.refresh_from_db()
        from apps.core.security.secret_display import reveal_stored_value

        lines = reveal_stored_value(config.value).splitlines()
        assert lines == [LEASE_PLAIN, SECOND_PLAIN, THIRD_PLAIN]
        assert SystemConfig.objects.get(pk=config.pk).value.startswith("enc:v1:")

    def test_non_secret_config_has_no_extra_block(self, client: Any, admin_user: Any, encryption_settings: Any) -> None:
        from apps.core.models import SystemConfig

        plain_config = SystemConfig.objects.create(
            key="TEST_OCR_PROVIDER", value="paddleocr_api", category="ocr", is_secret=False, is_active=True
        )
        client.force_login(admin_user)
        body = client.get(self._change_url(plain_config)).content.decode()

        assert "paddleocr_api" in body
        assert "当前值（明文）" not in body

    def test_add_page_has_no_block(self, client: Any, admin_user: Any) -> None:
        client.force_login(admin_user)
        response = client.get("/admin/core/systemconfig/add/")

        assert response.status_code == 200
        assert "当前值（明文）" not in response.content.decode()

    def test_decrypt_failure_is_reported_inline(
        self, client: Any, admin_user: Any, config: Any, encryption_settings: Any
    ) -> None:
        client.force_login(admin_user)
        encryption_settings.CREDENTIAL_ENCRYPTION_KEY = Fernet.generate_key().decode()

        response = client.get(self._change_url(config))

        assert response.status_code == 200
        body = response.content.decode()
        assert "无法解密" in body or "主密钥" in body
        for plain in (LEASE_PLAIN, SECOND_PLAIN, THIRD_PLAIN):
            assert plain not in body
