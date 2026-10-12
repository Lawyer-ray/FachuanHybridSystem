"""案件指派按合同 diff 同步的回归测试。

背景（2026-10-12 案件 389 事故）：旧实现 sync_assignments_from_contract 先删光
案件全部指派再按合同重建，案件级手动添加的律师被静默抹掉。现契约：

- source=manual 的行（手动添加/改派）任何同步都不删除、不覆盖；
- source=contract 的行跟随合同：合同上已移除的删掉、新出现的补建；
- 同一律师已有 manual 行时，合同同步不重复建行（uniq case+lawyer）。
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from django.db import models as dj_models

from apps.cases.models import Case, CaseAssignment, CaseAssignmentSource
from apps.cases.services.case.case_admin_service import CaseAdminService
from apps.cases.services.party.case_assignment_service import CaseAssignmentService
from apps.contracts.models import Contract, ContractAssignment
from apps.contracts.services.assignment.contract_assignment_query_service import ContractAssignmentQueryService
from apps.core.exceptions import NotFoundError
from apps.testing.factories import CaseFactory, LawyerFactory


def _lawyer(real_name: str):
    return LawyerFactory(real_name=real_name, username=f"lawyer-{uuid4().hex[:8]}")


def _case_with_contract() -> tuple[Case, Contract]:
    """CaseFactory 必带合同；此处同时做非空窄化。"""
    case = CaseFactory()
    contract = case.contract
    assert contract is not None
    return case, contract


def _service() -> CaseAssignmentService:
    return CaseAssignmentService(contract_assignment_query_service=ContractAssignmentQueryService())


def _sync(case_id: int) -> dict[str, int]:
    return _service().sync_assignments_from_contract(case_id=case_id, user=None, perm_open_access=True)


@pytest.mark.django_db
class TestSyncAssignmentsFromContractDiff:
    def test_manual_row_survives_sync(self) -> None:
        """核心回归：合同上没有的 manual 律师（案件 389 黄崧场景）不被清掉。"""
        case, contract = _case_with_contract()
        contract_lawyer = _lawyer("合同律师")
        manual_lawyer = _lawyer("手动律师")
        ContractAssignment.objects.create(contract=contract, lawyer=contract_lawyer)
        manual_row = CaseAssignment.objects.create(case=case, lawyer=manual_lawyer, source=CaseAssignmentSource.MANUAL)

        stats = _sync(case.id)

        assert stats == {"created": 1, "deleted": 0}
        assert CaseAssignment.objects.filter(pk=manual_row.pk).exists()
        new_row = CaseAssignment.objects.get(case=case, lawyer=contract_lawyer)
        assert new_row.source == CaseAssignmentSource.CONTRACT

    def test_stale_contract_row_removed(self) -> None:
        """合同上已移除的律师，其 contract 行被清理；manual 行不受影响。"""
        case, contract = _case_with_contract()
        removed = _lawyer("已移除")
        kept = _lawyer("仍在合同")
        manual = _lawyer("仅案件")
        ContractAssignment.objects.create(contract=contract, lawyer=kept)
        stale_row = CaseAssignment.objects.create(case=case, lawyer=removed, source=CaseAssignmentSource.CONTRACT)
        manual_row = CaseAssignment.objects.create(case=case, lawyer=manual)

        stats = _sync(case.id)

        assert stats == {"created": 1, "deleted": 1}
        assert not CaseAssignment.objects.filter(pk=stale_row.pk).exists()
        assert CaseAssignment.objects.filter(pk=manual_row.pk).exists()

    def test_missing_contract_lawyer_added_with_contract_source(self) -> None:
        case, contract = _case_with_contract()
        lawyer = _lawyer("合同律师")
        ContractAssignment.objects.create(contract=contract, lawyer=lawyer)

        stats = _sync(case.id)

        assert stats == {"created": 1, "deleted": 0}
        row = CaseAssignment.objects.get(case=case, lawyer=lawyer)
        assert row.source == CaseAssignmentSource.CONTRACT

    def test_manual_row_blocks_duplicate_for_same_lawyer(self) -> None:
        """同一律师已有 manual 行时，同步不重复建行也不删除该行。"""
        case, contract = _case_with_contract()
        lawyer = _lawyer("两处都有")
        ContractAssignment.objects.create(contract=contract, lawyer=lawyer)
        manual_row = CaseAssignment.objects.create(case=case, lawyer=lawyer)

        stats = _sync(case.id)

        assert stats == {"created": 0, "deleted": 0}
        assert CaseAssignment.objects.filter(case=case, lawyer=lawyer).count() == 1
        manual_row.refresh_from_db()
        assert manual_row.source == CaseAssignmentSource.MANUAL

    def test_sync_is_idempotent(self) -> None:
        case, contract = _case_with_contract()
        lawyer = _lawyer("合同律师")
        ContractAssignment.objects.create(contract=contract, lawyer=lawyer)

        first = _sync(case.id)
        second = _sync(case.id)

        assert first == {"created": 1, "deleted": 0}
        assert second == {"created": 0, "deleted": 0}
        assert CaseAssignment.objects.filter(case=case).count() == 1

    def test_case_without_contract_noop(self) -> None:
        case = CaseFactory()
        Case.objects.filter(pk=case.pk).update(contract=None)
        assert _sync(case.id) == {"created": 0, "deleted": 0}

    def test_case_not_found_raises(self) -> None:
        with pytest.raises(NotFoundError):
            _sync(99999999)

    def test_existing_rows_default_to_manual_after_migration(self) -> None:
        """迁移默认 manual：未显式指定来源的存量/新行都受保护。"""
        case = CaseFactory()
        row = CaseAssignment.objects.create(case=case, lawyer=_lawyer("默认来源"))
        row.refresh_from_db()
        assert row.source == CaseAssignmentSource.MANUAL


@pytest.mark.django_db
class TestAssignmentMutationMarksManual:
    def test_update_assignment_lawyer_change_marks_manual(self) -> None:
        case = CaseFactory()
        old_lawyer = _lawyer("原律师")
        new_lawyer = _lawyer("新律师")
        row = CaseAssignment.objects.create(case=case, lawyer=old_lawyer, source=CaseAssignmentSource.CONTRACT)

        updated = _service().update_assignment(row.id, {"lawyer_id": new_lawyer.id}, user=None, perm_open_access=True)

        assert updated.lawyer_id == new_lawyer.id
        updated.refresh_from_db()
        assert updated.source == CaseAssignmentSource.MANUAL

    def test_update_assignment_without_lawyer_change_keeps_source(self) -> None:
        case = CaseFactory()
        lawyer = _lawyer("不变律师")
        row = CaseAssignment.objects.create(case=case, lawyer=lawyer, source=CaseAssignmentSource.CONTRACT)

        _service().update_assignment(row.id, {}, user=None, perm_open_access=True)

        row.refresh_from_db()
        assert row.source == CaseAssignmentSource.CONTRACT

    def test_duplicate_case_preserves_source(self) -> None:
        case = CaseFactory()
        contract_lawyer = _lawyer("合同律师")
        manual_lawyer = _lawyer("手动律师")
        CaseAssignment.objects.create(case=case, lawyer=contract_lawyer, source=CaseAssignmentSource.CONTRACT)
        CaseAssignment.objects.create(case=case, lawyer=manual_lawyer, source=CaseAssignmentSource.MANUAL)

        copy = CaseAdminService().duplicate_case(case.id)

        assert copy.assignments.count() == 2
        assert copy.assignments.get(lawyer=contract_lawyer).source == CaseAssignmentSource.CONTRACT
        assert copy.assignments.get(lawyer=manual_lawyer).source == CaseAssignmentSource.MANUAL


class TestMarkAssignmentSource:
    """admin inline 保存时的来源标记规则（纯逻辑，无 DB）。"""

    @staticmethod
    def _instance(pk: int | None, lawyer_id: int) -> CaseAssignment:
        return CaseAssignment(pk=pk, case_id=1, lawyer_id=lawyer_id)

    def test_new_row_marked_manual(self) -> None:
        from apps.cases.admin.mixins.save import _mark_assignment_source

        obj = self._instance(None, 7)
        _mark_assignment_source(obj, None)
        assert obj.source == CaseAssignmentSource.MANUAL

    def test_lawyer_changed_row_marked_manual(self) -> None:
        from apps.cases.admin.mixins.save import _mark_assignment_source

        obj = self._instance(5, 9)
        _mark_assignment_source(obj, (7, CaseAssignmentSource.CONTRACT))
        assert obj.source == CaseAssignmentSource.MANUAL

    def test_unchanged_row_keeps_source(self) -> None:
        from apps.cases.admin.mixins.save import _mark_assignment_source

        obj = self._instance(5, 7)
        obj.source = CaseAssignmentSource.CONTRACT
        _mark_assignment_source(obj, (7, CaseAssignmentSource.CONTRACT))
        assert obj.source == CaseAssignmentSource.CONTRACT

    def test_missing_original_keeps_source(self) -> None:
        from apps.cases.admin.mixins.save import _mark_assignment_source

        obj = self._instance(5, 7)
        obj.source = CaseAssignmentSource.CONTRACT
        _mark_assignment_source(obj, None)
        assert obj.source == CaseAssignmentSource.CONTRACT


def test_source_choices_persisted() -> None:
    """字段 choices 与迁移保持一致，防止误改枚举值。"""
    assert CaseAssignmentSource.CONTRACT == "contract"
    assert CaseAssignmentSource.MANUAL == "manual"
    field = CaseAssignment._meta.get_field("source")
    assert field.get_default() == CaseAssignmentSource.MANUAL
    assert field.max_length == 16
    assert isinstance(field, dj_models.CharField)
