"""core 模块 batch8 覆盖测试 — 覆盖 tasking、services、middleware、llm 等未覆盖行。"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, PropertyMock, mock_open, patch

import pytest


# =====================================================================
# TaskRunContext — runtime.py
# =====================================================================

class TestTaskRunContext:
    def test_from_django_q_with_explicit_timeout(self):
        from apps.core.tasking.runtime import TaskRunContext

        ctx = TaskRunContext.from_django_q(timeout_seconds=300.0, safety_margin_seconds=30.0, min_soft_deadline_seconds=60.0)
        assert ctx.timeout_seconds == 300.0
        assert ctx.soft_deadline_monotonic >= ctx.started_monotonic + 60.0
        assert ctx.soft_deadline_monotonic == ctx.started_monotonic + max(60.0, 300.0 - 30.0)

    def test_from_django_q_default_timeout(self):
        from apps.core.tasking.runtime import TaskRunContext

        ctx = TaskRunContext.from_django_q()
        assert ctx.timeout_seconds == 600.0

    def test_from_django_q_invalid_q_cluster_timeout(self):
        from apps.core.tasking.runtime import TaskRunContext

        with patch("apps.core.tasking.runtime.settings") as mock_settings:
            mock_settings.Q_CLUSTER = {"timeout": "not_a_number"}
            ctx = TaskRunContext.from_django_q()
            assert ctx.timeout_seconds == 600.0

    def test_is_past_soft_deadline_false(self):
        from apps.core.tasking.runtime import TaskRunContext

        ctx = TaskRunContext(started_monotonic=time.monotonic(), soft_deadline_monotonic=time.monotonic() + 9999, timeout_seconds=600.0)
        assert ctx.is_past_soft_deadline() is False

    def test_is_past_soft_deadline_true(self):
        from apps.core.tasking.runtime import TaskRunContext

        ctx = TaskRunContext(started_monotonic=time.monotonic(), soft_deadline_monotonic=time.monotonic() - 1, timeout_seconds=0.001)
        time.sleep(0.01)
        assert ctx.is_past_soft_deadline() is True


# =====================================================================
# CancellationToken
# =====================================================================

class TestCancellationToken:
    def test_is_cancelled_true(self):
        from apps.core.tasking.runtime import CancellationToken

        token = CancellationToken(should_cancel=lambda: True)
        assert token.is_cancelled() is True

    def test_is_cancelled_false(self):
        from apps.core.tasking.runtime import CancellationToken

        token = CancellationToken(should_cancel=lambda: False)
        assert token.is_cancelled() is False

    def test_is_cancelled_type_error(self):
        from apps.core.tasking.runtime import CancellationToken

        token = CancellationToken(should_cancel=lambda: 1 / 0)  # raises ZeroDivisionError not caught, but TypeError
        # ZeroDivisionError is not caught, so let's test TypeError
        def bad():
            raise TypeError("bad")
        token2 = CancellationToken(should_cancel=bad)
        assert token2.is_cancelled() is False

    def test_is_cancelled_attribute_error(self):
        from apps.core.tasking.runtime import CancellationToken

        def bad():
            raise AttributeError("bad")
        token = CancellationToken(should_cancel=bad)
        assert token.is_cancelled() is False


# =====================================================================
# ProgressReporter
# =====================================================================

class TestProgressReporter:
    def test_report_basic(self):
        from apps.core.tasking.runtime import ProgressReporter

        mock_fn = MagicMock()
        reporter = ProgressReporter(update_fn=mock_fn, min_interval_seconds=0.0)
        reporter.report(current=5, total=10, message="half")
        mock_fn.assert_called_once_with(50, 5, 10, "half")

    def test_report_force(self):
        from apps.core.tasking.runtime import ProgressReporter

        mock_fn = MagicMock()
        reporter = ProgressReporter(update_fn=mock_fn, min_interval_seconds=999.0)
        reporter.report(current=1, total=10, message="first", force=True)
        reporter.report(current=5, total=10, message="half", force=True)
        assert mock_fn.call_count == 2

    def test_report_dedup_within_interval(self):
        from apps.core.tasking.runtime import ProgressReporter

        mock_fn = MagicMock()
        reporter = ProgressReporter(update_fn=mock_fn, min_interval_seconds=999.0)
        reporter.report(current=5, total=10, message="same", force=True)
        mock_fn.reset_mock()
        reporter.report(current=5, total=10, message="same")
        mock_fn.assert_not_called()

    def test_report_zero_total(self):
        from apps.core.tasking.runtime import ProgressReporter

        mock_fn = MagicMock()
        reporter = ProgressReporter(update_fn=mock_fn, min_interval_seconds=0.0)
        reporter.report(current=0, total=0, message="zero")
        mock_fn.assert_called_once_with(0, 0, 0, "zero")

    def test_report_clamps_progress(self):
        from apps.core.tasking.runtime import ProgressReporter

        mock_fn = MagicMock()
        reporter = ProgressReporter(update_fn=mock_fn, min_interval_seconds=0.0)
        reporter.report(current=200, total=100, message="over")
        mock_fn.assert_called_once_with(100, 200, 100, "over")

    def test_report_extra_force(self):
        from apps.core.tasking.runtime import ProgressReporter

        mock_fn = MagicMock()
        reporter = ProgressReporter(update_fn=mock_fn, min_interval_seconds=999.0)
        reporter.report_extra(progress=42, current=10, total=20, message="extra", force=True)
        mock_fn.assert_called_once_with(42, 10, 20, "extra")

    def test_report_extra_throttled(self):
        from apps.core.tasking.runtime import ProgressReporter

        mock_fn = MagicMock()
        reporter = ProgressReporter(update_fn=mock_fn, min_interval_seconds=999.0)
        reporter.report_extra(progress=42, current=10, total=20, message="extra", force=True)
        mock_fn.reset_mock()
        reporter.report_extra(progress=43, current=11, total=20, message="extra2")
        mock_fn.assert_not_called()


# =====================================================================
# TaskContext — context.py
# =====================================================================

class TestTaskContext:
    def test_to_dict(self):
        from apps.core.tasking.context import TaskContext

        ctx = TaskContext(request_id="r1", correlation_id="c1", task_name="t1", entity_id="e1", extra={"k": "v"})
        d = ctx.to_dict()
        assert d["request_id"] == "r1"
        assert d["correlation_id"] == "c1"
        assert d["task_name"] == "t1"
        assert d["entity_id"] == "e1"
        assert d["extra"] == {"k": "v"}

    def test_to_dict_defaults(self):
        from apps.core.tasking.context import TaskContext

        ctx = TaskContext()
        d = ctx.to_dict()
        assert d["extra"] == {}

    def test_from_dict_full(self):
        from apps.core.tasking.context import TaskContext

        data = {"request_id": "r1", "correlation_id": "c1", "task_name": "t1", "entity_id": "e1", "extra": {"k": "v"}}
        ctx = TaskContext.from_dict(data)
        assert ctx.request_id == "r1"
        assert ctx.extra == {"k": "v"}

    def test_from_dict_none(self):
        from apps.core.tasking.context import TaskContext

        ctx = TaskContext.from_dict(None)
        assert ctx.request_id is None
        assert ctx.extra == {}

    def test_from_dict_empty_extra(self):
        from apps.core.tasking.context import TaskContext

        ctx = TaskContext.from_dict({"extra": None})
        assert ctx.extra == {}


# =====================================================================
# DjangoQTaskScheduler — scheduler.py
# =====================================================================

class TestDjangoQTaskScheduler:
    @patch("apps.core.tasking.scheduler.Schedule")
    def test_delete_schedules_by_name(self, mock_schedule):
        from apps.core.tasking.scheduler import DjangoQTaskScheduler

        mock_qs = MagicMock()
        mock_qs.count.return_value = 3
        mock_schedule.objects.all.return_value = mock_qs
        scheduler = DjangoQTaskScheduler()
        result = scheduler.delete_schedules(name="test_name")
        mock_qs.filter.assert_called_once_with(name="test_name")
        mock_qs.delete.assert_called_once()
        assert result == 3

    @patch("apps.core.tasking.scheduler.Schedule")
    def test_delete_schedules_by_func(self, mock_schedule):
        from apps.core.tasking.scheduler import DjangoQTaskScheduler

        mock_qs = MagicMock()
        mock_qs.count.return_value = 1
        mock_schedule.objects.all.return_value = mock_qs
        scheduler = DjangoQTaskScheduler()
        result = scheduler.delete_schedules(func="some.func")
        mock_qs.filter.assert_called_once_with(func="some.func")
        assert result == 1

    @patch("apps.core.tasking.scheduler.Schedule")
    def test_delete_schedules_no_filters(self, mock_schedule):
        from apps.core.tasking.scheduler import DjangoQTaskScheduler

        mock_qs = MagicMock()
        mock_qs.count.return_value = 0
        mock_schedule.objects.all.return_value = mock_qs
        scheduler = DjangoQTaskScheduler()
        result = scheduler.delete_schedules()
        mock_qs.filter.assert_not_called()
        assert result == 0


# =====================================================================
# Cached decorator + invalidate_cache — cache_service.py
# =====================================================================

class TestCacheService:
    def test_cached_returns_cached_value(self):
        from apps.core.services.cache_service import cached

        with patch("apps.core.services.cache_service.cache") as mock_cache:
            mock_cache.get.return_value = "cached_result"

            @cached("test:{id}")
            def my_func(id):
                return "fresh"

            result = my_func(id=1)
            assert result == "cached_result"

    def test_cached_calls_func_on_miss(self):
        from apps.core.services.cache_service import cached

        with patch("apps.core.services.cache_service.cache") as mock_cache:
            mock_cache.get.return_value = None

            @cached("test:{id}")
            def my_func(id):
                return "fresh"

            result = my_func(id=1)
            assert result == "fresh"
            mock_cache.set.assert_called_once_with("test:1", "fresh", None)

    def test_cached_with_timeout(self):
        from apps.core.services.cache_service import cached

        with patch("apps.core.services.cache_service.cache") as mock_cache:
            mock_cache.get.return_value = None

            @cached("test:{id}", timeout=60)
            def my_func(id):
                return "fresh"

            my_func(id=1)
            mock_cache.set.assert_called_once_with("test:1", "fresh", 60)

    def test_cached_key_error_fallback(self):
        from apps.core.services.cache_service import cached

        with patch("apps.core.services.cache_service.cache") as mock_cache:
            mock_cache.get.return_value = None

            @cached("test:{missing}")
            def my_func(id):
                return "fresh"

            result = my_func(id=1)
            assert result == "fresh"

    def test_cached_connection_error_read(self):
        from apps.core.services.cache_service import cached

        with patch("apps.core.services.cache_service.cache") as mock_cache:
            mock_cache.get.side_effect = ConnectionError("no redis")

            @cached("test:{id}")
            def my_func(id):
                return "fallback"

            result = my_func(id=1)
            assert result == "fallback"

    def test_cached_connection_error_write(self):
        from apps.core.services.cache_service import cached

        with patch("apps.core.services.cache_service.cache") as mock_cache:
            mock_cache.get.return_value = None
            mock_cache.set.side_effect = ConnectionError("no redis")

            @cached("test:{id}")
            def my_func(id):
                return "fresh"

            result = my_func(id=1)
            assert result == "fresh"

    def test_invalidate_cache_success(self):
        from apps.core.services.cache_service import invalidate_cache

        with patch("apps.core.services.cache_service.cache") as mock_cache:
            invalidate_cache("test_key")
            mock_cache.delete.assert_called_once_with("test_key")

    def test_invalidate_cache_connection_error(self):
        from apps.core.services.cache_service import invalidate_cache

        with patch("apps.core.services.cache_service.cache") as mock_cache:
            mock_cache.delete.side_effect = OSError("no redis")
            invalidate_cache("test_key")  # should not raise


# =====================================================================
# EmailConfigService — email_config_service.py
# =====================================================================

class TestEmailConfigService:
    def test_get_config_returns_values(self):
        from apps.core.services.email_config_service import EmailConfigService

        mock_scs = MagicMock()
        mock_scs.get_value.side_effect = lambda k, d="": {
            "EMAIL_HOST": "smtp.test.com",
            "EMAIL_PORT": "465",
            "EMAIL_USE_SSL": "true",
            "EMAIL_USE_TLS": "false",
            "EMAIL_HOST_USER": "user@test.com",
            "EMAIL_HOST_PASSWORD": "pass",
            "EMAIL_FROM_NAME": "Test",
            "EMAIL_SUBJECT_PREFIX": "[Test]",
        }.get(k, d)

        with patch("apps.core.services.email_config_service.cache") as mock_cache:
            mock_cache.get.return_value = None
            with patch.object(EmailConfigService, "_get_config_service", return_value=mock_scs):
                config = EmailConfigService.get_config()
                assert config["EMAIL_HOST"] == "smtp.test.com"
                assert config["EMAIL_PORT"] == 465
                assert config["EMAIL_USE_SSL"] is True
                assert config["EMAIL_USE_TLS"] is False

    def test_get_config_uses_cache(self):
        from apps.core.services.email_config_service import EmailConfigService

        cached_config = {"EMAIL_HOST": "cached.host"}
        with patch("apps.core.services.email_config_service.cache") as mock_cache:
            mock_cache.get.return_value = cached_config
            result = EmailConfigService.get_config()
            assert result == cached_config

    def test_is_configured_true(self):
        from apps.core.services.email_config_service import EmailConfigService

        with patch.object(EmailConfigService, "get_config", return_value={"EMAIL_HOST": "smtp.test.com", "EMAIL_HOST_USER": "user@test.com"}):
            assert EmailConfigService.is_configured() is True

    def test_is_configured_false_no_host(self):
        from apps.core.services.email_config_service import EmailConfigService

        with patch.object(EmailConfigService, "get_config", return_value={"EMAIL_HOST": "", "EMAIL_HOST_USER": "user@test.com"}):
            assert EmailConfigService.is_configured() is False

    def test_clear_cache(self):
        from apps.core.services.email_config_service import EmailConfigService

        with patch("apps.core.services.email_config_service.cache") as mock_cache:
            EmailConfigService.clear_cache()
            mock_cache.delete.assert_called_once()


# =====================================================================
# ConversationHistoryService — conversation_history_service.py
# =====================================================================

class TestConversationHistoryService:
    def test_create_message_internal(self):
        from apps.core.services.conversation_history_service import ConversationHistoryService

        mock_repo = MagicMock()
        mock_record = SimpleNamespace(
            pk=1,
            session_id="s1",
            user_id="u1",
            role="user",
            content="hello",
            metadata={},
            created_at="2024-01-01",
            litigation_session_id=None,
            step="",
        )
        mock_repo.create.return_value = mock_record
        svc = ConversationHistoryService(repository=mock_repo)
        dto = svc.create_message_internal(session_id="s1", user_id="u1", role="user", content="hello", metadata={})
        assert dto.id == 1
        assert dto.session_id == "s1"
        assert dto.role == "user"

    def test_list_messages_internal_no_ids(self):
        from apps.core.services.conversation_history_service import ConversationHistoryService

        mock_repo = MagicMock()
        svc = ConversationHistoryService(repository=mock_repo)
        result = svc.list_messages_internal()
        assert result == []

    def test_count_messages_internal_no_ids(self):
        from apps.core.services.conversation_history_service import ConversationHistoryService

        mock_repo = MagicMock()
        svc = ConversationHistoryService(repository=mock_repo)
        assert svc.count_messages_internal() == 0

    def test_count_messages_by_litigation_session_ids_empty(self):
        from apps.core.services.conversation_history_service import ConversationHistoryService

        mock_repo = MagicMock()
        svc = ConversationHistoryService(repository=mock_repo)
        assert svc.count_messages_by_litigation_session_ids_internal(litigation_session_ids=[]) == {}

    def test_list_messages_internal_with_session_id(self):
        from apps.core.services.conversation_history_service import ConversationHistoryService

        mock_repo = MagicMock()
        mock_qs = MagicMock()
        mock_repo.get_all.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        mock_qs.order_by.return_value = mock_qs
        mock_qs.__getitem__ = MagicMock(return_value=[])
        svc = ConversationHistoryService(repository=mock_repo)
        result = svc.list_messages_internal(session_id="s1")
        assert result == []

    def test_list_messages_internal_desc_order(self):
        from apps.core.services.conversation_history_service import ConversationHistoryService

        mock_repo = MagicMock()
        mock_qs = MagicMock()
        mock_repo.get_all.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        mock_qs.order_by.return_value = mock_qs
        mock_qs.__getitem__ = MagicMock(return_value=[])
        svc = ConversationHistoryService(repository=mock_repo)
        svc.list_messages_internal(session_id="s1", order="desc")
        mock_qs.order_by.assert_called_with("-created_at")

    def test_get_conversation_history_messages(self):
        from apps.core.services.conversation_history_service import ConversationHistoryService

        mock_repo = MagicMock()
        mock_qs = MagicMock()
        mock_repo.get_by_session_id.return_value = mock_qs
        mock_record = SimpleNamespace(
            role="user",
            content="hello",
            created_at=MagicMock(isoformat=MagicMock(return_value="2024-01-01T00:00:00")),
            metadata={},
        )
        mock_qs.filter.return_value = mock_qs
        mock_qs.order_by.return_value = [mock_record]
        svc = ConversationHistoryService(repository=mock_repo)
        messages = svc.get_conversation_history_messages(session_id="s1", user_id="u1")
        assert len(messages) == 1
        assert messages[0]["role"] == "user"


# =====================================================================
# TokenRateLimitMiddleware — token_rate_limit.py
# =====================================================================

class TestTokenRateLimitMiddleware:
    def test_passes_non_token_path(self):
        from apps.core.middleware.token_rate_limit import TokenRateLimitMiddleware

        get_response = MagicMock(return_value="response")
        mw = TokenRateLimitMiddleware(get_response)
        request = MagicMock()
        request.path = "/api/v1/other/"
        request.method = "POST"
        result = mw(request)
        assert result == "response"

    def test_passes_get_token_request(self):
        from apps.core.middleware.token_rate_limit import TokenRateLimitMiddleware

        get_response = MagicMock(return_value="response")
        mw = TokenRateLimitMiddleware(get_response)
        request = MagicMock()
        request.path = "/api/v1/token/"
        request.method = "GET"
        result = mw(request)
        assert result == "response"

    def test_rate_limit_first_request(self):
        from apps.core.middleware.token_rate_limit import TokenRateLimitMiddleware

        with patch("apps.core.middleware.token_rate_limit.cache") as mock_cache:
            mock_cache.get.return_value = None
            get_response = MagicMock(return_value="response")
            mw = TokenRateLimitMiddleware(get_response)
            request = MagicMock()
            request.path = "/api/v1/token/"
            request.method = "POST"
            request.META = {"REMOTE_ADDR": "1.2.3.4"}
            result = mw(request)
            assert result == "response"
            assert mock_cache.set.call_count == 1

    def test_rate_limit_exceeded(self):
        from apps.core.middleware.token_rate_limit import TokenRateLimitMiddleware

        with patch("apps.core.middleware.token_rate_limit.cache") as mock_cache:
            mock_cache.get.return_value = 100
            get_response = MagicMock(return_value="response")
            mw = TokenRateLimitMiddleware(get_response)
            request = MagicMock()
            request.path = "/api/v1/token/"
            request.method = "POST"
            request.META = {"REMOTE_ADDR": "1.2.3.4"}
            result = mw(request)
            assert result.status_code == 429

    def test_get_client_ip_xff(self):
        from apps.core.middleware.token_rate_limit import TokenRateLimitMiddleware

        get_response = MagicMock()
        mw = TokenRateLimitMiddleware(get_response)
        request = MagicMock()
        request.META = {"HTTP_X_FORWARDED_FOR": "10.0.0.1, 192.168.1.1"}
        assert mw._get_client_ip(request) == "10.0.0.1"

    def test_get_client_ip_remote_addr(self):
        from apps.core.middleware.token_rate_limit import TokenRateLimitMiddleware

        get_response = MagicMock()
        mw = TokenRateLimitMiddleware(get_response)
        request = MagicMock()
        request.META = {"REMOTE_ADDR": "10.0.0.5"}
        assert mw._get_client_ip(request) == "10.0.0.5"

    def test_cache_error_passes_through(self):
        from apps.core.middleware.token_rate_limit import TokenRateLimitMiddleware

        with patch("apps.core.middleware.token_rate_limit.cache") as mock_cache:
            mock_cache.get.side_effect = Exception("cache down")
            get_response = MagicMock(return_value="response")
            mw = TokenRateLimitMiddleware(get_response)
            request = MagicMock()
            request.path = "/api/v1/token/"
            request.method = "POST"
            request.META = {"REMOTE_ADDR": "1.2.3.4"}
            result = mw(request)
            assert result == "response"


# =====================================================================
# PromptTemplate — models/prompt_template.py
# =====================================================================

class TestPromptTemplate:
    def test_str(self):
        from apps.core.models.prompt_template import PromptTemplate

        pt = PromptTemplate(name="test", title="Test Template")
        assert str(pt) == "Test Template (test)"


# =====================================================================
# BusinessConfigService — business_config_service.py
# =====================================================================

class TestBusinessConfigService:
    def test_get_stages_for_case_type(self):
        from apps.core.services.business_config_service import BusinessConfigService

        mock_config = MagicMock()
        mock_config.get_stages_for_case_type.return_value = [("init", "Init")]
        svc = BusinessConfigService(config=mock_config)
        result = svc.get_stages_for_case_type("civil")
        assert result == [("init", "Init")]

    def test_get_legal_statuses_for_case_type(self):
        from apps.core.services.business_config_service import BusinessConfigService

        mock_config = MagicMock()
        mock_config.get_legal_statuses_for_case_type.return_value = [("plaintiff", "原告")]
        svc = BusinessConfigService(config=mock_config)
        result = svc.get_legal_statuses_for_case_type("civil")
        assert result == [("plaintiff", "原告")]

    def test_get_stage_label(self):
        from apps.core.services.business_config_service import BusinessConfigService

        mock_config = MagicMock()
        mock_config.get_stage_label.return_value = "一审"
        svc = BusinessConfigService(config=mock_config)
        assert svc.get_stage_label("first_trial") == "一审"

    def test_get_legal_status_label(self):
        from apps.core.services.business_config_service import BusinessConfigService

        mock_config = MagicMock()
        mock_config.get_legal_status_label.return_value = "原告"
        svc = BusinessConfigService(config=mock_config)
        assert svc.get_legal_status_label("plaintiff") == "原告"

    def test_is_stage_valid_for_case_type(self):
        from apps.core.services.business_config_service import BusinessConfigService

        mock_config = MagicMock()
        mock_config.is_stage_valid_for_case_type.return_value = True
        svc = BusinessConfigService(config=mock_config)
        assert svc.is_stage_valid_for_case_type("first_trial", "civil") is True

    def test_is_legal_status_valid_for_case_type(self):
        from apps.core.services.business_config_service import BusinessConfigService

        mock_config = MagicMock()
        mock_config.is_legal_status_valid_for_case_type.return_value = True
        svc = BusinessConfigService(config=mock_config)
        assert svc.is_legal_status_valid_for_case_type("plaintiff", "civil") is True

    def test_get_compatible_legal_statuses(self):
        from apps.core.services.business_config_service import BusinessConfigService

        mock_config = MagicMock()
        mock_config.get_compatible_legal_statuses.return_value = [("defendant", "被告")]
        svc = BusinessConfigService(config=mock_config)
        result = svc.get_compatible_legal_statuses(["plaintiff"], "civil")
        assert result == [("defendant", "被告")]

    def test_is_legal_status_compatible(self):
        from apps.core.services.business_config_service import BusinessConfigService

        mock_config = MagicMock()
        mock_config.is_legal_status_compatible.return_value = True
        svc = BusinessConfigService(config=mock_config)
        assert svc.is_legal_status_compatible("defendant", ["plaintiff"]) is True

    def test_internal_methods_delegate(self):
        from apps.core.services.business_config_service import BusinessConfigService

        mock_config = MagicMock()
        svc = BusinessConfigService(config=mock_config)
        svc.get_stages_for_case_type_internal("civil")
        mock_config.get_stages_for_case_type.assert_called_once_with("civil")
        svc.get_legal_statuses_for_case_type_internal("civil")
        mock_config.get_legal_statuses_for_case_type.assert_called_once_with("civil")


# =====================================================================
# FileUploadService — file_upload_service.py
# =====================================================================

class TestFileUploadService:
    def test_validate_file_too_large(self):
        from apps.core.services.file_upload_service import FileUploadService
        from apps.core.exceptions import ValidationException

        svc = FileUploadService()
        mock_file = MagicMock()
        mock_file.size = 25 * 1024 * 1024
        mock_file.name = "test.pdf"
        mock_file.content_type = "application/pdf"
        with pytest.raises(ValidationException, match="文件大小超过限制"):
            svc.validate_file(mock_file)

    def test_validate_file_invalid_extension(self):
        from apps.core.services.file_upload_service import FileUploadService
        from apps.core.exceptions import ValidationException

        svc = FileUploadService()
        mock_file = MagicMock()
        mock_file.size = 1024
        mock_file.name = "test.exe"
        mock_file.content_type = "application/octet-stream"
        with pytest.raises(ValidationException, match="不支持的文件类型"):
            svc.validate_file(mock_file)

    def test_validate_file_invalid_mime(self):
        from apps.core.services.file_upload_service import FileUploadService
        from apps.core.exceptions import ValidationException

        svc = FileUploadService()
        mock_file = MagicMock()
        mock_file.size = 1024
        mock_file.name = "test.pdf"
        mock_file.content_type = "text/html"
        with pytest.raises(ValidationException, match="不支持的 MIME 类型"):
            svc.validate_file(mock_file)

    def test_validate_file_mime_extension_mismatch(self):
        from apps.core.services.file_upload_service import FileUploadService
        from apps.core.exceptions import ValidationException

        svc = FileUploadService()
        mock_file = MagicMock()
        mock_file.size = 1024
        mock_file.name = "test.jpg"
        mock_file.content_type = "application/pdf"
        with pytest.raises(ValidationException, match="文件类型与扩展名不匹配"):
            svc.validate_file(mock_file)

    def test_validate_file_valid(self):
        from apps.core.services.file_upload_service import FileUploadService

        svc = FileUploadService()
        mock_file = MagicMock()
        mock_file.size = 1024
        mock_file.name = "test.pdf"
        mock_file.content_type = "application/pdf"
        svc.validate_file(mock_file)  # should not raise


# =====================================================================
# StructuredOutput — llm/structured_output.py
# =====================================================================

class TestStructuredOutput:
    def test_clean_text(self):
        from apps.core.llm.structured_output import clean_text

        assert clean_text("```json\n{}\n```") == "{}"
        assert clean_text("```\nhello\n```") == "hello"
        assert clean_text("<|begin_of_text|>test<|end_of_text|>") == "test"

    def test_extract_json_text_valid_json(self):
        from apps.core.llm.structured_output import extract_json_text

        result = extract_json_text('{"key": "value"}')
        assert result == '{"key": "value"}'

    def test_extract_json_text_array(self):
        from apps.core.llm.structured_output import extract_json_text

        result = extract_json_text("[1, 2, 3]")
        assert result == "[1, 2, 3]"

    def test_extract_json_text_code_fence(self):
        from apps.core.llm.structured_output import extract_json_text

        result = extract_json_text('```json\n{"key": "value"}\n```')
        assert result == '{"key": "value"}'

    def test_extract_json_text_empty(self):
        from apps.core.llm.structured_output import extract_json_text

        result = extract_json_text("")
        assert result is None

    def test_extract_json_text_no_json(self):
        from apps.core.llm.structured_output import extract_json_text

        result = extract_json_text("no json here")
        assert result is None

    def test_extract_json_text_embedded_json(self):
        from apps.core.llm.structured_output import extract_json_text

        result = extract_json_text('Here is the result: {"answer": 42} done.')
        assert result == '{"answer": 42}'

    def test_parse_json_content_success(self):
        from apps.core.llm.structured_output import parse_json_content

        result = parse_json_content('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parse_json_content_no_json(self):
        from apps.core.llm.structured_output import parse_json_content

        with pytest.raises(ValueError, match="does not contain valid JSON"):
            parse_json_content("nothing here")

    def test_json_schema_instructions(self):
        from pydantic import BaseModel
        from apps.core.llm.structured_output import json_schema_instructions

        class MyModel(BaseModel):
            name: str
            count: int

        result = json_schema_instructions(MyModel)
        assert "JSON" in result
        assert "name" in result

    def test_extract_json_mismatched_braces(self):
        from apps.core.llm.structured_output import extract_json_text

        # A string where braces are mismatched - the function should handle gracefully
        result = extract_json_text("{not valid}[")
        # It will attempt parsing, fail, and return None
        assert result is None

    def test_extract_json_nested(self):
        from apps.core.llm.structured_output import extract_json_text

        result = extract_json_text("text before {\"a\": {\"b\": 1}} text after")
        assert result == '{"a": {"b": 1}}'


# =====================================================================
# ConversationHistoryRepository — repositories/
# =====================================================================

class TestConversationHistoryRepository:
    def test_get_all(self):
        from apps.core.repositories.conversation_repository import ConversationHistoryRepository

        with patch("apps.core.repositories.conversation_repository.ConversationHistory") as mock_model:
            repo = ConversationHistoryRepository()
            repo.get_all()
            mock_model.objects.all.assert_called_once()

    def test_get_by_session_id(self):
        from apps.core.repositories.conversation_repository import ConversationHistoryRepository

        with patch("apps.core.repositories.conversation_repository.ConversationHistory") as mock_model:
            repo = ConversationHistoryRepository()
            repo.get_by_session_id("s1")
            mock_model.objects.filter.assert_called_once_with(session_id="s1")

    def test_get_by_litigation_session_ids(self):
        from apps.core.repositories.conversation_repository import ConversationHistoryRepository

        with patch("apps.core.repositories.conversation_repository.ConversationHistory") as mock_model:
            repo = ConversationHistoryRepository()
            repo.get_by_litigation_session_ids([1, 2, 3])
            mock_model.objects.filter.assert_called_once_with(litigation_session_id__in=[1, 2, 3])

    def test_delete_by_session_id(self):
        from apps.core.repositories.conversation_repository import ConversationHistoryRepository

        with patch("apps.core.repositories.conversation_repository.ConversationHistory") as mock_model:
            repo = ConversationHistoryRepository()
            repo.delete_by_session_id("s1")
            mock_model.objects.filter.assert_called_once_with(session_id="s1")


# =====================================================================
# SystemConfigRepository — repositories/
# =====================================================================

class TestSystemConfigRepository:
    def test_get_by_id(self):
        from apps.core.repositories.system_config_repository import SystemConfigRepository

        with patch("apps.core.repositories.system_config_repository.SystemConfig") as mock_model:
            repo = SystemConfigRepository()
            repo.get_by_id(1)
            mock_model.objects.filter.assert_called_once_with(id=1)

    def test_get_by_key(self):
        from apps.core.repositories.system_config_repository import SystemConfigRepository

        with patch("apps.core.repositories.system_config_repository.SystemConfig") as mock_model:
            repo = SystemConfigRepository()
            repo.get_by_key("KEY")
            mock_model.objects.filter.assert_called_once_with(key="KEY")

    def test_get_by_keys(self):
        from apps.core.repositories.system_config_repository import SystemConfigRepository

        with patch("apps.core.repositories.system_config_repository.SystemConfig") as mock_model:
            repo = SystemConfigRepository()
            repo.get_by_keys(["A", "B"])
            mock_model.objects.filter.assert_called_once_with(key__in=["A", "B"], is_active=True)

    def test_get_all(self):
        from apps.core.repositories.system_config_repository import SystemConfigRepository

        with patch("apps.core.repositories.system_config_repository.SystemConfig") as mock_model:
            repo = SystemConfigRepository()
            repo.get_all()
            mock_model.objects.all.assert_called_once()

    def test_get_all_active(self):
        from apps.core.repositories.system_config_repository import SystemConfigRepository

        with patch("apps.core.repositories.system_config_repository.SystemConfig") as mock_model:
            mock_model.objects.filter.return_value = []
            repo = SystemConfigRepository()
            repo.get_all_active()
            mock_model.objects.filter.assert_called_once_with(is_active=True)

    def test_get_by_category(self):
        from apps.core.repositories.system_config_repository import SystemConfigRepository

        with patch("apps.core.repositories.system_config_repository.SystemConfig") as mock_model:
            repo = SystemConfigRepository()
            repo.get_by_category("general")
            mock_model.objects.filter.assert_called_once_with(category="general", is_active=True)

    def test_delete(self):
        from apps.core.repositories.system_config_repository import SystemConfigRepository

        with patch("apps.core.repositories.system_config_repository.SystemConfig") as mock_model:
            repo = SystemConfigRepository()
            repo.delete(1)
            mock_model.objects.filter.assert_called_once_with(id=1)
