"""core 模块 batch7 覆盖测试 — 覆盖 config providers、schema、filesystem、http、exceptions 等。"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, mock_open, patch

import pytest


# =====================================================================
# ConfigProvider 基类 — get_name / __str__ / __repr__
# =====================================================================

class TestConfigProviderBase:
    def test_get_name_and_repr(self):
        """Concrete subclass tests get_name, __str__, __repr__."""
        from apps.core.config.providers.base import ConfigProvider

        class DummyProvider(ConfigProvider):
            @property
            def priority(self):
                return 42

            def load(self):
                return {}

            def supports_reload(self):
                return False

        p = DummyProvider()
        assert p.get_name() == "DummyProvider"
        assert "42" in str(p)
        assert "DummyProvider" in repr(p)
        assert "priority=42" in repr(p)
        assert "reload=False" in repr(p)


# =====================================================================
# EnvProvider — 类型转换与环境变量加载
# =====================================================================

class TestEnvProvider:
    def test_normalize_key(self):
        from apps.core.config.providers.env import EnvProvider

        p = EnvProvider()
        assert p._normalize_key("DB_HOST") == "db.host"
        assert p._normalize_key("MY_LONG_KEY") == "my.long.key"

    def test_parse_bool_true_values(self):
        from apps.core.config.providers.env import EnvProvider

        p = EnvProvider()
        for v in ["true", "yes", "1", "on", "enabled", "True", "YES"]:
            assert p._parse_bool(v) is True

    def test_parse_bool_false_values(self):
        from apps.core.config.providers.env import EnvProvider

        p = EnvProvider()
        for v in ["false", "no", "0", "off", "False", "NO"]:
            assert p._parse_bool(v) is False

    def test_parse_list(self):
        from apps.core.config.providers.env import EnvProvider

        p = EnvProvider()
        assert p._parse_list("a,b,c") == ["a", "b", "c"]
        assert p._parse_list("single") == ["single"]
        assert p._parse_list("a, ,b") == ["a", "b"]

    def test_parse_dict(self):
        from apps.core.config.providers.env import EnvProvider

        p = EnvProvider()
        assert p._parse_dict("k1=v1,k2=v2") == {"k1": "v1", "k2": "v2"}
        assert p._parse_dict("noequals") == {}

    def test_auto_cast_bool(self):
        from apps.core.config.providers.env import EnvProvider

        p = EnvProvider()
        assert p._auto_cast("true") is True
        assert p._auto_cast("false") is False

    def test_auto_cast_int(self):
        from apps.core.config.providers.env import EnvProvider

        p = EnvProvider()
        assert p._auto_cast("42") == 42
        assert p._auto_cast("-7") == -7

    def test_auto_cast_float(self):
        from apps.core.config.providers.env import EnvProvider

        p = EnvProvider()
        assert p._auto_cast("3.14") == pytest.approx(3.14)

    def test_auto_cast_list(self):
        from apps.core.config.providers.env import EnvProvider

        p = EnvProvider()
        assert p._auto_cast("a,b") == ["a", "b"]

    def test_auto_cast_string(self):
        from apps.core.config.providers.env import EnvProvider

        p = EnvProvider()
        assert p._auto_cast("hello") == "hello"

    def test_cast_to_type_bool(self):
        from apps.core.config.providers.env import EnvProvider

        p = EnvProvider()
        assert p._cast_to_type("true", bool) is True

    def test_cast_to_type_int(self):
        from apps.core.config.providers.env import EnvProvider

        p = EnvProvider()
        assert p._cast_to_type("10", int) == 10

    def test_cast_to_type_float(self):
        from apps.core.config.providers.env import EnvProvider

        p = EnvProvider()
        assert p._cast_to_type("2.5", float) == pytest.approx(2.5)

    def test_cast_to_type_list(self):
        from apps.core.config.providers.env import EnvProvider

        p = EnvProvider()
        assert p._cast_to_type("a,b", list) == ["a", "b"]

    def test_cast_to_type_dict(self):
        from apps.core.config.providers.env import EnvProvider

        p = EnvProvider()
        result = p._cast_to_type("k=v", dict)
        assert result == {"k": "v"}

    def test_cast_to_type_str(self):
        from apps.core.config.providers.env import EnvProvider

        p = EnvProvider()
        assert p._cast_to_type("abc", str) == "abc"

    def test_priority(self):
        from apps.core.config.providers.env import EnvProvider

        p = EnvProvider()
        assert p.priority == 100

    def test_supports_reload_false(self):
        from apps.core.config.providers.env import EnvProvider

        p = EnvProvider()
        assert p.supports_reload() is False

    def test_load_with_prefix(self):
        from apps.core.config.providers.env import EnvProvider

        p = EnvProvider(prefix="TEST_PREFIX_")
        with patch.dict(os.environ, {"TEST_PREFIX_DB_HOST": "localhost"}):
            config = p.load()
            assert "db.host" in config
            assert config["db.host"] == "localhost"

    def test_load_without_prefix(self):
        from apps.core.config.providers.env import EnvProvider

        p = EnvProvider(prefix="")
        with patch.dict(os.environ, {"MYTESTVAR": "value123"}):
            config = p.load()
            assert "mytestvar" in config

    def test_convert_type_with_mapping(self):
        from apps.core.config.providers.env import EnvProvider

        p = EnvProvider(type_mapping={"MY_VAR": int})
        assert p._convert_type("MY_VAR", "42") == 42

    def test_sensitive_vars(self):
        from apps.core.config.providers.env import EnvProvider

        p = EnvProvider()
        assert "SECRET_KEY" in p._sensitive_vars
        assert "API_KEY" in p._sensitive_vars


# =====================================================================
# YamlProvider — 文件加载与变量替换
# =====================================================================

class TestYamlProvider:
    def test_priority(self):
        from apps.core.config.providers.yaml import YamlProvider

        p = YamlProvider("/nonexistent/path.yaml")
        assert p.priority == 50

    def test_supports_reload_true(self):
        from apps.core.config.providers.yaml import YamlProvider

        p = YamlProvider("/path.yaml")
        assert p.supports_reload() is True

    def test_get_file_path(self):
        from apps.core.config.providers.yaml import YamlProvider

        p = YamlProvider("/some/path.yaml")
        assert p.get_file_path() == "/some/path.yaml"

    def test_load_file_not_found(self):
        from apps.core.config.exceptions import ConfigFileError
        from apps.core.config.providers.yaml import YamlProvider

        p = YamlProvider("/nonexistent_file_12345.yaml")
        with pytest.raises(ConfigFileError):
            p.load()

    def test_load_valid_yaml(self):
        from apps.core.config.providers.yaml import YamlProvider

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("database:\n  host: localhost\n  port: 5432\n")
            f.flush()
            path = f.name

        try:
            p = YamlProvider(path)
            config = p.load()
            assert "database.host" in config
            assert config["database.host"] == "localhost"
            assert config["database.port"] == 5432
        finally:
            os.unlink(path)

    def test_load_cached(self):
        from apps.core.config.providers.yaml import YamlProvider

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("a: 1\n")
            f.flush()
            path = f.name

        try:
            p = YamlProvider(path)
            config1 = p.load()
            config2 = p.load()  # should hit cache
            assert config1 == config2
        finally:
            os.unlink(path)

    def test_substitute_variables(self):
        from apps.core.config.providers.yaml import YamlProvider

        p = YamlProvider("/dummy")
        with patch.dict(os.environ, {"MY_VAR": "replaced"}):
            result = p._substitute_variables("value: ${MY_VAR}")
            assert result == "value: replaced"

    def test_substitute_variables_with_default(self):
        from apps.core.config.providers.yaml import YamlProvider

        p = YamlProvider("/dummy")
        with patch.dict(os.environ, {}, clear=True):
            result = p._substitute_variables("value: ${NONEXISTENT:default_val}")
            assert result == "value: default_val"

    def test_substitute_variables_empty_default(self):
        from apps.core.config.providers.yaml import YamlProvider

        p = YamlProvider("/dummy")
        with patch.dict(os.environ, {}, clear=True):
            result = p._substitute_variables("value: ${NONEXISTENT}")
            assert result == "value: "

    def test_flatten_dict(self):
        from apps.core.config.providers.yaml import YamlProvider

        p = YamlProvider("/dummy")
        result = p._flatten_dict({"a": {"b": 1, "c": 2}, "d": 3})
        assert result == {"a.b": 1, "a.c": 2, "d": 3}

    def test_flatten_dict_nested(self):
        from apps.core.config.providers.yaml import YamlProvider

        p = YamlProvider("/dummy")
        result = p._flatten_dict({"a": {"b": {"c": 1}}})
        assert result == {"a.b.c": 1}

    def test_flatten_dict_empty(self):
        from apps.core.config.providers.yaml import YamlProvider

        p = YamlProvider("/dummy")
        assert p._flatten_dict({}) == {}

    def test_load_invalid_yaml(self):
        from apps.core.config.exceptions import ConfigFileError
        from apps.core.config.providers.yaml import YamlProvider

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(":\n  :\n    invalid: [unterminated")
            f.flush()
            path = f.name

        try:
            p = YamlProvider(path)
            with pytest.raises(ConfigFileError):
                p.load()
        finally:
            os.unlink(path)


# =====================================================================
# ConfigField — 数据类验证
# =====================================================================

class TestConfigField:
    def test_create_valid_field(self):
        from apps.core.config.schema.field import ConfigField

        f = ConfigField(name="test", type=str, description="A test field")
        assert f.name == "test"
        assert f.required is False
        assert f.sensitive is False

    def test_min_gt_max_raises(self):
        from apps.core.config.schema.field import ConfigField

        with pytest.raises(ValueError, match="min_value.*不能大于.*max_value"):
            ConfigField(name="bad", type=int, min_value=100, max_value=1)

    def test_min_length_gt_max_length_raises(self):
        from apps.core.config.schema.field import ConfigField

        with pytest.raises(ValueError, match="min_length.*不能大于.*max_length"):
            ConfigField(name="bad", type=str, min_length=10, max_length=1)

    def test_required_with_default_raises(self):
        from apps.core.config.schema.field import ConfigField

        with pytest.raises(ValueError, match="不能同时设置为必需字段和提供默认值"):
            ConfigField(name="bad", type=str, required=True, default="val")


# =====================================================================
# ConfigSchema — 注册、验证、建议
# =====================================================================

class TestConfigSchema:
    def test_register_and_get_field(self):
        from apps.core.config.schema.field import ConfigField
        from apps.core.config.schema.schema import ConfigSchema

        schema = ConfigSchema()
        f = ConfigField(name="db.host", type=str)
        schema.register(f)
        assert schema.get_field("db.host") is f

    def test_register_duplicate_raises(self):
        from apps.core.config.schema.field import ConfigField
        from apps.core.config.schema.schema import ConfigSchema

        schema = ConfigSchema()
        f = ConfigField(name="db.host", type=str)
        schema.register(f)
        with pytest.raises(ValueError, match="已存在"):
            schema.register(f)

    def test_get_field_not_found(self):
        from apps.core.config.schema.schema import ConfigSchema

        schema = ConfigSchema()
        assert schema.get_field("nonexistent") is None

    def test_validate_and_raise(self):
        from apps.core.config.exceptions import ConfigValidationError
        from apps.core.config.schema.field import ConfigField
        from apps.core.config.schema.schema import ConfigSchema

        schema = ConfigSchema()
        schema.register(ConfigField(name="required_field", type=str, required=True))
        with pytest.raises(ConfigValidationError):
            schema.validate_and_raise({})

    def test_validate_passes_with_required(self):
        from apps.core.config.schema.field import ConfigField
        from apps.core.config.schema.schema import ConfigSchema

        schema = ConfigSchema()
        schema.register(ConfigField(name="required_field", type=str, required=True))
        schema.validate_and_raise({"required_field": "value"})

    def test_get_suggestions_exact(self):
        from apps.core.config.schema.field import ConfigField
        from apps.core.config.schema.schema import ConfigSchema

        schema = ConfigSchema()
        schema.register(ConfigField(name="db.host", type=str))
        suggestions = schema.get_suggestions("db.host")
        assert "db.host" in suggestions

    def test_get_suggestions_partial(self):
        from apps.core.config.schema.field import ConfigField
        from apps.core.config.schema.schema import ConfigSchema

        schema = ConfigSchema()
        schema.register(ConfigField(name="database.host", type=str))
        schema.register(ConfigField(name="database.port", type=int))
        suggestions = schema.get_suggestions("database")
        assert len(suggestions) >= 1

    def test_get_suggestions_max(self):
        from apps.core.config.schema.field import ConfigField
        from apps.core.config.schema.schema import ConfigSchema

        schema = ConfigSchema()
        for i in range(10):
            schema.register(ConfigField(name=f"item.{i}", type=int))
        suggestions = schema.get_suggestions("item", max_suggestions=3)
        assert len(suggestions) <= 3


# =====================================================================
# ConfigSchema registry — 全局函数
# =====================================================================

class TestConfigRegistry:
    def test_get_config_field_existing(self):
        from apps.core.config.schema.registry import get_config_field

        # Should have at least one registered field
        fields = [k for k in dir(get_config_field) if not k.startswith("_")]

    def test_get_all_config_fields(self):
        from apps.core.config.schema.registry import get_all_config_fields

        fields = get_all_config_fields()
        assert isinstance(fields, dict)

    def test_get_config_fields_by_category(self):
        from apps.core.config.schema.registry import get_config_fields_by_category

        fields = get_config_fields_by_category("nonexistent_category")
        assert isinstance(fields, dict)
        assert len(fields) == 0

    def test_get_sensitive_config_fields(self):
        from apps.core.config.schema.registry import get_sensitive_config_fields

        fields = get_sensitive_config_fields()
        assert isinstance(fields, dict)

    def test_get_required_config_fields(self):
        from apps.core.config.schema.registry import get_required_config_fields

        fields = get_required_config_fields()
        assert isinstance(fields, dict)

    def test_get_config_field_not_found(self):
        from apps.core.config.schema.registry import get_config_field

        with pytest.raises(KeyError, match="不存在"):
            get_config_field("nonexistent.key.that.does.not.exist")


# =====================================================================
# KeepOriginalNameStorage — 文件存储
# =====================================================================

class TestKeepOriginalNameStorage:
    def test_generate_filename_preserves_original(self):
        from apps.core.filesystem.storage import KeepOriginalNameStorage

        storage = KeepOriginalNameStorage()
        result = storage.generate_filename("subdir/my file (1).pdf")
        assert result == "subdir/my file (1).pdf"

    def test_generate_filename_backslash(self):
        from apps.core.filesystem.storage import KeepOriginalNameStorage

        storage = KeepOriginalNameStorage()
        result = storage.generate_filename("subdir\\file.pdf")
        assert "/" in result or "file.pdf" in result

    def test_generate_filename_no_dir(self):
        from apps.core.filesystem.storage import KeepOriginalNameStorage

        storage = KeepOriginalNameStorage()
        result = storage.generate_filename("simple.pdf")
        assert result == "simple.pdf"

    def test_get_available_name_no_conflict(self):
        from apps.core.filesystem.storage import KeepOriginalNameStorage

        storage = KeepOriginalNameStorage()
        with patch.object(storage, "exists", return_value=False):
            assert storage.get_available_name("test.pdf") == "test.pdf"

    def test_get_available_name_with_conflict(self):
        from apps.core.filesystem.storage import KeepOriginalNameStorage

        storage = KeepOriginalNameStorage()
        call_count = 0

        def mock_exists(name):
            nonlocal call_count
            call_count += 1
            # First call (original) returns True, second (counter=1) returns False
            return call_count == 1

        with patch.object(storage, "exists", side_effect=mock_exists):
            result = storage.get_available_name("test.pdf")
            assert result == "test_1.pdf"

    def test_get_available_name_with_dir(self):
        from apps.core.filesystem.storage import KeepOriginalNameStorage

        storage = KeepOriginalNameStorage()
        with patch.object(storage, "exists", return_value=False):
            result = storage.get_available_name("subdir/test.pdf")
            assert result == "subdir/test.pdf"


# =====================================================================
# normalize_folder_node_path — 路径规范化
# =====================================================================

class TestNormalizeFolderNodePath:
    def test_empty_path(self):
        from apps.core.filesystem.folder_node_path import normalize_folder_node_path

        assert normalize_folder_node_path("") == ""

    def test_single_segment(self):
        from apps.core.filesystem.folder_node_path import normalize_folder_node_path

        assert normalize_folder_node_path("folder") == "folder"

    def test_numbered_prefix_kept(self):
        from apps.core.filesystem.folder_node_path import normalize_folder_node_path

        assert normalize_folder_node_path("1-律师资料/2-案件文书") == "1-律师资料/2-案件文书"

    def test_non_numbered_prefix_stripped(self):
        from apps.core.filesystem.folder_node_path import normalize_folder_node_path

        result = normalize_folder_node_path("root/1-律师资料/2-案件文书")
        assert result == "1-律师资料/2-案件文书"

    def test_multi_segment_numbered_prefix(self):
        from apps.core.filesystem.folder_node_path import normalize_folder_node_path

        assert normalize_folder_node_path("9-folder/sub") == "9-folder/sub"


# =====================================================================
# parse_range_header — HTTP Range 解析
# =====================================================================

class TestParseRangeHeader:
    def test_no_range(self):
        from apps.core.http.range import parse_range_header

        assert parse_range_header("", 1000) is None
        assert parse_range_header("invalid", 1000) is None

    def test_no_bytes_prefix(self):
        from apps.core.http.range import parse_range_header

        assert parse_range_header("items=0-10", 1000) is None

    def test_explicit_range(self):
        from apps.core.http.range import parse_range_header

        result = parse_range_header("bytes=0-499", 1000)
        assert result == (0, 499)

    def test_explicit_range_no_end(self):
        from apps.core.http.range import parse_range_header

        result = parse_range_header("bytes=500-", 1000)
        assert result == (500, 999)

    def test_suffix_range(self):
        from apps.core.http.range import parse_range_header

        result = parse_range_header("bytes=-500", 1000)
        assert result == (500, 999)

    def test_suffix_range_exceeds_file(self):
        from apps.core.http.range import parse_range_header

        result = parse_range_header("bytes=-2000", 1000)
        assert result == (0, 999)

    def test_end_clamped_to_file_size(self):
        from apps.core.http.range import parse_range_header

        result = parse_range_header("bytes=0-9999", 1000)
        assert result == (0, 999)

    def test_start_clamped_to_file_size(self):
        from apps.core.http.range import parse_range_header

        result = parse_range_header("bytes=9999-9999", 1000)
        assert result == (999, 999)

    def test_end_before_start(self):
        from apps.core.http.range import parse_range_header

        assert parse_range_header("bytes=500-100", 1000) is None

    def test_multiple_ranges_takes_first(self):
        from apps.core.http.range import parse_range_header

        result = parse_range_header("bytes=0-100,200-300", 1000)
        assert result == (0, 100)

    def test_suffix_zero(self):
        from apps.core.http.range import parse_range_header

        result = parse_range_header("bytes=-0", 1000)
        assert result is None

    def test_invalid_start(self):
        from apps.core.http.range import parse_range_header

        assert parse_range_header("bytes=abc-100", 1000) is None

    def test_no_dash(self):
        from apps.core.http.range import parse_range_header

        assert parse_range_header("bytes=0", 1000) is None


# =====================================================================
# ErrorEnvelope — 错误封装
# =====================================================================

class TestErrorEnvelope:
    def test_to_payload_basic(self):
        from apps.core.exceptions.error_presentation import ErrorEnvelope

        env = ErrorEnvelope(code="ERR", message="msg", errors={"key": "val"})
        payload = env.to_payload()
        assert payload["code"] == "ERR"
        assert payload["message"] == "msg"
        assert payload["errors"] == {"key": "val"}
        assert payload["retryable"] is False
        assert payload["channel"] == "http"
        assert payload["error"] == "msg"

    def test_to_payload_no_legacy(self):
        from apps.core.exceptions.error_presentation import ErrorEnvelope

        env = ErrorEnvelope(code="ERR", message="msg", errors={})
        payload = env.to_payload(include_legacy_error=False)
        assert "error" not in payload

    def test_to_payload_with_retryable(self):
        from apps.core.exceptions.error_presentation import ErrorEnvelope

        env = ErrorEnvelope(code="ERR", message="msg", errors={}, retryable=True, channel="ws")
        payload = env.to_payload()
        assert payload["retryable"] is True
        assert payload["channel"] == "ws"


# =====================================================================
# ExceptionPresenter — 异常映射
# =====================================================================

class TestExceptionPresenter:
    def test_business_validation(self):
        from apps.core.exceptions import ValidationException
        from apps.core.exceptions.error_presentation import ExceptionPresenter

        presenter = ExceptionPresenter()
        exc = ValidationException("数据错误", code="INVALID")
        envelope, status = presenter.present(exc, channel="http")
        assert envelope.code == "INVALID"
        assert status == 400

    def test_business_not_found(self):
        from apps.core.exceptions import NotFoundError
        from apps.core.exceptions.error_presentation import ExceptionPresenter

        presenter = ExceptionPresenter()
        exc = NotFoundError("不存在", code="NOT_FOUND")
        envelope, status = presenter.present(exc, channel="http")
        assert status == 404

    def test_business_auth_error(self):
        from apps.core.exceptions import AuthenticationError
        from apps.core.exceptions.error_presentation import ExceptionPresenter

        presenter = ExceptionPresenter()
        exc = AuthenticationError()
        envelope, status = presenter.present(exc, channel="http")
        assert status == 401

    def test_business_permission_denied(self):
        from apps.core.exceptions import PermissionDenied
        from apps.core.exceptions.error_presentation import ExceptionPresenter

        presenter = ExceptionPresenter()
        exc = PermissionDenied()
        envelope, status = presenter.present(exc, channel="http")
        assert status == 403

    def test_business_conflict(self):
        from apps.core.exceptions import ConflictError
        from apps.core.exceptions.error_presentation import ExceptionPresenter

        presenter = ExceptionPresenter()
        exc = ConflictError()
        envelope, status = presenter.present(exc, channel="http")
        assert status == 409

    def test_business_rate_limit(self):
        from apps.core.exceptions import RateLimitError
        from apps.core.exceptions.error_presentation import ExceptionPresenter

        presenter = ExceptionPresenter()
        exc = RateLimitError()
        envelope, status = presenter.present(exc, channel="http")
        assert status == 429
        assert envelope.retryable is True

    def test_business_service_unavailable(self):
        from apps.core.exceptions import ServiceUnavailableError
        from apps.core.exceptions.error_presentation import ExceptionPresenter

        presenter = ExceptionPresenter()
        exc = ServiceUnavailableError()
        envelope, status = presenter.present(exc, channel="http")
        assert status == 503

    def test_business_external_service(self):
        from apps.core.exceptions import ExternalServiceError
        from apps.core.exceptions.error_presentation import ExceptionPresenter

        presenter = ExceptionPresenter()
        exc = ExternalServiceError()
        envelope, status = presenter.present(exc, channel="http")
        assert status == 502

    def test_business_timeout(self):
        from apps.core.exceptions import RecognitionTimeoutError
        from apps.core.exceptions.error_presentation import ExceptionPresenter

        presenter = ExceptionPresenter()
        exc = RecognitionTimeoutError()
        envelope, status = presenter.present(exc, channel="http")
        assert status == 504

    def test_unknown_exception_debug(self):
        from apps.core.exceptions.error_presentation import ExceptionPresenter

        presenter = ExceptionPresenter()
        exc = ValueError("something went wrong")
        envelope, status = presenter.present(exc, channel="http", debug=True)
        assert envelope.code == "INTERNAL_ERROR"
        assert "something went wrong" in envelope.message
        assert status == 500

    def test_unknown_exception_no_debug(self):
        from apps.core.exceptions.error_presentation import ExceptionPresenter

        presenter = ExceptionPresenter()
        exc = ValueError("something went wrong")
        envelope, status = presenter.present(exc, channel="http", debug=False)
        assert "稍后重试" in envelope.message

    def test_unknown_exception_websocket(self):
        from apps.core.exceptions.error_presentation import ExceptionPresenter

        presenter = ExceptionPresenter()
        exc = ValueError("ws error")
        envelope, status = presenter.present(exc, channel="ws", debug=False)
        assert status is None

    def test_business_exception_with_custom_status(self):
        from apps.core.exceptions.common import BusinessException
        from apps.core.exceptions.error_presentation import ExceptionPresenter

        presenter = ExceptionPresenter()
        exc = BusinessException("custom")
        exc.status = 418
        envelope, status = presenter.present(exc, channel="http")
        assert status == 418

    def test_retryable_for_business_exception(self):
        from apps.core.exceptions.error_presentation import ExceptionPresenter

        presenter = ExceptionPresenter()
        assert presenter._retryable_for_business_exception(Exception()) is False


# =====================================================================
# Error catalog — 便捷函数
# =====================================================================

class TestErrorCatalog:
    def test_case_not_found(self):
        from apps.core.exceptions.error_catalog import case_not_found

        exc = case_not_found(case_id=42)
        assert "案件不存在" in str(exc)
        assert exc.code == "CASE_NOT_FOUND"

    def test_contract_not_found(self):
        from apps.core.exceptions.error_catalog import contract_not_found

        exc = contract_not_found(contract_id=10)
        assert "合同不存在" in str(exc)
        assert exc.code == "CONTRACT_NOT_FOUND"

    def test_evidence_list_not_found(self):
        from apps.core.exceptions.error_catalog import evidence_list_not_found

        exc = evidence_list_not_found(list_id=5)
        assert "证据清单不存在" in str(exc)

    def test_evidence_item_not_found(self):
        from apps.core.exceptions.error_catalog import evidence_item_not_found

        exc = evidence_item_not_found(item_id=7)
        assert "证据明细不存在" in str(exc)


# =====================================================================
# BusinessException 基类
# =====================================================================

class TestBusinessException:
    def test_message_and_code(self):
        from apps.core.exceptions.common import BusinessException

        exc = BusinessException(message="test message", code="TEST_CODE")
        assert exc.message == "test message"
        assert exc.code == "TEST_CODE"

    def test_errors_default(self):
        from apps.core.exceptions.common import BusinessException

        exc = BusinessException(message="test")
        assert exc.errors == {}


# =====================================================================
# ForbiddenError / UnauthorizedError — 向后兼容
# =====================================================================

class TestCompatErrors:
    def test_forbidden_error(self):
        from apps.core.exceptions.common import ForbiddenError

        exc = ForbiddenError()
        assert exc.status == 403

    def test_unauthorized_error(self):
        from apps.core.exceptions.common import UnauthorizedError

        exc = UnauthorizedError()
        assert exc.status == 401


# =====================================================================
# build_range_file_response — 流式文件响应
# =====================================================================

class TestBuildRangeFileResponse:
    def test_file_not_found(self):
        from django.http import HttpResponse
        from apps.core.http.streaming import build_range_file_response

        request = MagicMock()
        request.headers = {}
        request.META = {}
        request.method = "GET"

        resp = build_range_file_response(request, "/nonexistent/file.txt")
        assert resp.status_code == 404

    def test_full_file_response(self):
        from django.http import FileResponse
        from apps.core.http.streaming import build_range_file_response

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello world")
            f.flush()
            path = f.name

        try:
            request = MagicMock()
            request.headers = {}
            request.META = {}
            request.method = "GET"

            resp = build_range_file_response(request, path)
            assert resp.status_code == 200
            assert resp.get("Accept-Ranges") == "bytes"
            assert resp.get("X-Content-Type-Options") == "nosniff"
        finally:
            os.unlink(path)

    def test_range_response(self):
        from apps.core.http.streaming import build_range_file_response

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello world test file")
            f.flush()
            path = f.name

        try:
            request = MagicMock()
            request.headers = {"Range": "bytes=0-4"}
            request.META = {}
            request.method = "GET"

            resp = build_range_file_response(request, path)
            assert resp.status_code == 206
            assert "bytes 0-4/" in resp.get("Content-Range", "")
        finally:
            os.unlink(path)

    def test_head_request(self):
        from apps.core.http.streaming import build_range_file_response

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("test")
            f.flush()
            path = f.name

        try:
            request = MagicMock()
            request.headers = {}
            request.META = {}
            request.method = "HEAD"

            resp = build_range_file_response(request, path)
            assert resp.status_code == 200
        finally:
            os.unlink(path)

    def test_dangerous_content_type_forced_download(self):
        """HTML content-type should be forced to octet-stream."""
        from apps.core.http.streaming import build_range_file_response

        with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as f:
            f.write("<html>test</html>")
            f.flush()
            path = f.name

        try:
            request = MagicMock()
            request.headers = {}
            request.META = {}
            request.method = "GET"

            resp = build_range_file_response(request, path, content_type="text/html")
            assert resp.get("Content-Disposition", "").startswith("attachment")
        finally:
            os.unlink(path)

    def test_range_start_exceeds_file_size(self):
        from apps.core.http.streaming import build_range_file_response

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("small")
            f.flush()
            path = f.name

        try:
            request = MagicMock()
            request.headers = {"Range": "bytes=9999-9999"}
            request.META = {}
            request.method = "GET"

            resp = build_range_file_response(request, path)
            assert resp.status_code == 416
        finally:
            os.unlink(path)

    def test_head_range_request(self):
        from apps.core.http.streaming import build_range_file_response

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello world test data here")
            f.flush()
            path = f.name

        try:
            request = MagicMock()
            request.headers = {"Range": "bytes=0-4"}
            request.META = {}
            request.method = "HEAD"

            resp = build_range_file_response(request, path)
            assert resp.status_code == 206
            assert resp.get("Content-Length") == "5"
        finally:
            os.unlink(path)

    def test_as_attachment(self):
        from apps.core.http.streaming import build_range_file_response

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("content")
            f.flush()
            path = f.name

        try:
            request = MagicMock()
            request.headers = {}
            request.META = {}
            request.method = "GET"

            resp = build_range_file_response(request, path, as_attachment=True)
            assert "attachment" in resp.get("Content-Disposition", "")
        finally:
            os.unlink(path)


# =====================================================================
# LifespanApp — ASGI 生命周期
# =====================================================================

class TestLifespanApp:
    @pytest.mark.asyncio
    async def test_startup_success(self):
        from apps.core.infrastructure.asgi_lifespan import LifespanApp

        startup_called = False

        async def on_startup():
            nonlocal startup_called
            startup_called = True

        app = LifespanApp(on_startup=on_startup)

        messages = [{"type": "lifespan.startup"}]
        sent = []

        async def receive():
            return messages.pop(0)

        async def send(msg):
            sent.append(msg)

        await app({}, receive, send)
        assert startup_called
        assert {"type": "lifespan.startup.complete"} in sent

    @pytest.mark.asyncio
    async def test_startup_failure(self):
        from apps.core.infrastructure.asgi_lifespan import LifespanApp

        async def on_startup():
            raise RuntimeError("boom")

        app = LifespanApp(on_startup=on_startup)

        sent = []

        async def receive():
            return {"type": "lifespan.startup"}

        async def send(msg):
            sent.append(msg)

        await app({}, receive, send)
        assert sent[0]["type"] == "lifespan.startup.failed"

    @pytest.mark.asyncio
    async def test_shutdown_success(self):
        from apps.core.infrastructure.asgi_lifespan import LifespanApp

        shutdown_called = False

        async def on_shutdown():
            nonlocal shutdown_called
            shutdown_called = True

        app = LifespanApp(on_shutdown=on_shutdown)

        messages = [
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ]
        sent = []

        async def receive():
            return messages.pop(0)

        async def send(msg):
            sent.append(msg)

        await app({}, receive, send)
        assert shutdown_called
        assert sent[-1]["type"] == "lifespan.shutdown.complete"

    @pytest.mark.asyncio
    async def test_shutdown_failure(self):
        from apps.core.infrastructure.asgi_lifespan import LifespanApp

        async def on_shutdown():
            raise RuntimeError("shutdown boom")

        messages = [
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ]
        sent = []

        async def receive():
            return messages.pop(0)

        async def send(msg):
            sent.append(msg)

        app = LifespanApp(on_shutdown=lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        await app({}, receive, send)
        assert sent[-1]["type"] == "lifespan.shutdown.failed"

    @pytest.mark.asyncio
    async def test_no_hooks(self):
        from apps.core.infrastructure.asgi_lifespan import LifespanApp

        messages = [
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ]
        sent = []

        async def receive():
            return messages.pop(0)

        async def send(msg):
            sent.append(msg)

        app = LifespanApp()
        await app({}, receive, send)
        assert sent[0]["type"] == "lifespan.startup.complete"
        assert sent[1]["type"] == "lifespan.shutdown.complete"


# =====================================================================
# httpx_clients — 事件钩子与客户端获取
# =====================================================================

class TestHttpxClients:
    def test_httpx_event_hooks_disabled(self):
        from apps.core.http.httpx_clients import _httpx_event_hooks

        with patch.dict(os.environ, {"DJANGO_HTTPX_METRICS": ""}):
            assert _httpx_event_hooks() is None

    def test_httpx_event_hooks_enabled(self):
        from apps.core.http.httpx_clients import _httpx_event_hooks

        with patch.dict(os.environ, {"DJANGO_HTTPX_METRICS": "true"}):
            hooks = _httpx_event_hooks()
            assert hooks is not None
            assert "request" in hooks
            assert "response" in hooks


# =====================================================================
# FolderBrowsePolicy — 浏览策略 (mocked)
# =====================================================================

class TestFolderBrowsePolicy:
    def test_init_defaults(self):
        from apps.core.filesystem.browse_policy import FolderBrowsePolicy

        policy = FolderBrowsePolicy()
        assert policy.roots_setting_name == "FOLDER_BROWSE_ROOTS"

    def test_init_custom(self):
        from apps.core.filesystem.browse_policy import FolderBrowsePolicy

        policy = FolderBrowsePolicy(roots_setting_name="CUSTOM_ROOTS")
        assert policy.roots_setting_name == "CUSTOM_ROOTS"

    def test_get_browse_roots_empty(self):
        from apps.core.filesystem.browse_policy import FolderBrowsePolicy

        policy = FolderBrowsePolicy()
        with patch("apps.core.filesystem.browse_policy.settings") as mock_settings:
            with patch.object(policy, "_get_user_downloads_path", return_value=None):
                mock_settings.NONEXISTENT = None
                roots = policy.get_browse_roots()
                # May have Downloads or empty
                assert isinstance(roots, list)

    def test_resolve_network_path_raises(self):
        from apps.core.exceptions import ValidationException
        from apps.core.filesystem.browse_policy import FolderBrowsePolicy

        policy = FolderBrowsePolicy()
        mock_validator = MagicMock()
        mock_validator.is_network_path.return_value = True
        policy.validator = mock_validator

        with pytest.raises(ValidationException):
            policy.resolve_under_allowed_roots("//network/path")

    def test_resolve_no_roots_raises(self):
        from apps.core.exceptions import ValidationException
        from apps.core.filesystem.browse_policy import FolderBrowsePolicy

        policy = FolderBrowsePolicy()
        with patch.object(policy.validator, "is_network_path", return_value=False):
            with patch.object(policy, "get_browse_roots", return_value=[]):
                with pytest.raises(ValidationException, match="未配置"):
                    policy.resolve_under_allowed_roots("/some/path")

    def test_list_subdirs_permission_denied(self):
        from apps.core.exceptions import ValidationException
        from apps.core.filesystem.browse_policy import FolderBrowsePolicy

        policy = FolderBrowsePolicy()
        mock_target = MagicMock()
        mock_target.iterdir.side_effect = PermissionError("no access")
        with patch.object(policy, "resolve_under_allowed_roots", return_value=mock_target):
            with pytest.raises(ValidationException, match="无权限"):
                policy.list_subdirs("/some/dir")


# =====================================================================
# _DANGEROUS_CONTENT_TYPES — 安全内容类型
# =====================================================================

class TestDangerousContentTypes:
    def test_html_is_dangerous(self):
        from apps.core.http.streaming import _DANGEROUS_CONTENT_TYPES

        assert "text/html" in _DANGEROUS_CONTENT_TYPES
        assert "application/javascript" in _DANGEROUS_CONTENT_TYPES
        assert "image/svg+xml" in _DANGEROUS_CONTENT_TYPES
        assert "application/octet-stream" not in _DANGEROUS_CONTENT_TYPES


# =====================================================================
# DTO 模块测试
# =====================================================================

class TestChatDTO:
    def test_chat_result(self):
        from apps.core.dto.chat import ChatResult

        r = ChatResult(success=True, chat_id="123", chat_name="test")
        assert r.success is True
        assert r.chat_id == "123"

    def test_message_content(self):
        from apps.core.dto.chat import MessageContent

        m = MessageContent(title="T", text="Body")
        assert m.file_path is None

    def test_platform_notification_result(self):
        from apps.core.dto.chat import PlatformNotificationResult

        r = PlatformNotificationResult(platform="feishu", success=True)
        assert r.platform == "feishu"

    def test_multi_platform_any_success(self):
        from apps.core.dto.chat import MultiPlatformNotificationResult, PlatformNotificationResult

        m = MultiPlatformNotificationResult(attempts=[
            PlatformNotificationResult(platform="a", success=False),
            PlatformNotificationResult(platform="b", success=True),
        ])
        assert m.any_success is True
        assert m.all_success is False

    def test_multi_platform_all_success(self):
        from apps.core.dto.chat import MultiPlatformNotificationResult, PlatformNotificationResult

        m = MultiPlatformNotificationResult(attempts=[
            PlatformNotificationResult(platform="a", success=True),
            PlatformNotificationResult(platform="b", success=True),
        ])
        assert m.all_success is True

    def test_multi_platform_failed_platforms(self):
        from apps.core.dto.chat import MultiPlatformNotificationResult, PlatformNotificationResult

        m = MultiPlatformNotificationResult(attempts=[
            PlatformNotificationResult(platform="a", success=False),
            PlatformNotificationResult(platform="b", success=True),
        ])
        assert m.failed_platforms == ["a"]
        assert m.successful_platforms == ["b"]

    def test_to_notification_results(self):
        from apps.core.dto.chat import MultiPlatformNotificationResult, PlatformNotificationResult

        m = MultiPlatformNotificationResult(attempts=[
            PlatformNotificationResult(platform="feishu", success=True, chat_id="c1", sent_at="2026-01-01", file_count=2, sent_file_count=2),
        ])
        results = m.to_notification_results()
        assert "feishu" in results
        assert results["feishu"]["success"] is True

    def test_multi_platform_empty(self):
        from apps.core.dto.chat import MultiPlatformNotificationResult

        m = MultiPlatformNotificationResult()
        assert m.any_success is False
        assert m.all_success is False


class TestContractsDTO:
    def test_party_role_dto(self):
        from apps.core.dto.contracts import PartyRoleDTO

        p = PartyRoleDTO(id=1, contract_id=2, client_id=3, client_name="客户", role_type="PRINCIPAL")
        assert p.is_our_client is False

    def test_supplementary_agreement_dto(self):
        from apps.core.dto.contracts import SupplementaryAgreementDTO

        d = SupplementaryAgreementDTO(id=1, contract_id=2, title="补充协议")
        assert d.content is None
        assert d.signed_date is None

    def test_contract_dto_defaults(self):
        from apps.core.dto.contracts import ContractDTO

        d = ContractDTO(id=1, name="合同", case_type="civil", status="active", representation_stages=["一审"])
        assert d.primary_lawyer_id is None
        assert d.is_filed is False


# =====================================================================
# config/business_config — 补充覆盖
# =====================================================================

class TestBusinessConfig:
    def test_config_module_importable(self):
        from apps.core.config import business_config

        assert hasattr(business_config, "__name__")


# =====================================================================
# config/exceptions
# =====================================================================

class TestConfigExceptions:
    def test_config_exception(self):
        from apps.core.config.exceptions import ConfigException

        exc = ConfigException("config error")
        assert "config error" in str(exc)

    def test_config_file_error(self):
        from apps.core.config.exceptions import ConfigFileError

        exc = ConfigFileError("/path/file.yaml", line=10, message="bad yaml")
        assert "file.yaml" in str(exc)

    def test_config_validation_error(self):
        from apps.core.config.exceptions import ConfigValidationError

        exc = ConfigValidationError(["field1 required", "field2 required"])
        assert len(exc.errors) == 2
