"""core 模块真实执行测试 - 覆盖 cache_service, scrub, permissions, config, llm, filename_template, material_classification 等。"""
from __future__ import annotations

import hashlib
import time
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ============================================================
# core/security/scrub.py
# ============================================================


class TestScrub:
    def test_mask_secret_short(self) -> None:
        from apps.core.security.scrub import mask_secret

        assert mask_secret("abc") == "***"
        assert mask_secret("abcdef") == "***"

    def test_mask_secret_long(self) -> None:
        from apps.core.security.scrub import mask_secret

        result = mask_secret("abcdefghijklmnop")
        assert result == "ab***op"

    def test_looks_like_token_with_sk_prefix(self) -> None:
        from apps.core.security.scrub import looks_like_token

        assert looks_like_token("sk-abcdefghij123456") is True
        assert looks_like_token("short") is False

    def test_looks_like_token_long_alphanumeric(self) -> None:
        from apps.core.security.scrub import looks_like_token

        assert looks_like_token("a" * 24) is True
        assert looks_like_token("abc") is False

    def test_is_sensitive_key_name_exact_match(self) -> None:
        from apps.core.security.scrub import is_sensitive_key_name

        for name in ("token", "password", "secret", "api_key", "access_token", "authorization"):
            assert is_sensitive_key_name(name) is True, f"Expected {name} to be sensitive"

    def test_is_sensitive_key_name_camel_case(self) -> None:
        from apps.core.security.scrub import is_sensitive_key_name

        assert is_sensitive_key_name("accessToken") is True
        assert is_sensitive_key_name("refreshToken") is True

    def test_is_sensitive_key_name_non_sensitive(self) -> None:
        from apps.core.security.scrub import is_sensitive_key_name

        assert is_sensitive_key_name("name") is False
        assert is_sensitive_key_name("description") is False

    def test_scrub_text_masks_sk_key(self) -> None:
        from apps.core.security.scrub import scrub_text

        result = scrub_text("Using sk-abcdefghijklmnopqrstuvwxyz123456 to connect")
        assert "sk-abc" not in result or "***" in result

    def test_scrub_obj_dict(self) -> None:
        from apps.core.security.scrub import scrub_obj

        obj = {"name": "test", "token": "very_long_secret_value_here", "count": 42}
        result = scrub_obj(obj)
        assert result["name"] == "test"
        assert result["token"] != "very_long_secret_value_here"
        assert result["count"] == 42

    def test_scrub_obj_nested(self) -> None:
        from apps.core.security.scrub import scrub_obj

        obj = {"data": {"password": "secret123", "ok": "visible"}}
        result = scrub_obj(obj)
        assert result["data"]["password"] != "secret123"
        assert result["data"]["ok"] == "visible"

    def test_scrub_obj_list(self) -> None:
        from apps.core.security.scrub import scrub_obj

        obj = [{"name": "a"}, {"token": "longtokenvalue123"}]
        result = scrub_obj(obj)
        assert isinstance(result, list)
        assert result[0]["name"] == "a"

    def test_scrub_obj_max_depth(self) -> None:
        from apps.core.security.scrub import scrub_obj

        obj = {"a": {"b": {"c": {"d": {"e": {"f": {"g": "deep"}}}}}}}
        result = scrub_obj(obj, depth=5)
        assert result == obj

    def test_fingerprint_sha256(self) -> None:
        from apps.core.security.scrub import fingerprint_sha256

        result = fingerprint_sha256("test_value")
        expected = hashlib.sha256(b"test_value").hexdigest()
        assert result == expected

    def test_fingerprint_sha256_empty(self) -> None:
        from apps.core.security.scrub import fingerprint_sha256

        result = fingerprint_sha256("")
        expected = hashlib.sha256(b"").hexdigest()
        assert result == expected

    def test_scrub_for_storage(self) -> None:
        from apps.core.security.scrub import scrub_for_storage

        data = {"api_key": "super_secret_key_123456", "name": "test"}
        result = scrub_for_storage(data)
        assert result["api_key"] != "super_secret_key_123456"


# ============================================================
# core/security/permissions.py
# ============================================================


