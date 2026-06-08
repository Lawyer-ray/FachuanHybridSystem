"""Tests for feedback_loop, event_service, state_sync, keywords, llm_preflight."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import ValidationException


# ── keywords ───────────────────────────────────────────────────────────────


class TestNormalizeKeywordQuery:
    def test_empty_input(self) -> None:
        from apps.legal_research.services.keywords import normalize_keyword_query

        assert normalize_keyword_query("") == ""
        assert normalize_keyword_query(None) == ""  # type: ignore[arg-type]
        assert normalize_keyword_query("   ") == ""

    def test_single_keyword(self) -> None:
        from apps.legal_research.services.keywords import normalize_keyword_query

        assert normalize_keyword_query("合同") == "合同"

    def test_comma_separated(self) -> None:
        from apps.legal_research.services.keywords import normalize_keyword_query

        result = normalize_keyword_query("合同,纠纷,违约")
        assert result == "合同 纠纷 违约"

    def test_space_separated(self) -> None:
        from apps.legal_research.services.keywords import normalize_keyword_query

        result = normalize_keyword_query("合同 纠纷")
        assert result == "合同 纠纷"

    def test_chinese_separators(self) -> None:
        from apps.legal_research.services.keywords import normalize_keyword_query

        result = normalize_keyword_query("合同；纠纷、违约")
        assert result == "合同 纠纷 违约"

    def test_newline_separated(self) -> None:
        from apps.legal_research.services.keywords import normalize_keyword_query

        result = normalize_keyword_query("合同\n纠纷\r违约")
        assert result == "合同 纠纷 违约"

    def test_deduplication(self) -> None:
        from apps.legal_research.services.keywords import normalize_keyword_query

        result = normalize_keyword_query("合同 合同 纠纷")
        assert result == "合同 纠纷"

    def test_mixed_separators(self) -> None:
        from apps.legal_research.services.keywords import normalize_keyword_query

        result = normalize_keyword_query("合同, 纠纷；违约、侵权")
        assert result == "合同 纠纷 违约 侵权"

    def test_extra_whitespace(self) -> None:
        from apps.legal_research.services.keywords import normalize_keyword_query

        result = normalize_keyword_query("  合同  ,  纠纷  ")
        assert result == "合同 纠纷"


# ── feedback_loop ──────────────────────────────────────────────────────────


class TestFeedbackLoopService:
    def _make_service(self) -> tuple:
        from apps.legal_research.services.task.feedback_loop import LegalResearchFeedbackLoopService

        config = MagicMock()
        config._store: dict[str, str] = {}

        def get_value(key, default=""):
            return config._store.get(key, default)

        def set_value(key, value, **kwargs):
            config._store[key] = value

        config.get_value = MagicMock(side_effect=get_value)
        config.set_value = MagicMock(side_effect=set_value)
        svc = LegalResearchFeedbackLoopService(config_service=config)
        return svc, config

    def test_apply_feedback_hit_false_increments(self) -> None:
        from apps.legal_research.services.task.feedback_loop import (
            LegalResearchFeedbackLoopService,
            LegalResearchFeedbackType,
        )

        svc, config = self._make_service()
        svc.apply_feedback(feedback_type=LegalResearchFeedbackType.HIT_FALSE)
        # counter incremented
        calls = [c for c in config.set_value.call_args_list if "NEGATIVE" in str(c)]
        assert len(calls) >= 1

    def test_apply_feedback_missed_case(self) -> None:
        from apps.legal_research.services.task.feedback_loop import (
            LegalResearchFeedbackLoopService,
            LegalResearchFeedbackType,
        )

        svc, config = self._make_service()
        svc.apply_feedback(feedback_type=LegalResearchFeedbackType.MISSED_CASE)
        calls = [c for c in config.set_value.call_args_list if "MISSED" in str(c)]
        assert len(calls) >= 1

    def test_apply_feedback_hit_true(self) -> None:
        from apps.legal_research.services.task.feedback_loop import (
            LegalResearchFeedbackLoopService,
            LegalResearchFeedbackType,
        )

        svc, config = self._make_service()
        svc.apply_feedback(feedback_type=LegalResearchFeedbackType.HIT_TRUE)
        calls = [c for c in config.set_value.call_args_list if "POSITIVE" in str(c)]
        assert len(calls) >= 1

    def test_apply_feedback_disabled(self) -> None:
        from apps.legal_research.services.task.feedback_loop import (
            LegalResearchFeedbackLoopService,
            LegalResearchFeedbackType,
        )

        svc, config = self._make_service()
        config._store[LegalResearchFeedbackLoopService.KEY_ONLINE_ENABLED] = "false"
        svc.apply_feedback(feedback_type=LegalResearchFeedbackType.HIT_FALSE)
        # No counter updates when disabled
        counter_calls = [c for c in config.set_value.call_args_list if "COUNT" in str(c)]
        assert len(counter_calls) == 0

    def test_apply_feedback_unknown_type(self) -> None:
        from apps.legal_research.services.task.feedback_loop import LegalResearchFeedbackLoopService

        svc, config = self._make_service()
        svc.apply_feedback(feedback_type="unknown_type")
        # Should not raise, just log warning

    def test_record_result_feedback_relevant(self) -> None:
        from apps.legal_research.services.task.feedback_loop import LegalResearchFeedbackLoopService

        svc, config = self._make_service()
        result = MagicMock()
        result.metadata = {}
        svc.record_result_feedback(result=result, is_relevant=True, operator="test")
        assert result.metadata["human_feedback"] == "relevant"

    def test_record_result_feedback_not_relevant(self) -> None:
        from apps.legal_research.services.task.feedback_loop import LegalResearchFeedbackLoopService

        svc, config = self._make_service()
        result = MagicMock()
        result.metadata = {}
        svc.record_result_feedback(result=result, is_relevant=False)
        assert result.metadata["human_feedback"] == "false_positive"

    def test_record_task_missed_feedback(self) -> None:
        from apps.legal_research.services.task.feedback_loop import LegalResearchFeedbackLoopService

        svc, config = self._make_service()
        task = MagicMock()
        svc.record_task_missed_feedback(task=task, operator="tester", note="遗漏案例")
        assert "漏命中" in task.message

    def test_get_bool_variants(self) -> None:
        from apps.legal_research.services.task.feedback_loop import LegalResearchFeedbackLoopService

        svc, config = self._make_service()

        for truthy in ("1", "true", "yes", "on", "y", "True", "YES"):
            config._store["k"] = truthy
            assert svc._get_bool("k", default=False) is True, f"Failed for {truthy}"

        for falsy in ("0", "false", "no", "off", "n", "False", "NO"):
            config._store["k"] = falsy
            assert svc._get_bool("k", default=True) is False, f"Failed for {falsy}"

        assert svc._get_bool("nonexistent", default=True) is True

    def test_increment_counter_from_zero(self) -> None:
        from apps.legal_research.services.task.feedback_loop import LegalResearchFeedbackLoopService

        svc, config = self._make_service()
        svc._increment_counter("COUNTER_KEY")
        config.set_value.assert_called()
        args = config.set_value.call_args
        assert args[0][1] == "1"

    def test_increment_counter_from_non_numeric(self) -> None:
        from apps.legal_research.services.task.feedback_loop import LegalResearchFeedbackLoopService

        svc, config = self._make_service()
        config._store["COUNTER_KEY"] = "abc"
        svc._increment_counter("COUNTER_KEY")
        args = config.set_value.call_args
        assert args[0][1] == "1"

    def test_get_float_clamps(self) -> None:
        from apps.legal_research.services.task.feedback_loop import LegalResearchFeedbackLoopService
        from apps.legal_research.services.similarity.tuning_config import LegalResearchTuningConfig

        svc, config = self._make_service()
        key = LegalResearchFeedbackLoopService.KEY_MIN_SIMILARITY_DELTA
        config._store[key.key] = "10.0"  # above max
        value = svc._get_float(key)
        assert value == key.max_value

    def test_set_float_clamps(self) -> None:
        from apps.legal_research.services.task.feedback_loop import LegalResearchFeedbackLoopService

        svc, config = self._make_service()
        key = LegalResearchFeedbackLoopService.KEY_MIN_SIMILARITY_DELTA
        svc._set_float(key, 999.0)
        args = config.set_value.call_args
        clamped = float(args[0][1])
        assert clamped <= key.max_value


# ── event_service ──────────────────────────────────────────────────────────


class TestEventServiceNormalization:
    def test_normalize_task_id_none(self) -> None:
        from apps.legal_research.services.task.event_service import LegalResearchTaskEventService

        assert LegalResearchTaskEventService._normalize_task_id(None) is None
        assert LegalResearchTaskEventService._normalize_task_id("") is None
        assert LegalResearchTaskEventService._normalize_task_id("0") is None
        assert LegalResearchTaskEventService._normalize_task_id("-1") is None

    def test_normalize_task_id_valid(self) -> None:
        from apps.legal_research.services.task.event_service import LegalResearchTaskEventService

        assert LegalResearchTaskEventService._normalize_task_id("42") == 42
        assert LegalResearchTaskEventService._normalize_task_id(42) == 42

    def test_normalize_task_id_invalid(self) -> None:
        from apps.legal_research.services.task.event_service import LegalResearchTaskEventService

        assert LegalResearchTaskEventService._normalize_task_id("abc") is None

    def test_normalize_status_code_none(self) -> None:
        from apps.legal_research.services.task.event_service import LegalResearchTaskEventService

        assert LegalResearchTaskEventService._normalize_status_code(None) is None

    def test_normalize_status_code_out_of_range(self) -> None:
        from apps.legal_research.services.task.event_service import LegalResearchTaskEventService

        assert LegalResearchTaskEventService._normalize_status_code(50) is None
        assert LegalResearchTaskEventService._normalize_status_code(1000) is None

    def test_normalize_status_code_valid(self) -> None:
        from apps.legal_research.services.task.event_service import LegalResearchTaskEventService

        assert LegalResearchTaskEventService._normalize_status_code(200) == 200
        assert LegalResearchTaskEventService._normalize_status_code("404") == 404

    def test_sanitize_url_masks_sensitive_params(self) -> None:
        from apps.legal_research.services.task.event_service import LegalResearchTaskEventService

        url = "https://example.com/api?token=secret123&data=ok"
        sanitized = LegalResearchTaskEventService._sanitize_url(url)
        assert "secret123" not in sanitized
        assert "token=***" in sanitized

    def test_sanitize_url_truncates_long(self) -> None:
        from apps.legal_research.services.task.event_service import LegalResearchTaskEventService

        url = "https://example.com/" + "a" * 2000
        sanitized = LegalResearchTaskEventService._sanitize_url(url)
        assert len(sanitized) <= LegalResearchTaskEventService.MAX_URL_CHARS

    def test_sanitize_url_empty(self) -> None:
        from apps.legal_research.services.task.event_service import LegalResearchTaskEventService

        assert LegalResearchTaskEventService._sanitize_url("") == ""
        assert LegalResearchTaskEventService._sanitize_url(None) == ""  # type: ignore[arg-type]

    def test_is_sensitive_key(self) -> None:
        from apps.legal_research.services.task.event_service import LegalResearchTaskEventService

        assert LegalResearchTaskEventService._is_sensitive_key("password") is True
        assert LegalResearchTaskEventService._is_sensitive_key("api_key") is True
        assert LegalResearchTaskEventService._is_sensitive_key("AUTHORIZATION") is True
        assert LegalResearchTaskEventService._is_sensitive_key("token") is True
        assert LegalResearchTaskEventService._is_sensitive_key("name") is False
        assert LegalResearchTaskEventService._is_sensitive_key("") is False

    def test_sanitize_node_masks_sensitive_dict_keys(self) -> None:
        from apps.legal_research.services.task.event_service import LegalResearchTaskEventService

        result = LegalResearchTaskEventService._sanitize_node(
            value={"password": "secret", "name": "ok"},
            level=0,
            key_hint="",
        )
        assert result["password"] == "***"
        assert result["name"] == "ok"

    def test_sanitize_node_limits_depth(self) -> None:
        from apps.legal_research.services.task.event_service import LegalResearchTaskEventService

        deep = {"a": {"b": {"c": {"d": {"e": "too deep"}}}}}
        result = LegalResearchTaskEventService._sanitize_node(value=deep, level=0, key_hint="")
        # level 0-4 allowed, level 5 returns "..."
        assert result["a"]["b"]["c"]["d"]["e"] == "..."

    def test_sanitize_node_limits_list_items(self) -> None:
        from apps.legal_research.services.task.event_service import LegalResearchTaskEventService

        items = list(range(30))
        result = LegalResearchTaskEventService._sanitize_node(value=items, level=0, key_hint="")
        assert len(result) == LegalResearchTaskEventService.MAX_LIST_ITEMS + 1  # +1 for "..."

    def test_sanitize_node_limits_dict_items(self) -> None:
        from apps.legal_research.services.task.event_service import LegalResearchTaskEventService

        data = {f"k{i}": i for i in range(40)}
        result = LegalResearchTaskEventService._sanitize_node(value=data, level=0, key_hint="")
        assert "__truncated__" in result

    def test_sanitize_node_bytes(self) -> None:
        from apps.legal_research.services.task.event_service import LegalResearchTaskEventService

        result = LegalResearchTaskEventService._sanitize_node(value=b"hello", level=0, key_hint="")
        assert result == "<bytes:5>"

    def test_sanitize_node_sensitive_key_hint(self) -> None:
        from apps.legal_research.services.task.event_service import LegalResearchTaskEventService

        result = LegalResearchTaskEventService._sanitize_node(
            value="secret_value", level=0, key_hint="api_key"
        )
        assert result == "***"

    def test_sanitize_node_long_string(self) -> None:
        from apps.legal_research.services.task.event_service import LegalResearchTaskEventService

        long_text = "x" * 500
        result = LegalResearchTaskEventService._sanitize_node(value=long_text, level=0, key_hint="")
        assert len(result) <= LegalResearchTaskEventService.MAX_STRING_CHARS

    def test_sanitize_payload_truncates_large(self) -> None:
        from apps.legal_research.services.task.event_service import LegalResearchTaskEventService

        big = {f"k{i}": "x" * 200 for i in range(20)}
        result = LegalResearchTaskEventService._sanitize_payload(big)
        assert "preview" in result

    def test_sanitize_payload_empty(self) -> None:
        from apps.legal_research.services.task.event_service import LegalResearchTaskEventService

        assert LegalResearchTaskEventService._sanitize_payload(None) == {}
        assert LegalResearchTaskEventService._sanitize_payload("") == {}

    def test_sanitize_payload_non_mapping(self) -> None:
        from apps.legal_research.services.task.event_service import LegalResearchTaskEventService

        result = LegalResearchTaskEventService._sanitize_payload(42)
        assert "value" in result


# ── state_sync ─────────────────────────────────────────────────────────────


class TestStateSync:
    def test_sync_when_not_queued_or_running(self) -> None:
        from apps.legal_research.models import LegalResearchTaskStatus
        from apps.legal_research.services.task.state_sync import sync_failed_queue_state

        task = MagicMock()
        task.status = LegalResearchTaskStatus.COMPLETED
        assert sync_failed_queue_state(task=task) is False

    def test_sync_when_no_q_task_id(self) -> None:
        from apps.legal_research.models import LegalResearchTaskStatus
        from apps.legal_research.services.task.state_sync import sync_failed_queue_state

        task = MagicMock()
        task.status = LegalResearchTaskStatus.QUEUED
        task.q_task_id = ""
        assert sync_failed_queue_state(task=task) is False

    @patch("apps.core.tasking.TaskQueryService")
    def test_sync_when_failed_task_found(self, mock_tqs_cls) -> None:
        from apps.legal_research.models import LegalResearchTaskStatus
        from apps.legal_research.services.task.state_sync import sync_failed_queue_state

        task = MagicMock()
        task.status = LegalResearchTaskStatus.QUEUED
        task.q_task_id = "q-123"
        task.error = ""

        mock_instance = MagicMock()
        mock_instance.get_failed_task_info.return_value = {"result": "ConnectionError", "stopped": None}
        mock_tqs_cls.return_value = mock_instance

        result = sync_failed_queue_state(task=task)
        assert result is True
        assert task.status == LegalResearchTaskStatus.FAILED

    @patch("apps.core.tasking.TaskQueryService")
    def test_sync_when_task_info_none(self, mock_tqs_cls) -> None:
        from apps.legal_research.models import LegalResearchTaskStatus
        from apps.legal_research.services.task.state_sync import sync_failed_queue_state

        task = MagicMock()
        task.status = LegalResearchTaskStatus.RUNNING
        task.q_task_id = "q-123"

        mock_instance = MagicMock()
        mock_instance.get_failed_task_info.return_value = None
        mock_tqs_cls.return_value = mock_instance

        assert sync_failed_queue_state(task=task) is False

    @patch("apps.core.tasking.TaskQueryService")
    def test_sync_when_exception_in_query(self, mock_tqs_cls) -> None:
        from apps.legal_research.models import LegalResearchTaskStatus
        from apps.legal_research.services.task.state_sync import sync_failed_queue_state

        task = MagicMock()
        task.status = LegalResearchTaskStatus.QUEUED
        task.q_task_id = "q-123"

        mock_tqs_cls.side_effect = RuntimeError("db error")
        assert sync_failed_queue_state(task=task) is False

    @patch("apps.core.tasking.TaskQueryService")
    def test_sync_truncates_long_error(self, mock_tqs_cls) -> None:
        from apps.legal_research.models import LegalResearchTaskStatus
        from apps.legal_research.services.task.state_sync import sync_failed_queue_state

        task = MagicMock()
        task.status = LegalResearchTaskStatus.QUEUED
        task.q_task_id = "q-123"
        task.error = ""

        mock_instance = MagicMock()
        mock_instance.get_failed_task_info.return_value = {"result": "x" * 2000, "stopped": None}
        mock_tqs_cls.return_value = mock_instance

        sync_failed_queue_state(task=task)
        assert len(task.error) <= 1000


# ── llm_preflight ──────────────────────────────────────────────────────────


class TestLLMPreflight:
    @patch("apps.legal_research.services.llm_preflight.LLMConfig")
    def test_backend_not_enabled_raises(self, mock_llm_config) -> None:
        from apps.legal_research.services.llm_preflight import verify_siliconflow_connectivity

        config = MagicMock()
        config.enabled = False
        mock_llm_config.resolve_backend_for_model.return_value = "siliconflow"
        mock_llm_config.get_backend_configs.return_value = {"siliconflow": config}

        with pytest.raises(ValidationException, match="未启用"):
            verify_siliconflow_connectivity(model="test/model")

    @patch("apps.legal_research.services.llm_preflight.LLMConfig")
    def test_no_base_url_raises(self, mock_llm_config) -> None:
        from apps.legal_research.services.llm_preflight import verify_siliconflow_connectivity

        config = MagicMock()
        config.enabled = True
        config.base_url = ""
        config.api_key = "key"
        mock_llm_config.resolve_backend_for_model.return_value = "siliconflow"
        mock_llm_config.get_backend_configs.return_value = {"siliconflow": config}

        with pytest.raises(ValidationException, match="未配置.*Base URL"):
            verify_siliconflow_connectivity(model="test/model")

    @patch("apps.legal_research.services.llm_preflight.LLMConfig")
    def test_no_api_key_for_siliconflow_raises(self, mock_llm_config) -> None:
        from apps.legal_research.services.llm_preflight import verify_siliconflow_connectivity

        config = MagicMock()
        config.enabled = True
        config.base_url = "https://api.example.com"
        config.api_key = ""
        mock_llm_config.resolve_backend_for_model.return_value = "siliconflow"
        mock_llm_config.get_backend_configs.return_value = {"siliconflow": config}

        with pytest.raises(ValidationException, match="未配置.*API Key"):
            verify_siliconflow_connectivity(model="test/model")

    @patch("apps.legal_research.services.llm_preflight.httpx.get")
    @patch("apps.legal_research.services.llm_preflight.LLMConfig")
    def test_ollama_connection_failure(self, mock_llm_config, mock_get) -> None:
        import httpx as real_httpx

        from apps.legal_research.services.llm_preflight import verify_siliconflow_connectivity

        config = MagicMock()
        config.enabled = True
        config.base_url = "http://localhost:11434"
        config.api_key = ""
        mock_llm_config.resolve_backend_for_model.return_value = "ollama"
        mock_llm_config.get_backend_configs.return_value = {"ollama": config}

        mock_get.side_effect = real_httpx.ConnectError("connection refused")

        with pytest.raises(ValidationException, match="Ollama 连接失败"):
            verify_siliconflow_connectivity(model="llama3:latest")

    @patch("apps.legal_research.services.llm_preflight.LLMConfig")
    def test_ollama_non_200_raises(self, mock_llm_config) -> None:
        from apps.legal_research.services.llm_preflight import verify_siliconflow_connectivity

        config = MagicMock()
        config.enabled = True
        config.base_url = "http://localhost:11434"
        config.api_key = ""
        mock_llm_config.resolve_backend_for_model.return_value = "ollama"
        mock_llm_config.get_backend_configs.return_value = {"ollama": config}

        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("apps.legal_research.services.llm_preflight.httpx.get", return_value=mock_response):
            with pytest.raises(ValidationException, match="Ollama 服务不可用"):
                verify_siliconflow_connectivity(model="llama3:latest")

    @patch("apps.legal_research.services.llm_preflight.LLMConfig")
    def test_openai_compatible_auth_failure(self, mock_llm_config) -> None:
        from apps.legal_research.services.llm_preflight import verify_siliconflow_connectivity

        config = MagicMock()
        config.enabled = True
        config.base_url = "https://api.example.com"
        config.api_key = "bad-key"  # pragma: allowlist secret
        mock_llm_config.resolve_backend_for_model.return_value = "openai_compatible"
        mock_llm_config.get_backend_configs.return_value = {"openai_compatible": config}

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response

        with patch("apps.legal_research.services.llm_preflight.httpx.HTTPTransport"):
            with patch("apps.legal_research.services.llm_preflight.httpx.Client", return_value=mock_client):
                with pytest.raises(ValidationException, match="鉴权失败"):
                    verify_siliconflow_connectivity(model="gpt-4")


# ── source factory ─────────────────────────────────────────────────────────


class TestSourceFactory:
    def test_create_default_weike(self) -> None:
        from apps.legal_research.services.sources.factory import SourceClientFactory

        client = SourceClientFactory.create(None)
        assert client is not None

    def test_create_weike(self) -> None:
        from apps.legal_research.services.sources.factory import SourceClientFactory

        client = SourceClientFactory.create("weike")
        assert client is not None

    def test_create_unsupported(self) -> None:
        from apps.legal_research.services.sources.factory import (
            SourceClientFactory,
            UnsupportedCaseSourceError,
        )

        with pytest.raises(UnsupportedCaseSourceError):
            SourceClientFactory.create("unknown_source")

    def test_register_empty_source_raises(self) -> None:
        from apps.legal_research.services.sources.factory import SourceClientFactory

        with pytest.raises(ValueError, match="不能为空"):
            SourceClientFactory.register(source="", builder=lambda: MagicMock())

    def test_register_and_create(self) -> None:
        from apps.legal_research.services.sources.factory import SourceClientFactory

        mock_builder = MagicMock()
        SourceClientFactory.register(source="test_source", builder=mock_builder)
        result = SourceClientFactory.create("test_source")
        mock_builder.assert_called_once()
        # Clean up
        del SourceClientFactory._builders["test_source"]
