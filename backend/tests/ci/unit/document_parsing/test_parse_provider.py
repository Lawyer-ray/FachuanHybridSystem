"""DocumentParseProvider 模型 / ParseProviderService / 数据迁移测试"""

import pytest

from apps.core.models import DocumentParseProvider
from apps.core.services.document_parse_provider_service import ParseProviderService


@pytest.fixture(autouse=True)
def _invalidate_cache():
    ParseProviderService.invalidate_cache()
    yield
    ParseProviderService.invalidate_cache()


class TestModelCredentials:
    @pytest.mark.django_db
    def test_parsed_credentials_dedup(self) -> None:
        p = DocumentParseProvider.objects.create(
            name="M1",
            provider_type="mineru",
            credentials="key1\nkey2\nkey1\n  key3  ",
        )
        assert p.parsed_credentials() == ["key1", "key2", "key3"]

    @pytest.mark.django_db
    def test_split_textin_credential(self) -> None:
        assert DocumentParseProvider.split_textin_credential("app-1|secret-1") == ("app-1", "secret-1")
        assert DocumentParseProvider.split_textin_credential(" app | sec ") == ("app", "sec")
        assert DocumentParseProvider.split_textin_credential("no-pipe") is None
        assert DocumentParseProvider.split_textin_credential("") is None


class TestParseProviderService:
    @pytest.mark.django_db
    def test_get_provider_filters_enabled_and_type(self) -> None:
        DocumentParseProvider.objects.create(
            name="M1", provider_type="mineru", priority=10, enabled=True, credentials="k1"
        )
        DocumentParseProvider.objects.create(
            name="T1", provider_type="textin", priority=5, enabled=True, credentials="app|sec"
        )
        DocumentParseProvider.objects.create(
            name="M2", provider_type="mineru", priority=1, enabled=False, credentials="k2"
        )

        assert ParseProviderService.get_provider("textin").name == "T1"
        # 禁用平台不返回；mineru 启用的是 M1
        assert ParseProviderService.get_provider("mineru").name == "M1"
        assert ParseProviderService.get_provider("local") is None

    @pytest.mark.django_db
    def test_get_providers_sorted_by_priority(self) -> None:
        DocumentParseProvider.objects.create(
            name="B", provider_type="mineru", priority=20, enabled=True, credentials="k1"
        )
        DocumentParseProvider.objects.create(
            name="A", provider_type="mineru", priority=5, enabled=True, credentials="k2"
        )
        providers = ParseProviderService.get_providers()
        assert [p.name for p in providers] == ["A", "B"]

    @pytest.mark.django_db
    def test_invalidate_cache_refreshes(self) -> None:
        DocumentParseProvider.objects.create(
            name="M1", provider_type="mineru", priority=10, enabled=True, credentials="k1"
        )
        assert ParseProviderService.get_provider("mineru") is not None
        # 禁用后清缓存应能反映
        DocumentParseProvider.objects.filter(name="M1").update(enabled=False)
        ParseProviderService.invalidate_cache()
        assert ParseProviderService.get_provider("mineru") is None


class TestSeedMigration:
    @pytest.mark.django_db
    def test_migrate_seed_and_cleanup(self) -> None:
        from importlib import import_module
        from unittest.mock import MagicMock

        from apps.core.models.system_config import SystemConfig
        from apps.core.security.secret_codec import SecretCodec

        module = import_module("apps.core.migrations.0023_seed_document_parse_provider")

        # 构造旧的 SystemConfig 配置
        codec = SecretCodec()
        SystemConfig.objects.create(
            key="MINERU_API_KEY",
            value=codec.encrypt("mkey-a mkey-b"),
            category="document_parsing",
            is_secret=True,
        )
        SystemConfig.objects.create(
            key="TEXTIN_APP_ID",
            value=codec.encrypt("t-app"),
            category="document_parsing",
            is_secret=True,
        )
        SystemConfig.objects.create(
            key="TEXTIN_SECRET_CODE",
            value=codec.encrypt("t-secret"),
            category="document_parsing",
            is_secret=True,
        )
        SystemConfig.objects.create(
            key="DOCUMENT_PARSING_BACKEND",
            value="textin",
            category="document_parsing",
            is_secret=False,
        )

        # 运行迁移函数（仅操作 model，schema_editor 未使用）
        from django.apps import apps

        module.seed_and_cleanup(apps, MagicMock())

        # 旧键删除
        assert SystemConfig.objects.filter(key="DOCUMENT_PARSING_BACKEND").exists() is False
        assert SystemConfig.objects.filter(key="MINERU_API_KEY").exists() is False
        assert SystemConfig.objects.filter(key="TEXTIN_APP_ID").exists() is False
        assert SystemConfig.objects.filter(key="TEXTIN_SECRET_CODE").exists() is False

        # 播种结果：textin 为 preferred → priority 5，mineru 默认 10
        textin = DocumentParseProvider.objects.get(provider_type="textin")
        assert textin.credentials == "t-app|t-secret"
        assert textin.priority == 5
        mineru = DocumentParseProvider.objects.get(provider_type="mineru")
        assert mineru.parsed_credentials() == ["mkey-a", "mkey-b"]
        assert mineru.priority == 10
