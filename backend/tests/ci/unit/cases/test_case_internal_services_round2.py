"""案件内部服务补测：指派聚合 / 模板绑定查询 / 日志内部服务。

覆盖 CaseAssignmentAggregationService、CaseTemplateBindingQueryService、
CaseLogInternalService 的低覆盖分支。
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from django.utils import timezone

from apps.cases.models import CaseAssignment, CaseTemplateBinding
from apps.cases.services.case.case_assignment_aggregation_service import CaseAssignmentAggregationService
from apps.cases.services.case.case_log_internal_service import CaseLogInternalService
from apps.cases.services.case.case_template_binding_query_service import CaseTemplateBindingQueryService
from apps.core.exceptions import NotFoundError
from apps.documents.models import DocumentTemplate
from apps.testing.factories import CaseFactory, CaseLogFactory, LawyerFactory


@pytest.mark.django_db
class TestCaseAssignmentAggregationService:
    def test_repo_lazy_init(self) -> None:
        service = CaseAssignmentAggregationService()
        assert service.case_assignment_repo is not None
        assert service.case_assignment_repo is service.case_assignment_repo

    def test_empty_case_ids_returns_empty(self) -> None:
        assert CaseAssignmentAggregationService().get_primary_lawyer_names_by_case_ids([]) == {}

    def test_first_assignment_wins(self) -> None:
        case = CaseFactory()
        first = LawyerFactory(real_name="首席律师", username=f"lawyer-{uuid4().hex[:8]}")
        second = LawyerFactory(real_name="辅办律师", username=f"lawyer-{uuid4().hex[:8]}")
        CaseAssignment.objects.create(case=case, lawyer=first)
        CaseAssignment.objects.create(case=case, lawyer=second)

        result = CaseAssignmentAggregationService().get_primary_lawyer_names_by_case_ids([case.id])

        assert result == {case.id: "首席律师"}

    def test_username_fallback_when_real_name_blank(self) -> None:
        case = CaseFactory()
        lawyer = LawyerFactory(real_name="", username=f"lawyer-{uuid4().hex[:8]}")
        CaseAssignment.objects.create(case=case, lawyer=lawyer)

        result = CaseAssignmentAggregationService().get_primary_lawyer_names_by_case_ids([case.id])

        assert result[case.id] == lawyer.username

    def test_missing_case_defaults_to_none(self) -> None:
        case = CaseFactory()
        assigned = CaseAssignment.objects.create(
            case=case, lawyer=LawyerFactory(real_name="A", username=f"lawyer-{uuid4().hex[:8]}")
        )

        result = CaseAssignmentAggregationService().get_primary_lawyer_names_by_case_ids([case.id, 88888])

        assert result[case.id] == "A"
        assert result[88888] is None
        assert assigned.case_id == case.id

    def test_assignment_without_lawyer_maps_to_none(self) -> None:
        """注入 repo 返回无 lawyer 的指派对象时映射为 None（防御分支）。"""
        stub_assignment = SimpleNamespace(case_id=66, lawyer=None)
        service = CaseAssignmentAggregationService(
            case_assignment_repo=SimpleNamespace(list_assignments_by_case_ids=lambda ids: [stub_assignment])
        )

        result = service.get_primary_lawyer_names_by_case_ids([66])

        assert result == {66: None}

    def test_custom_repo_injected(self) -> None:
        stub_repo = SimpleNamespace(list_assignments_by_case_ids=lambda ids: [])
        service = CaseAssignmentAggregationService(case_assignment_repo=stub_repo)
        assert service.case_assignment_repo is stub_repo


@pytest.mark.django_db
class TestCaseTemplateBindingQueryService:
    def _make_binding(self, *, source: str = "manual", template_name: str = "委托书模板", is_active: bool = True):
        case = CaseFactory()
        template = DocumentTemplate.objects.create(name=template_name, file_path=f"{template_name}.docx")
        template.is_active = is_active
        template.save(update_fields=["is_active"])
        binding = CaseTemplateBinding.objects.create(case=case, template=template, binding_source=source)
        return case, template, binding

    def test_no_binding_returns_none(self) -> None:
        case = CaseFactory()
        assert CaseTemplateBindingQueryService().get_case_template_binding_internal(case.id) is None

    def test_binding_mapped_to_dto(self) -> None:
        case, template, binding = self._make_binding()

        dto = CaseTemplateBindingQueryService().get_case_template_binding_internal(case.id)

        assert dto is not None
        assert dto.id == binding.id
        assert dto.case_id == case.id
        assert dto.template_id == template.id
        assert dto.template_name == "委托书模板"
        assert dto.template_function_code is None
        assert dto.binding_source == "manual"
        assert dto.created_at is not None

    def test_bindings_by_name_filters_inactive(self) -> None:
        case, _, binding = self._make_binding(template_name="授权委托书")
        # 同名但停用的模板不返回
        inactive_tpl = DocumentTemplate.objects.create(name="授权委托书", file_path="b.docx")
        inactive_tpl.is_active = False
        inactive_tpl.save(update_fields=["is_active"])
        CaseTemplateBinding.objects.create(case=case, template=inactive_tpl, binding_source="manual")

        result = CaseTemplateBindingQueryService().get_case_template_bindings_by_name_internal(case.id, "授权委托书")

        assert [dto.id for dto in result] == [binding.id]
        assert all(dto.template_name == "授权委托书" for dto in result)

    def test_bindings_by_name_no_match(self) -> None:
        case, _, _ = self._make_binding(template_name="委托书模板")
        result = CaseTemplateBindingQueryService().get_case_template_bindings_by_name_internal(case.id, "不存在模板")
        assert result == []

    def test_binding_query_error_reraised(self) -> None:
        """ORM 异常被记录后原样抛出。"""
        case = CaseFactory()
        with patch(
            "apps.cases.services.case.case_template_binding_query_service.CaseTemplateBinding.objects.select_related",
            side_effect=RuntimeError("db down"),
        ):
            with pytest.raises(RuntimeError, match="db down"):
                CaseTemplateBindingQueryService().get_case_template_binding_internal(case.id)

    def test_bindings_by_name_query_error_reraised(self) -> None:
        case = CaseFactory()
        with patch(
            "apps.cases.services.case.case_template_binding_query_service.CaseTemplateBinding.objects.filter",
            side_effect=RuntimeError("db down"),
        ):
            with pytest.raises(RuntimeError, match="db down"):
                CaseTemplateBindingQueryService().get_case_template_bindings_by_name_internal(case.id, "模板")


@pytest.mark.django_db
class TestCaseLogInternalUpdateReminder:
    def test_missing_log_returns_false(self) -> None:
        assert CaseLogInternalService().update_case_log_reminder_internal(99999, None, "general") is False

    def test_naive_time_made_aware_and_reminder_created(self) -> None:
        log = CaseLogFactory()
        service = CaseLogInternalService()
        naive = datetime(2026, 10, 1, 9, 0, 0)
        reminder_service = MagicMock()
        reminder_service.create_reminder_internal.return_value = {"id": 1}

        with patch(
            "apps.cases.services.case.case_log_internal_service.get_reminder_service",
            return_value=reminder_service,
        ):
            result = service.update_case_log_reminder_internal(log.id, naive, "general")

        assert result is True
        call_kwargs = reminder_service.create_reminder_internal.call_args.kwargs
        assert call_kwargs["case_log_id"] == log.id
        assert call_kwargs["reminder_type"] == "general"
        assert timezone.is_aware(call_kwargs["reminder_time"])

    def test_reminder_failure_returns_false(self) -> None:
        log = CaseLogFactory()
        service = CaseLogInternalService()
        reminder_service = MagicMock()
        reminder_service.create_reminder_internal.return_value = None

        with patch(
            "apps.cases.services.case.case_log_internal_service.get_reminder_service",
            return_value=reminder_service,
        ):
            result = service.update_case_log_reminder_internal(log.id, timezone.now(), "general")

        assert result is False

    def test_exception_returns_false(self) -> None:
        log = CaseLogFactory()
        service = CaseLogInternalService()

        with patch(
            "apps.cases.services.case.case_log_internal_service.get_reminder_service",
            side_effect=RuntimeError("boom"),
        ):
            result = service.update_case_log_reminder_internal(log.id, timezone.now(), "general")

        assert result is False


@pytest.mark.django_db
class TestCaseLogInternalServiceOthers:
    def test_get_case_log_model_internal_found(self) -> None:
        log = CaseLogFactory(content="内容")
        result = CaseLogInternalService().get_case_log_model_internal(log.id)
        assert result is not None
        assert result.content == "内容"

    def test_get_case_log_model_internal_missing(self) -> None:
        assert CaseLogInternalService().get_case_log_model_internal(99999) is None

    def test_create_case_log_internal_success(self) -> None:
        case = CaseFactory()
        actor = LawyerFactory(username=f"lawyer-{uuid4().hex[:8]}")
        service = CaseLogInternalService()

        log_id = service.create_case_log_internal(case.id, "跨模块日志", user_id=actor.id, event_date="2026-10-01")

        assert isinstance(log_id, int)
        log = service.get_case_log_model_internal(log_id)
        assert log is not None
        assert log.actor_id == actor.id

    def test_create_case_log_internal_missing_case(self) -> None:
        with pytest.raises(NotFoundError, match="不存在"):
            CaseLogInternalService().create_case_log_internal(99999, "内容")