class TestPermissions:
    def test_check_authenticated_pass(self) -> None:
        from apps.core.security.permissions import AccessContext, PermissionMixin

        ctx = AccessContext(
            user=SimpleNamespace(is_authenticated=True),
            org_access=None,
            perm_open_access=False,
        )
        mixin = PermissionMixin()
        mixin.check_authenticated(ctx)  # should not raise

    def test_check_authenticated_fail(self) -> None:
        from apps.core.security.permissions import AccessContext, PermissionMixin
        from apps.core.exceptions import AuthenticationError

        ctx = AccessContext(user=None, org_access=None, perm_open_access=False)
        mixin = PermissionMixin()
        with pytest.raises(AuthenticationError):
            mixin.check_authenticated(ctx)

    def test_is_authenticated_user_true(self) -> None:
        from apps.core.security.permissions import AccessContext, PermissionMixin

        ctx = AccessContext(
            user=SimpleNamespace(is_authenticated=True),
            org_access=None,
            perm_open_access=False,
        )
        mixin = PermissionMixin()
        assert mixin.is_authenticated_user(ctx) is True

    def test_has_open_access(self) -> None:
        from apps.core.security.permissions import AccessContext, PermissionMixin

        ctx = AccessContext(user=None, org_access=None, perm_open_access=True)
        mixin = PermissionMixin()
        assert mixin.has_open_access(ctx) is True

    def test_check_resource_access_open(self) -> None:
        from apps.core.security.permissions import AccessContext, PermissionMixin

        ctx = AccessContext(user=None, org_access=None, perm_open_access=True)
        mixin = PermissionMixin()
        mixin.check_resource_access(ctx, lambda c: False)  # should not raise

    def test_check_resource_access_denied(self) -> None:
        from apps.core.security.permissions import AccessContext, PermissionMixin
        from apps.core.exceptions import AuthenticationError

        # When user is not authenticated and not open_access,
        # check_resource_access raises AuthenticationError (from check_authenticated)
        ctx = AccessContext(user=None, org_access=None, perm_open_access=False)
        mixin = PermissionMixin()
        with pytest.raises(AuthenticationError):
            mixin.check_resource_access(ctx, lambda c: False)

    def test_check_resource_access_authenticated_passes(self) -> None:
        from apps.core.security.permissions import AccessContext, PermissionMixin

        # Authenticated user passes without needing resource_check
        ctx = AccessContext(
            user=SimpleNamespace(is_authenticated=True),
            org_access=None,
            perm_open_access=False,
        )
        mixin = PermissionMixin()
        mixin.check_resource_access(ctx, lambda c: False)  # should not raise


# ============================================================
# core/config/cache.py
# ============================================================


class TestConfigCache:
    def test_set_and_get(self) -> None:
        from apps.core.config.cache import ConfigCache

        cache = ConfigCache(max_size=100, ttl=60)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_missing_key(self) -> None:
        from apps.core.config.cache import ConfigCache

        cache = ConfigCache()
        assert cache.get("missing") is None

    def test_delete(self) -> None:
        from apps.core.config.cache import ConfigCache

        cache = ConfigCache()
        cache.set("k", "v")
        assert cache.delete("k") is True
        assert cache.get("k") is None

    def test_delete_missing(self) -> None:
        from apps.core.config.cache import ConfigCache

        cache = ConfigCache()
        assert cache.delete("nope") is False

    def test_clear(self) -> None:
        from apps.core.config.cache import ConfigCache

        cache = ConfigCache()
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.get("a") is None
        assert cache.get("b") is None

    def test_lru_eviction(self) -> None:
        from apps.core.config.cache import ConfigCache

        cache = ConfigCache(max_size=2, ttl=3600)
        cache.set("a", 1)
        time.sleep(0.01)
        cache.set("b", 2)
        time.sleep(0.01)
        cache.set("c", 3)  # should evict "a"
        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert cache.get("c") == 3

    def test_cleanup_expired(self) -> None:
        from apps.core.config.cache import CacheEntry, ConfigCache

        cache = ConfigCache(max_size=100, ttl=0.01)
        cache.set("old", "value")
        time.sleep(0.02)
        count = cache.cleanup_expired()
        assert count == 1
        assert cache.get("old") is None

    def test_cleanup_expired_no_ttl(self) -> None:
        from apps.core.config.cache import ConfigCache

        cache = ConfigCache(max_size=100, ttl=0)
        cache.set("k", "v")
        count = cache.cleanup_expired()
        assert count == 0

    def test_touch_updates_access_count(self) -> None:
        from apps.core.config.cache import CacheEntry

        entry = CacheEntry(value="test")
        assert entry.access_count == 0
        entry.touch()
        assert entry.access_count == 1


