"""DocumentParseProvider 模型 / ParseProviderService / 数据迁移测试"""

import pytest
from django.db import connection

from apps.core.models import DocumentParseProvider, LLMProvider
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

        textin = ParseProviderService.get_provider("textin")
        mineru = ParseProviderService.get_provider("mineru")
        # 禁用平台不返回；mineru 启用的是 M1
        assert textin is not None and textin.name == "T1"
        assert mineru is not None and mineru.name == "M1"
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


class TestCredentialsEncryptionAtRest:
    """credentials 改为 EncryptedTextField 后：落库密文、读回明文、解析不变。"""

    @pytest.mark.django_db
    def test_credentials_encrypted_at_rest_and_round_trip(self) -> None:
        raw = "app-1|secret-1\napp-2|secret-2"  # pragma: allowlist secret
        provider = DocumentParseProvider.objects.create(
            name="T1", provider_type="textin", credentials=raw
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT credentials FROM core_documentparseprovider WHERE id = %s", [provider.id]
            )
            stored = cursor.fetchone()[0]
        assert stored.startswith("enc:v1:")
        assert "secret-1" not in stored  # pragma: allowlist secret

        reloaded = DocumentParseProvider.objects.get(pk=provider.pk)
        assert reloaded.credentials == raw
        assert reloaded.parsed_credentials() == ["app-1|secret-1", "app-2|secret-2"]
        assert DocumentParseProvider.split_textin_credential(reloaded.parsed_credentials()[0]) == (
            "app-1",
            "secret-1",
        )


class TestEncryptExistingSecretsMigration:
    """0028 数据迁移：存量明文凭证加密回写，重复执行幂等。"""

    @pytest.mark.django_db
    def test_plaintext_rows_encrypted_in_place(self) -> None:
        from importlib import import_module
        from unittest.mock import MagicMock

        from django.apps import apps

        module = import_module(
            "apps.core.migrations.0028_alter_documentparseprovider_credentials_and_more"
        )

        llm = LLMProvider.objects.create(
            name="存量平台", base_url="http://law/v1", api_keys="", default_model="kimi26"
        )
        textin = DocumentParseProvider.objects.create(
            name="存量T1", provider_type="textin", credentials=""
        )
        # 模拟迁移前已落库的明文行（绕过 ORM 加密直接写库）
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE core_llmprovider SET api_keys = %s WHERE id = %s",
                ["sk-old-1\nsk-old-2", llm.id],
            )
            cursor.execute(
                "UPDATE core_documentparseprovider SET credentials = %s WHERE id = %s",
                ["old-app|old-secret", textin.id],
            )

        module.encrypt_existing_secrets(apps, MagicMock())

        with connection.cursor() as cursor:
            cursor.execute("SELECT api_keys FROM core_llmprovider WHERE id = %s", [llm.id])
            llm_stored = cursor.fetchone()[0]
            cursor.execute(
                "SELECT credentials FROM core_documentparseprovider WHERE id = %s", [textin.id]
            )
            textin_stored = cursor.fetchone()[0]
        assert llm_stored.startswith("enc:v1:")
        assert "sk-old-1" not in llm_stored  # pragma: allowlist secret
        assert textin_stored.startswith("enc:v1:")
        assert "old-secret" not in textin_stored  # pragma: allowlist secret

        # ORM 读回明文，key 池 / 凭证拆分逻辑不变
        assert LLMProvider.objects.get(pk=llm.pk).parsed_api_keys() == ["sk-old-1", "sk-old-2"]  # pragma: allowlist secret
        assert DocumentParseProvider.objects.get(pk=textin.pk).parsed_credentials() == [
            "old-app|old-secret"
        ]

        # 幂等：重复执行不报错，明文读回结果不变
        module.encrypt_existing_secrets(apps, MagicMock())
        assert DocumentParseProvider.objects.get(pk=textin.pk).credentials == "old-app|old-secret"  # pragma: allowlist secret
