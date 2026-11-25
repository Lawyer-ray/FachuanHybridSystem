"""敏感配置的「看得见」行为：编辑页直接把当前明文回填进「配置值」输入框。

口径（2026-11-25 用户要求）：不加只读块、不加二级页、不加确认按钮——
打开 `/admin/core/systemconfig/<pk>/change/` 就该看到存了什么。

保留的兜底：
- 清空后保存 → 保留库中原值（`clean()` 里回填密文），误清空不会丢配置；
- 解密失败（换过主密钥 / 缺密钥）→ 输入框留空 + help_text 给出可执行提示，页面不 500；
- changelist「配置值」列仍走掩码（表格里不铺明文）。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet

from apps.core.admin.forms import SystemConfigAdminForm
from apps.core.security.secret_display import (
    SecretValueUndecryptable,
    count_segments,
    describe_stored_value,
    mask_summary,
    reveal_stored_value,
)

pytestmark = pytest.mark.django_db

KEY_ONE = "sk-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1"  # pragma: allowlist secret
KEY_TWO = "sk-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb2"  # pragma: allowlist secret
KEY_THREE = "sk-ccccccccccccccccccccccccccccccccccc3"  # pragma: allowlist secret


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


def _config(*, key: str = "TEST_SECRET_CFG", **overrides: Any) -> Any:
    """建/取一条 secret 配置。key 默认用测试专属名，避免撞默认配置的 unique 约束。"""
    from apps.core.models import SystemConfig

    data = {
        "value": _encrypt("\n".join([KEY_ONE, KEY_TWO, KEY_THREE])),
        "category": "ocr",
        "is_secret": True,
        "is_active": True,
    }
    data.update(overrides)
    obj, _created = SystemConfig.objects.update_or_create(key=key, defaults=data)
    return obj


def _multi_key_config() -> Any:
    """多 Key 型配置（key 必须在 _MULTI_KEY_CONFIGS 里，因此复用默认行而不是新建）。"""
    return _config(key="PADDLEOCR_API_TOKEN")


class TestFormEchoesPlaintext:
    """表单层：initial 就是明文，多 Key 逐行保留。"""

    def test_initial_is_plaintext(self, encryption_settings: Any) -> None:
        form = SystemConfigAdminForm(instance=_config())

        assert form.initial["value"] == f"{KEY_ONE}\n{KEY_TWO}\n{KEY_THREE}"

    def test_rendered_textarea_contains_every_key(self, encryption_settings: Any) -> None:
        rendered = SystemConfigAdminForm(instance=_config()).as_p()

        for key in (KEY_ONE, KEY_TWO, KEY_THREE):
            assert key in rendered
        assert "enc:v1:" not in rendered
        assert "已回填当前值" in rendered

    def test_multi_key_hint_survives(self, encryption_settings: Any) -> None:
        """多 Key 提示不能被"已回填"文案覆盖掉（两段 help_text 要叠加）。"""

        def _all_help_text(form: SystemConfigAdminForm) -> str:
            return str(form.fields["value"].help_text or "")

        help_text = _all_help_text(SystemConfigAdminForm(instance=_multi_key_config()))

        assert "已回填当前值" in help_text
        assert "每行一个" in help_text

    def test_blank_submit_keeps_plaintext_value(self, encryption_settings: Any) -> None:
        """清空输入框再保存 → 库中原值不变（分段仍为 3）。"""
        config = _config()

        form = SystemConfigAdminForm(
            data={
                "key": config.key,
                "value": "",
                "category": config.category,
                "description": "",
                "is_secret": "on",  # pragma: allowlist secret
                "is_active": "on",
            },
            instance=config,
        )
        assert form.is_valid(), form.errors
        form.save()
        config.refresh_from_db()

        assert reveal_stored_value(config.value).splitlines() == [KEY_ONE, KEY_TWO, KEY_THREE]

    def test_resubmitting_echoed_plaintext_round_trips(self, encryption_settings: Any) -> None:
        """原值回填后再保存（用户什么都没改）→ 内容不变，不是"明文覆盖密文"事故。"""
        config = _config()
        form = SystemConfigAdminForm(instance=config)
        echoed = str(form.initial["value"])

        bound = SystemConfigAdminForm(
            data={
                "key": config.key,
                "value": echoed,
                "category": config.category,
                "description": "",
                "is_secret": "on",  # pragma: allowlist secret
                "is_active": "on",
            },
            instance=config,
        )
        assert bound.is_valid(), bound.errors
        bound.save()
        config.refresh_from_db()

        assert config.value.startswith("enc:v1:")
        assert reveal_stored_value(config.value).splitlines() == [KEY_ONE, KEY_TWO, KEY_THREE]

    def test_decrypt_failure_leaves_field_empty_with_hint(self, encryption_settings: Any, caplog: Any) -> None:
        config = _config()
        encryption_settings.CREDENTIAL_ENCRYPTION_KEY = Fernet.generate_key().decode()

        form = SystemConfigAdminForm(instance=config)

        assert form.initial["value"] == ""
        assert "主密钥" in str(form.fields["value"].help_text)
        assert caplog is not None

    def test_non_secret_value_is_untouched(self, encryption_settings: Any) -> None:
        config = _config(key="OCR_PROVIDER", value="paddleocr_api", is_secret=False)

        form = SystemConfigAdminForm(instance=config)

        assert form.initial["value"] == "paddleocr_api"


class TestAdminChangePageShowsPlaintext:
    """端点层：打开编辑页就能看到明文，且没有额外页面/按钮。"""

    def test_change_page_contains_plaintext(self, client: Any, admin_user: Any, encryption_settings: Any) -> None:
        config = _config()
        client.force_login(admin_user)

        response = client.get(f"/admin/core/systemconfig/{config.pk}/change/")

        assert response.status_code == 200
        body = response.content.decode()
        for key in (KEY_ONE, KEY_TWO, KEY_THREE):
            assert key in body

    def test_no_readonly_block_and_no_second_page(self, client: Any, admin_user: Any, encryption_settings: Any) -> None:
        config = _config()
        client.force_login(admin_user)

        body = client.get(f"/admin/core/systemconfig/{config.pk}/change/").content.decode()

        assert "当前值（明文）" not in body
        assert "查看已存值" not in body
        assert "stored-value" not in body

    def test_stored_value_route_is_gone(self, client: Any, admin_user: Any, encryption_settings: Any) -> None:
        config = _config()
        client.force_login(admin_user)

        response = client.get(f"/admin/core/systemconfig/{config.pk}/stored-value/")

        # 路由已删；Django admin 会把 "stored-value" 当成 object_id 的一部分 → 302 到不存在的 change 页
        assert response.status_code in (302, 404)
        assert KEY_ONE not in response.content.decode()


class TestMaskHelpers:
    """changelist 掩码口径（表格里不铺明文）。"""

    def test_mask_summary_counts_segments(self, encryption_settings: Any) -> None:
        raw = _encrypt("\n".join([KEY_ONE, KEY_TWO, KEY_THREE]))

        assert mask_summary(raw) == "已配置 3 个值"
        assert count_segments(raw) == 3

    def test_single_secret_mask_keeps_head_and_tail(self, encryption_settings: Any) -> None:
        desc = describe_stored_value(_encrypt(KEY_ONE), is_secret=True)

        assert desc.segments[0].startswith(KEY_ONE[:4])
        assert desc.segments[0].endswith(KEY_ONE[-4:])
        assert KEY_ONE not in desc.segments[0]

    def test_comma_and_semicolon_are_separators(self, encryption_settings: Any) -> None:
        raw = _encrypt(f"{KEY_ONE},{KEY_TWO};{KEY_THREE}")

        assert count_segments(raw) == 3

    def test_wrong_key_marks_decrypt_failed(self, encryption_settings: Any) -> None:
        ciphertext = _encrypt(KEY_ONE)
        encryption_settings.CREDENTIAL_ENCRYPTION_KEY = Fernet.generate_key().decode()

        desc = describe_stored_value(ciphertext, is_secret=True)

        assert desc.decrypt_failed is True
        assert desc.failure_reason == "bad_cipher"

        with pytest.raises(SecretValueUndecryptable):
            reveal_stored_value(ciphertext)

    def test_empty_value(self) -> None:
        assert describe_stored_value("", is_secret=True).display == "未设置"
        assert count_segments(None) == 0
