"""
Tests for core/tasking/ - context, entries, convenience, exceptions.
Also tests for core/services/wiring.py, core/config/__init__.py.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest


class TestTaskContext:
    def test_create_default(self):
        from apps.core.tasking.context import TaskContext

        ctx = TaskContext()
        assert ctx.request_id is None
        assert ctx.correlation_id is None
        assert ctx.task_name is None

    def test_create_with_values(self):
        from apps.core.tasking.context import TaskContext

        ctx = TaskContext(request_id="req-1", task_name="my_task", entity_id="42")
        assert ctx.request_id == "req-1"
        assert ctx.task_name == "my_task"

    def test_to_dict(self):
        from apps.core.tasking.context import TaskContext

        ctx = TaskContext(request_id="r1", task_name="t1")
        d = ctx.to_dict()
        assert d["request_id"] == "r1"
        assert d["task_name"] == "t1"
        assert d["extra"] == {}

    def test_from_dict_none(self):
        from apps.core.tasking.context import TaskContext

        ctx = TaskContext.from_dict(None)
        assert ctx.request_id is None

    def test_from_dict_with_values(self):
        from apps.core.tasking.context import TaskContext

        ctx = TaskContext.from_dict({"request_id": "r1", "task_name": "t1", "extra": {"k": "v"}})
        assert ctx.request_id == "r1"
        assert ctx.extra == {"k": "v"}

    def test_from_dict_empty(self):
        from apps.core.tasking.context import TaskContext

        ctx = TaskContext.from_dict({})
        assert ctx.request_id is None
        assert ctx.extra == {}

    def test_frozen(self):
        from apps.core.tasking.context import TaskContext

        ctx = TaskContext(request_id="r1")
        with pytest.raises(AttributeError):
            ctx.request_id = "r2"


class TestTaskEntries:
    def test_import_callable(self):
        from apps.core.tasking.entries import _import_callable

        func = _import_callable("os.path.join")
        assert callable(func)

    def test_run_task_success(self):
        from apps.core.tasking.entries import run_task

        with patch("apps.core.tasking.entries.set_current_request_id"):
            result = run_task(
                target="os.path.join",
                args=["a", "b"],
            )
            import os
            assert result == os.path.join("a", "b")

    def test_run_task_with_context(self):
        from apps.core.tasking.entries import run_task

        with patch("apps.core.tasking.entries.set_current_request_id"):
            result = run_task(
                target="os.path.join",
                args=["x", "y"],
                context={"request_id": "req-1", "task_name": "test_task"},
            )
            import os
            assert result == os.path.join("x", "y")

    def test_run_task_failure_raises(self):
        from apps.core.tasking.entries import run_task

        with patch("apps.core.tasking.entries.set_current_request_id"):
            with pytest.raises((TypeError, ValueError)):
                run_task(
                    target="builtins.int",
                    args=["not_a_number"],
                    context={"task_name": "failing_task"},
                )


class TestTaskConvenience:
    def test_get_submission_service_singleton(self):
        from apps.core.tasking.convenience import _get_submission_service, _submission_service

        # Reset the global
        import apps.core.tasking.convenience as mod
        mod._submission_service = None

        svc1 = _get_submission_service()
        svc2 = _get_submission_service()
        assert svc1 is svc2

    def test_submit_task(self):
        from apps.core.tasking.convenience import submit_task
        import apps.core.tasking.convenience as mod

        mock_service = MagicMock()
        mock_service.submit.return_value = "task-123"
        mod._submission_service = mock_service

        result = submit_task("some.task.func", 1, 2, task_name="test")
        assert result == "task-123"
        mock_service.submit.assert_called_once()

    def teardown_method(self):
        import apps.core.tasking.convenience as mod
        mod._submission_service = None


class TestTaskExceptions:
    def test_task_timeout_error_import(self):
        from apps.core.tasking.exceptions import TaskTimeoutError

        assert TaskTimeoutError is not None
        assert issubclass(TaskTimeoutError, BaseException)


class TestCoreWiring:
    def test_wiring_imports(self):
        from apps.core.services import wiring

        assert wiring is not None


class TestConfigInit:
    def test_get_config_exists(self):
        from apps.core.config import get_config

        assert callable(get_config)

    def test_get_config_default(self):
        from apps.core.config import get_config

        result = get_config("nonexistent.key.xyz", "default_val")
        assert result == "default_val"


class TestCoreExceptionsErrorCatalog:
    def test_error_catalog_imports(self):
        from apps.core.exceptions.error_catalog import NotFoundError, case_not_found

        assert NotFoundError is not None
        assert callable(case_not_found)


class TestCoreDtos:
    def test_cases_dto(self):
        from apps.core.dto.cases import CaseDTO

        assert CaseDTO is not None

    def test_chat_dto(self):
        from apps.core.dto.chat import MessageContent

        assert MessageContent is not None

    def test_client_dto(self):
        from apps.core.dto.client import ClientDTO

        assert ClientDTO is not None

    def test_contracts_dto(self):
        from apps.core.dto.contracts import ContractDTO

        assert ContractDTO is not None

    def test_organization_dto(self):
        from apps.core.dto.organization import LawFirmDTO

        assert LawFirmDTO is not None

    def test_reminders_dto(self):
        from apps.core.dto.reminders import ReminderDTO

        assert ReminderDTO is not None


class TestModelFields:
    def test_encrypted_module_exists(self):
        import apps.core.model_fields.encrypted as mod

        assert mod is not None


class TestCoreModels:
    @pytest.mark.django_db
    def test_enums_import(self):
        from apps.core.models.enums import CaseStage, LegalStatus, SimpleCaseType

        assert len(CaseStage.choices) > 0
        assert len(LegalStatus.choices) > 0
        assert len(SimpleCaseType.choices) > 0
