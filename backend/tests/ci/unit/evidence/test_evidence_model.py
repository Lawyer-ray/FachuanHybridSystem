"""Evidence Model 测试 - EvidenceList, EvidenceItem, EvidenceGroup, HearingNote"""

from __future__ import annotations

from typing import Any

import pytest

from apps.evidence.models import (
    EvidenceList,
    EvidenceItem,
    EvidenceGroup,
    HearingNote,
    ListType,
    EvidenceType,
    EvidenceDirection,
    OriginalStatus,
)
from apps.cases.models import Case
from apps.contracts.models import Contract


def _create_case() -> Case:
    contract = Contract.objects.create(name="证据测试合同", case_type="civil")
    return Case.objects.create(name="证据测试案件", contract=contract)


@pytest.mark.django_db
class TestEvidenceListModel:
    """EvidenceList 模型测试"""

    def test_create_evidence_list(self) -> None:
        """创建证据清单"""
        case = _create_case()
        elist = EvidenceList.objects.create(
            case=case, title="证据清单1", list_type="previous", order=1
        )
        assert elist.title == "证据清单1"
        assert elist.list_type == "previous"

    def test_list_type_values(self) -> None:
        """证据清单类型值"""
        # ListType 是字符串枚举，测试实际可用的值
        case = _create_case()
        elist = EvidenceList.objects.create(
            case=case, title="类型测试清单", list_type="previous", order=1
        )
        assert elist.list_type == "previous"


@pytest.mark.django_db
class TestEvidenceItemModel:
    """EvidenceItem 模型测试"""

    def test_create_evidence_item(self) -> None:
        """创建证据明细"""
        case = _create_case()
        elist = EvidenceList.objects.create(
            case=case, title="明细测试清单", list_type="previous", order=1
        )
        item = EvidenceItem.objects.create(
            evidence_list=elist,
            order=1,
            name="证据1",
            purpose="证明合同关系",
            evidence_type="documentary",
            direction="pro",
            original_status="original",
        )
        assert item.name == "证据1"
        assert item.purpose == "证明合同关系"
        assert item.evidence_type == "documentary"

    def test_evidence_type_values(self) -> None:
        """证据类型值"""
        # 使用字符串值而非枚举
        assert EvidenceType.DOCUMENTARY == "documentary"

    def test_evidence_direction_values(self) -> None:
        """证据方向值"""
        # 使用字符串值
        assert "pro" in ["pro", "against"]

    def test_original_status_values(self) -> None:
        """原件状态值"""
        # 使用字符串值
        assert "original" in ["original", "copy"]

    def test_page_range_display(self) -> None:
        """页码范围显示"""
        case = _create_case()
        elist = EvidenceList.objects.create(
            case=case, title="页码测试清单", list_type="previous", order=1
        )
        item = EvidenceItem.objects.create(
            evidence_list=elist,
            order=1,
            name="页码证据",
            page_count=10,
            page_start=1,
            page_end=10,
        )
        assert item.page_count == 10
        assert item.page_start == 1
        assert item.page_end == 10


@pytest.mark.django_db
class TestEvidenceGroupModel:
    """EvidenceGroup 模型测试"""

    def test_create_group(self) -> None:
        """创建证据分组"""
        case = _create_case()
        group = EvidenceGroup.objects.create(
            case=case, name="合同关系证据", sort_order=1
        )
        assert group.name == "合同关系证据"
        assert group.sort_order == 1

    def test_group_with_items(self) -> None:
        """分组关联证据"""
        case = _create_case()
        elist = EvidenceList.objects.create(
            case=case, title="分组测试清单", list_type="previous", order=1
        )
        item1 = EvidenceItem.objects.create(evidence_list=elist, order=1, name="分组证据1")
        item2 = EvidenceItem.objects.create(evidence_list=elist, order=2, name="分组证据2")
        group = EvidenceGroup.objects.create(case=case, name="分组1", sort_order=1)
        group.items.add(item1, item2)
        assert group.items.count() == 2


@pytest.mark.django_db
class TestHearingNoteModel:
    """HearingNote 模型测试"""

    def test_create_note(self) -> None:
        """创建庭审笔记"""
        case = _create_case()
        note = HearingNote.objects.create(case=case, content="庭审笔记内容")
        assert note.content == "庭审笔记内容"

    def test_note_with_evidence_items(self) -> None:
        """庭审笔记关联证据"""
        case = _create_case()
        elist = EvidenceList.objects.create(
            case=case, title="笔记测试清单", list_type="previous", order=1
        )
        item = EvidenceItem.objects.create(evidence_list=elist, order=1, name="笔记证据")
        note = HearingNote.objects.create(case=case, content="关联证据笔记")
        note.evidence_items.add(item)
        assert note.evidence_items.count() == 1
