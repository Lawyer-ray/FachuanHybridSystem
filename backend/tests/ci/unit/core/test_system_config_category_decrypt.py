"""SystemConfig 分类配置读侧解密回归测试。

覆盖 2026-10-12 事故：2026-10-04 安全审计把 SystemConfig 存量明文 secret
全量重加密（值带 enc:v1: 前缀）后，get_category_configs 读侧未解密，
群聊 provider（飞书/企微/钉钉/Telegram）把密文当 app_secret 发给平台，
法院短信群聊通知自 10-09 起全线「获取飞书访问令牌失败: app secret invalid」。

修复语义：get_category_configs 与 get_value 同口径——密文读侧解密，
明文原样返回（兼容存量），解不开的密文降级返回原值（E-01 语义）。
"""

from __future__ import annotations

import pytest

from apps.core.models import SystemConfig
from apps.core.security.secret_codec import SecretCodec
from apps.core.services.system_config_service import SystemConfigService


def _make_feishu_configs(secret_stored_value: str) -> None:
    SystemConfig.objects.update_or_create(
        key="FEISHU_APP_ID",
        defaults={"value": "cli_test_app_id", "category": "feishu", "is_active": True},
    )
    SystemConfig.objects.update_or_create(
        key="FEISHU_APP_SECRET",
        defaults={"value": secret_stored_value, "category": "feishu", "is_active": True},
    )


class TestGetCategoryConfigsDecrypt:
    def test_encrypted_secret_decrypted_on_read(self, db):
        """密文存储的 secret 经分类读取返回明文（事故场景）。"""
        codec = SecretCodec()
        _make_feishu_configs(codec.encrypt("mock-credential-value-001"))

        configs = SystemConfigService().get_category_configs("feishu")

        assert configs["FEISHU_APP_SECRET"] == "mock-credential-value-001"  # pragma: allowlist secret
        assert not configs["FEISHU_APP_SECRET"].startswith("enc:v1:")

    def test_plaintext_value_passthrough(self, db):
        """存量明文不受影响，原样返回。"""
        _make_feishu_configs("legacy-plain-credential")
        SystemConfig.objects.update_or_create(
            key="FEISHU_WEBHOOK_URL",
            defaults={
                "value": "https://open.feishu.cn/hook/xxx",  # pragma: allowlist secret
                "category": "feishu",
                "is_active": True,
            },
        )

        configs = SystemConfigService().get_category_configs("feishu")

        assert configs["FEISHU_APP_SECRET"] == "legacy-plain-credential"  # pragma: allowlist secret
        assert configs["FEISHU_WEBHOOK_URL"] == "https://open.feishu.cn/hook/xxx"

    def test_undecryptable_ciphertext_degrades_to_original(self, db):
        """密钥轮换后解不开的密文降级返回原值（E-01：不炸读取链路）。"""
        _make_feishu_configs("enc:v1:GARBAGE_NOT_DECRYPTABLE")

        configs = SystemConfigService().get_category_configs("feishu")

        assert configs["FEISHU_APP_SECRET"] == "enc:v1:GARBAGE_NOT_DECRYPTABLE"  # pragma: allowlist secret

    def test_feishu_provider_gets_usable_secret(self, db):
        """端到端：群聊 provider 的分类加载链路拿到的是明文 secret。"""
        from apps.automation.services.chat.feishu_provider import FeishuChatProvider

        codec = SecretCodec()
        _make_feishu_configs(codec.encrypt("provider-level-credential"))

        provider = FeishuChatProvider()
        cfg = provider._load_config_from_db()

        assert cfg["APP_SECRET"] == "provider-level-credential"  # pragma: allowlist secret
        assert cfg["APP_ID"] == "cli_test_app_id"

    @pytest.mark.parametrize("category", ["feishu", "wechat_work", "dingtalk", "telegram"])
    def test_all_chat_platforms_categories_covered(self, db, category):
        """四个群聊平台分类都走同一解密口径（同一次事故面）。"""
        secret = SecretCodec().encrypt(f"secret-for-{category}")
        SystemConfig.objects.update_or_create(
            key=f"{category.upper()}_APP_SECRET",
            defaults={"value": secret, "category": category, "is_active": True},
        )

        configs = SystemConfigService().get_category_configs(category)

        assert configs[f"{category.upper()}_APP_SECRET"] == f"secret-for-{category}"