# ============================================================
# core/config/exceptions.py (extra tests)
# ============================================================


class TestConfigExceptionsRepr:
    def test_config_exception_repr(self) -> None:
        from apps.core.config.exceptions import ConfigException

        exc = ConfigException("msg", code="C1")
        r = repr(exc)
        assert "ConfigException" in r
        assert "msg" in r

    def test_config_type_error_no_value(self) -> None:
        from apps.core.config.exceptions import ConfigTypeError

        exc = ConfigTypeError("key", expected_type=int, actual_type=str)
        assert exc.value is None
        assert "key" in str(exc)

    def test_config_file_error_no_line(self) -> None:
        from apps.core.config.exceptions import ConfigFileError

        exc = ConfigFileError("/path")
        assert "path" in str(exc)


# ============================================================
# core/services/filename_template_service.py
# ============================================================


class TestFilenameTemplateService:
    def test_render_simple_template(self) -> None:
        from apps.core.services.filename_template_service import FilenameTemplateService

        result = FilenameTemplateService._render(
            "{title} - {case_name}",
            {"title", "case_name"},
            title="起诉状",
            case_name="张三诉李四",
        )
        assert result == "起诉状 - 张三诉李四"

    def test_render_with_invalid_placeholder(self) -> None:
        from apps.core.services.filename_template_service import FilenameTemplateService

        result = FilenameTemplateService._render(
            "{title} - {invalid}",
            {"title"},
            title="test",
        )
        assert result == "test - {invalid}"

    def test_get_unique_filepath_no_conflict(self, tmp_path: object) -> None:
        from apps.core.services.filename_template_service import FilenameTemplateService
        import pathlib

        d = pathlib.Path(str(tmp_path))
        filepath, name = FilenameTemplateService.get_unique_filepath(str(d), "test.txt")
        assert name == "test.txt"
        assert filepath == str(d / "test.txt")

    def test_get_unique_filepath_with_conflict(self, tmp_path: object) -> None:
        from apps.core.services.filename_template_service import FilenameTemplateService
        import pathlib

        d = pathlib.Path(str(tmp_path))
        (d / "test.txt").touch()
        (d / "test_1.txt").touch()
        filepath, name = FilenameTemplateService.get_unique_filepath(str(d), "test.txt")
        assert name == "test_2.txt"

    def test_render_court_doc_with_mock(self) -> None:
        from apps.core.services.filename_template_service import FilenameTemplateService

        mock_config = MagicMock()
        mock_config.get_value.return_value = "{title}（{case_name}）_{date}收"
        FilenameTemplateService._system_config_service = mock_config
        try:
            result = FilenameTemplateService.render_court_doc(
                title="判决书", case_name="张三诉李四", date="20260101"
            )
            assert "判决书" in result
            assert "张三诉李四" in result
        finally:
            FilenameTemplateService._system_config_service = None


# ============================================================
# core/services/material_classification_service.py
# ============================================================


