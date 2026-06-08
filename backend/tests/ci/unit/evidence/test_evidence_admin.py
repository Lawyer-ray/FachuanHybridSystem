"""Evidence Admin 测试 - EvidenceListAdmin, EvidenceItemAdmin, EvidenceGroupAdmin, HearingNoteAdmin"""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.evidence.admin.evidence_admin import EvidenceListAdmin
from apps.evidence.admin.evidence_item_admin import EvidenceItemAdmin
from apps.evidence.admin.group_admin import EvidenceGroupAdmin
from apps.evidence.admin.hearing_note_admin import HearingNoteAdmin
from apps.evidence.models import EvidenceGroup, EvidenceItem, EvidenceList, HearingNote
from apps.cases.models import Case
from apps.contracts.models import Contract

User = get_user_model()


def _make_request(path: str = "/admin/") -> Any:
    factory = RequestFactory()
    request = factory.get(path)
    request.user = User(is_superuser=True, is_staff=True)
    return request


def _create_case(name: str = "证据测试案件") -> Case:
    contract = Contract.objects.create(name=f"证据测试合同-{name}", case_type="civil")
    return Case.objects.create(name=name, contract=contract)


@pytest.mark.django_db
class TestEvidenceListAdmin:
    """EvidenceListAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = EvidenceListAdmin(EvidenceList, AdminSite())
        assert "title" in admin_obj.list_display
        assert "case_display" in admin_obj.list_display
        assert "list_type" in admin_obj.list_display

    def test_list_select_related(self) -> None:
        """list_select_related 包含 case 和 created_by"""
        admin_obj = EvidenceListAdmin(EvidenceList, AdminSite())
        assert "case" in admin_obj.list_select_related
        assert "created_by" in admin_obj.list_select_related

    def test_get_queryset_annotate_item_count(self) -> None:
        """get_queryset 应使用 annotate(Count) 计算 item_count"""
        case = _create_case()
        elist = EvidenceList.objects.create(
            case=case, title="证据清单1", list_type="previous", order=1
        )
        EvidenceItem.objects.create(evidence_list=elist, order=1, name="证据1")
        EvidenceItem.objects.create(evidence_list=elist, order=2, name="证据2")

        admin_obj = EvidenceListAdmin(EvidenceList, AdminSite())
        qs = admin_obj.get_queryset(_make_request())
        results = list(qs)
        assert len(results) == 1
        assert results[0].item_count == 2


@pytest.mark.django_db
class TestEvidenceItemAdmin:
    """EvidenceItemAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = EvidenceItemAdmin(EvidenceItem, AdminSite())
        assert "order" in admin_obj.list_display
        assert "name" in admin_obj.list_display
        assert "evidence_type" in admin_obj.list_display

    def test_search_fields(self) -> None:
        """search_fields 包含 name"""
        admin_obj = EvidenceItemAdmin(EvidenceItem, AdminSite())
        assert "name" in admin_obj.search_fields


@pytest.mark.django_db
class TestEvidenceGroupAdmin:
    """EvidenceGroupAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = EvidenceGroupAdmin(EvidenceGroup, AdminSite())
        assert "name" in admin_obj.list_display
        assert "case" in admin_obj.list_display
        assert "item_count" in admin_obj.list_display

    def test_get_queryset_annotate_item_count(self) -> None:
        """get_queryset 应使用 annotate(Count) 计算 item_count"""
        case = _create_case("分组测试案件")
        elist = EvidenceList.objects.create(
            case=case, title="分组证据清单", list_type="previous", order=1
        )
        item1 = EvidenceItem.objects.create(evidence_list=elist, order=1, name="分组证据1")
        item2 = EvidenceItem.objects.create(evidence_list=elist, order=2, name="分组证据2")
        group = EvidenceGroup.objects.create(case=case, name="证据分组1", sort_order=1)
        group.items.add(item1, item2)

        admin_obj = EvidenceGroupAdmin(EvidenceGroup, AdminSite())
        qs = admin_obj.get_queryset(_make_request())
        results = list(qs)
        assert len(results) == 1
        assert results[0].item_count == 2

    def test_item_count_display_uses_annotation(self) -> None:
        """item_count display 方法应使用 annotate 的值"""
        case = _create_case("显示测试案件")
        elist = EvidenceList.objects.create(
            case=case, title="显示证据清单", list_type="previous", order=1
        )
        item = EvidenceItem.objects.create(evidence_list=elist, order=1, name="显示证据")
        group = EvidenceGroup.objects.create(case=case, name="显示分组", sort_order=1)
        group.items.add(item)

        admin_obj = EvidenceGroupAdmin(EvidenceGroup, AdminSite())
        qs = admin_obj.get_queryset(_make_request())
        obj = qs.first()
        assert admin_obj.item_count(obj) == 1


@pytest.mark.django_db
class TestHearingNoteAdmin:
    """HearingNoteAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = HearingNoteAdmin(HearingNote, AdminSite())
        assert "case" in admin_obj.list_display
        assert "content_short" in admin_obj.list_display
        assert "evidence_count" in admin_obj.list_display

    def test_list_select_related(self) -> None:
        """list_select_related 包含 case"""
        admin_obj = HearingNoteAdmin(HearingNote, AdminSite())
        assert "case" in admin_obj.list_select_related

    def test_get_queryset_annotate_evidence_count(self) -> None:
        """get_queryset 应使用 annotate(Count) 计算 evidence_count"""
        case = _create_case("庭审笔记测试案件")
        elist = EvidenceList.objects.create(
            case=case, title="庭审笔记证据清单", list_type="previous", order=1
        )
        item = EvidenceItem.objects.create(evidence_list=elist, order=1, name="庭审笔记证据")
        note = HearingNote.objects.create(case=case, content="庭审笔记内容")
        note.evidence_items.add(item)

        admin_obj = HearingNoteAdmin(HearingNote, AdminSite())
        qs = admin_obj.get_queryset(_make_request())
        results = list(qs)
        assert len(results) == 1
        assert results[0].evidence_count == 1

    def test_content_short_truncation(self) -> None:
        """content_short 应截断长内容"""
        case = _create_case("截断测试案件")
        long_content = "a" * 100
        note = HearingNote.objects.create(case=case, content=long_content)

        admin_obj = HearingNoteAdmin(HearingNote, AdminSite())
        result = admin_obj.content_short(note)
        assert len(result) <= 53  # 50 + "..."
        assert result.endswith("...")

    def test_content_short_no_truncation(self) -> None:
        """content_short 不应截断短内容"""
        case = _create_case("短内容测试案件")
        note = HearingNote.objects.create(case=case, content="短内容")

        admin_obj = HearingNoteAdmin(HearingNote, AdminSite())
        result = admin_obj.content_short(note)
        assert result == "短内容"