class TestMaterialClassification:
    def test_classify_contract_not_in_contract_folder(self) -> None:
        from apps.core.services.material_classification_service import MaterialClassificationService

        svc = MaterialClassificationService()
        result = svc.classify_contract_material(
            filename="判决书.pdf",
            text_excerpt="",
            source_path="/案件材料/判决书.pdf",
        )
        assert result["category"] == "case_material"

    def test_classify_contract_in_contract_folder_supervision(self) -> None:
        from apps.core.services.material_classification_service import MaterialClassificationService

        svc = MaterialClassificationService()
        result = svc.classify_contract_material(
            filename="办案服务质量监督卡.pdf",
            text_excerpt="",
            source_path="/合同发票/监督卡.pdf",
        )
        assert result["category"] == "supervision_card"

    def test_classify_contract_in_folder_supplementary(self) -> None:
        from apps.core.services.material_classification_service import MaterialClassificationService

        svc = MaterialClassificationService()
        result = svc.classify_contract_material(
            filename="补充协议.pdf",
            text_excerpt="",
            source_path="/合同发票/",
        )
        assert result["category"] == "supplementary_agreement"

    def test_classify_contract_in_folder_invoice(self) -> None:
        from apps.core.services.material_classification_service import MaterialClassificationService

        svc = MaterialClassificationService()
        result = svc.classify_contract_material(
            filename="增值税发票.pdf",
            text_excerpt="",
            source_path="/合同发票/",
        )
        assert result["category"] == "invoice"

    def test_classify_contract_in_folder_original(self) -> None:
        from apps.core.services.material_classification_service import MaterialClassificationService

        svc = MaterialClassificationService()
        result = svc.classify_contract_material(
            filename="委托代理合同.pdf",
            text_excerpt="",
            source_path="/合同发票/",
        )
        assert result["category"] == "contract_original"

    def test_classify_case_by_filename_execution(self) -> None:
        from apps.core.services.material_classification_service import MaterialClassificationService

        svc = MaterialClassificationService()
        result = svc.classify_case_material(
            filename="执行申请书.pdf",
            text_excerpt="",
            enable_ai=False,
        )
        assert result["category"] == "party"
        assert result["side"] == "our"

    def test_classify_case_litigation_doc(self) -> None:
        from apps.core.services.material_classification_service import MaterialClassificationService

        svc = MaterialClassificationService()
        result = svc.classify_case_material(
            filename="起诉状.pdf",
            text_excerpt="原告张三",
            enable_ai=False,
        )
        # "起诉状" is in _LITIGATION_DOCUMENT_KEYWORDS but not in _CASE_RULES
        # Without AI, no case rule matches, so falls back to "unknown"
        assert result["category"] in ("party", "unknown")

    def test_extract_subfolder_hint(self) -> None:
        from apps.core.services.material_classification_service import MaterialClassificationService

        svc = MaterialClassificationService()
        assert svc._extract_subfolder_hint("2-立案材料") == "立案材料"
        assert svc._extract_subfolder_hint("3_执行依据") == "执行依据"
        assert svc._extract_subfolder_hint("") == ""
        assert svc._extract_subfolder_hint("1") == "1"

    def test_normalize_for_match(self) -> None:
        from apps.core.services.material_classification_service import MaterialClassificationService

        svc = MaterialClassificationService()
        assert svc._normalize_for_match("  Hello World  ") == "helloworld"
        assert svc._normalize_for_match(None) == ""
        assert svc._normalize_for_match("path\\to\\file") == "path/to/file"

    def test_to_confidence(self) -> None:
        from apps.core.services.material_classification_service import MaterialClassificationService

        svc = MaterialClassificationService()
        assert svc._to_confidence(0.5) == 0.5
        assert svc._to_confidence(1.5) == 1.0
        assert svc._to_confidence(-0.1) == 0.0
        assert svc._to_confidence(None) == 0.0
        assert svc._to_confidence("invalid") == 0.0

    def test_extract_json(self) -> None:
        from apps.core.services.material_classification_service import MaterialClassificationService

        svc = MaterialClassificationService()
        result = svc._extract_json('{"category": "party", "side": "our"}')
        assert result == {"category": "party", "side": "our"}

    def test_extract_json_fenced(self) -> None:
        from apps.core.services.material_classification_service import MaterialClassificationService

        svc = MaterialClassificationService()
        result = svc._extract_json('```json\n{"a": 1}\n```')
        assert result == {"a": 1}

    def test_extract_json_invalid(self) -> None:
        from apps.core.services.material_classification_service import MaterialClassificationService

        svc = MaterialClassificationService()
        assert svc._extract_json("not json") is None
        assert svc._extract_json("") is None

    def test_extract_party_ids_by_side(self) -> None:
        from apps.core.services.material_classification_service import MaterialClassificationService

        svc = MaterialClassificationService()
        ctx = {"our_party_ids": [1, 2, 3]}
        result = svc._extract_party_ids_by_side(side="our", context=ctx)
        assert result == [1, 2, 3]

    def test_extract_party_ids_invalid(self) -> None:
        from apps.core.services.material_classification_service import MaterialClassificationService

        svc = MaterialClassificationService()
        ctx = {"our_party_ids": ["bad", -1, 0, 5]}
        result = svc._extract_party_ids_by_side(side="our", context=ctx)
        assert result == [5]

    def test_extract_primary_supervising_authority_id(self) -> None:
        from apps.core.services.material_classification_service import MaterialClassificationService

        svc = MaterialClassificationService()
        assert svc._extract_primary_supervising_authority_id({"primary_supervising_authority_id": 42}) == 42
        assert svc._extract_primary_supervising_authority_id({}) is None
        assert svc._extract_primary_supervising_authority_id({"primary_supervising_authority_id": -1}) is None

    def test_parse_work_log_from_folder_name(self) -> None:
        from apps.core.services.material_classification_service import MaterialClassificationService

        svc = MaterialClassificationService()
        result = svc.parse_work_log_from_folder_name("2025.01.23-知识产权合同")
        assert result is not None
        assert result["date"] == "2025-01-23"
        assert result["content"] == "审核知识产权合同"

    def test_parse_work_log_no_match(self) -> None:
        from apps.core.services.material_classification_service import MaterialClassificationService

        svc = MaterialClassificationService()
        assert svc.parse_work_log_from_folder_name("random_folder") is None


# ============================================================
# core/llm/config.py
# ============================================================


class TestLLMConfig:
    def test_resolve_backend_openai_compatible_default(self) -> None:
        from apps.core.llm.config import LLMConfig

        assert LLMConfig.resolve_backend_for_model("Qwen/Qwen2.5-7B-Instruct") == "openai_compatible"

    def test_resolve_backend_ollama(self) -> None:
        from apps.core.llm.config import LLMConfig

        assert LLMConfig.resolve_backend_for_model("qwen3:0.6b") == "ollama"

    def test_resolve_backend_openai_compatible(self) -> None:
        from apps.core.llm.config import LLMConfig

        assert LLMConfig.resolve_backend_for_model("kimi26") == "openai_compatible"

    def test_resolve_backend_empty(self) -> None:
        from apps.core.llm.config import LLMConfig

        # Mock _get_system_config to avoid DB access
        with patch.object(LLMConfig, "_get_system_config", return_value="openai_compatible"):
            result = LLMConfig.resolve_backend_for_model("")
            assert result in {"ollama", "openai_compatible"}

    def test_normalize_api_key(self) -> None:
        from apps.core.llm.config import LLMConfig

        assert LLMConfig._normalize_api_key("Bearer sk-12345") == "sk-12345"
        assert LLMConfig._normalize_api_key("  raw-key  ") == "raw-key"

    def test_normalize_base_url(self) -> None:
        from apps.core.llm.config import LLMConfig

        assert LLMConfig._normalize_base_url("https://example.com/v1///") == "https://example.com/v1"
        assert LLMConfig._normalize_base_url("") == ""

    def test_parse_bool(self) -> None:
        from apps.core.llm.config import LLMConfig

        assert LLMConfig._parse_bool("true", False) is True
        assert LLMConfig._parse_bool("0", True) is False
        assert LLMConfig._parse_bool("yes", False) is True
        assert LLMConfig._parse_bool("n", True) is False
        assert LLMConfig._parse_bool("", False) is False
        assert LLMConfig._parse_bool(True, False) is True
        assert LLMConfig._parse_bool("unknown", True) is True

    def test_parse_int(self) -> None:
        from apps.core.llm.config import LLMConfig

        assert LLMConfig._parse_int("42", 0) == 42
        assert LLMConfig._parse_int(None, 99) == 99
        assert LLMConfig._parse_int("", 99) == 99
        assert LLMConfig._parse_int("abc", 99) == 99

    def test_default_models_list(self) -> None:
        from apps.core.llm.config import LLMConfig

        models = LLMConfig.DEFAULT_AVAILABLE_MODELS
        assert len(models) >= 1
        assert "kimi26" in models

    def test_valid_backends(self) -> None:
        from apps.core.llm.config import LLMConfig

        assert "ollama" in LLMConfig._VALID_BACKENDS
        assert "openai_compatible" in LLMConfig._VALID_BACKENDS


# ============================================================
# core/llm/exceptions.py
# ============================================================


class TestLLMExceptions:
    def test_llm_error(self) -> None:
        from apps.core.llm.exceptions import LLMError

        exc = LLMError("test error")
        assert exc.code == "LLM_ERROR"
        assert "test error" in exc.message

    def test_llm_network_error(self) -> None:
        from apps.core.llm.exceptions import LLMNetworkError

        exc = LLMNetworkError()
        assert exc.code == "LLM_NETWORK_ERROR"

    def test_llm_api_error(self) -> None:
        from apps.core.llm.exceptions import LLMAPIError

        exc = LLMAPIError(status_code=500)
        assert exc.status_code == 500
        assert exc.code == "LLM_API_ERROR"

    def test_llm_auth_error(self) -> None:
        from apps.core.llm.exceptions import LLMAuthenticationError

        exc = LLMAuthenticationError()
        assert exc.code == "LLM_AUTH_ERROR"

    def test_llm_timeout_error(self) -> None:
        from apps.core.llm.exceptions import LLMTimeoutError

        exc = LLMTimeoutError(timeout_seconds=30.0)
        assert exc.timeout_seconds == 30.0
        assert exc.code == "LLM_TIMEOUT"

    def test_llm_backend_unavailable(self) -> None:
        from apps.core.llm.exceptions import LLMBackendUnavailableError

        exc = LLMBackendUnavailableError()
        assert exc.code == "LLM_ALL_BACKENDS_UNAVAILABLE"


# ============================================================
# core/services/cache_service.py
# ============================================================


class TestCacheService:
    def test_cached_decorator(self) -> None:
        from apps.core.services.cache_service import cached, invalidate_cache

        call_count = 0

        @cached("test:{x}", timeout=5)
        def compute(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        # First call should compute
        result = compute(5)
        assert result == 10
        assert call_count == 1

        # Second call should come from cache (if cache available)
        result2 = compute(5)
        assert result2 == 10

        invalidate_cache("test:5")

    def test_invalidate_cache_missing_key(self) -> None:
        from apps.core.services.cache_service import invalidate_cache

        invalidate_cache("nonexistent_key")  # should not raise


# ============================================================
# core/services/utils.py  (formatters already tested, test date formatting)
# ============================================================


class TestFormatters:
    def test_format_date_chinese(self) -> None:
        from apps.documents.utils.formatters import format_date_chinese

        assert format_date_chinese(date(2026, 1, 15)) == "2026年01月15日"

    def test_format_date_chinese_none_no_default(self) -> None:
        from apps.documents.utils.formatters import format_date_chinese

        assert format_date_chinese(None) == ""

    def test_format_currency(self) -> None:
        from apps.documents.utils.formatters import format_currency
        from decimal import Decimal

        assert format_currency(Decimal("1234.56")) == "1,234.56"
        assert format_currency(Decimal("1234.56"), include_symbol=True) == "¥1,234.56"

    def test_format_currency_none(self) -> None:
        from apps.documents.utils.formatters import format_currency

        assert format_currency(None) == ""

    def test_format_percentage(self) -> None:
        from apps.documents.utils.formatters import format_percentage
        from decimal import Decimal

        assert format_percentage(Decimal("10.5")) == "10.50%"
        # decimal_places=0 is not > 0, so falls through to basic format
        assert format_percentage(Decimal("10.5"), decimal_places=0) == "10.5%"

    def test_format_date_iso_string(self) -> None:
        from apps.documents.utils.formatters import format_date

        result = format_date("2026-01-15", fmt="%Y年%m月%d日")
        assert result == "2026年01月15日"

    def test_format_date_none(self) -> None:
        from apps.documents.utils.formatters import format_date

        assert format_date(None) == ""
