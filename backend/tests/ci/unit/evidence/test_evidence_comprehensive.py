"""evidence 模块单元测试

覆盖文件:
- apps/evidence/models/evidence.py
- apps/evidence/models/enums.py
- apps/evidence/models/group.py
- apps/evidence/models/hearing_note.py
- apps/evidence/api/evidence_api.py
- apps/evidence/services/core/page_range_calculator.py
- apps/evidence/services/wiring.py
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ==================== Enums ====================


class TestEvidenceEnums:
    """证据枚举测试"""

    def test_evidence_direction(self):
        from apps.evidence.models.enums import EvidenceDirection

        assert EvidenceDirection.OUR == "our"
        assert EvidenceDirection.OPPONENT == "opponent"
        assert EvidenceDirection.COURT == "court"

    def test_evidence_type(self):
        from apps.evidence.models.enums import EvidenceType

        assert EvidenceType.DOCUMENTARY == "documentary"
        assert EvidenceType.PHYSICAL == "physical"
        assert EvidenceType.AUDIOVISUAL == "audiovisual"
        assert EvidenceType.ELECTRONIC == "electronic"
        assert EvidenceType.WITNESS == "witness"
        assert EvidenceType.APPRAISAL == "appraisal"
        assert EvidenceType.INSPECTION == "inspection"
        assert EvidenceType.STATEMENT == "statement"

    def test_original_status(self):
        from apps.evidence.models.enums import OriginalStatus

        assert OriginalStatus.HAS_ORIGINAL == "has_original"
        assert OriginalStatus.COPY_ONLY == "copy_only"
        assert OriginalStatus.ELECTRONIC == "electronic"


# ==================== Models ====================


class TestEvidenceListModels:
    """EvidenceList 模型属性测试"""

    def test_list_type_choices(self):
        from apps.evidence.models.evidence import ListType

        assert ListType.LIST_1 == "list_1"
        assert ListType.LIST_6 == "list_6"

    def test_merge_status_choices(self):
        from apps.evidence.models.evidence import MergeStatus

        assert MergeStatus.PENDING == "pending"
        assert MergeStatus.PROCESSING == "processing"
        assert MergeStatus.COMPLETED == "completed"
        assert MergeStatus.FAILED == "failed"

    def test_list_type_order(self):
        from apps.evidence.models.evidence import LIST_TYPE_ORDER, ListType

        assert LIST_TYPE_ORDER[ListType.LIST_1] == 1
        assert LIST_TYPE_ORDER[ListType.LIST_6] == 6

    def test_list_type_previous(self):
        from apps.evidence.models.evidence import LIST_TYPE_PREVIOUS, ListType

        assert LIST_TYPE_PREVIOUS[ListType.LIST_1] is None
        assert LIST_TYPE_PREVIOUS[ListType.LIST_2] == ListType.LIST_1

    def test_evidence_list_str(self, db, case):
        from apps.evidence.models.evidence import EvidenceList

        elist = EvidenceList.objects.create(
            case=case,
            list_type="list_1",
            title="证据清单一",
        )
        assert str(elist) == f"{case.name} - 证据清单一"

    def test_evidence_list_start_order_cached(self, db, case):
        from apps.evidence.models.evidence import EvidenceList

        elist = EvidenceList(case=case, list_type="list_1")
        elist.__dict__["_cached_start_order"] = 5
        assert elist.start_order == 5

    def test_evidence_list_start_page_cached(self, db, case):
        from apps.evidence.models.evidence import EvidenceList

        elist = EvidenceList(case=case, list_type="list_1")
        elist.__dict__["_cached_start_page"] = 10
        assert elist.start_page == 10

    def test_evidence_list_end_page_zero(self, db, case):
        from apps.evidence.models.evidence import EvidenceList

        elist = EvidenceList(case=case, list_type="list_1", total_pages=0)
        elist.__dict__["_cached_start_page"] = 1
        assert elist.end_page == 1

    def test_evidence_list_end_page_nonzero(self, db, case):
        from apps.evidence.models.evidence import EvidenceList

        elist = EvidenceList(case=case, list_type="list_1", total_pages=10)
        elist.__dict__["_cached_start_page"] = 5
        assert elist.end_page == 14

    def test_page_range_display_empty(self, db, case):
        from apps.evidence.models.evidence import EvidenceList

        elist = EvidenceList(case=case, list_type="list_1", total_pages=0)
        assert elist.page_range_display == ""

    def test_page_range_display_range(self, db, case):
        from apps.evidence.models.evidence import EvidenceList

        elist = EvidenceList(case=case, list_type="list_1", total_pages=5)
        elist.__dict__["_cached_start_page"] = 3
        assert elist.page_range_display == "3-7"


class TestEvidenceItemModels:
    """EvidenceItem 模型属性测试"""

    def test_evidence_item_str(self, db, case):
        from apps.evidence.models.evidence import EvidenceItem, EvidenceList

        elist = EvidenceList.objects.create(case=case, list_type="list_1", title="清单")
        item = EvidenceItem.objects.create(
            evidence_list=elist,
            order=1,
            name="合同原件",
            purpose="证明合同关系",
        )
        assert str(item) == "1. 合同原件"

    def test_page_range_display_none(self):
        from apps.evidence.models.evidence import EvidenceItem

        item = EvidenceItem(page_start=None, page_end=None)
        assert item.page_range_display == "-"

    def test_page_range_display_same(self):
        from apps.evidence.models.evidence import EvidenceItem

        item = EvidenceItem(page_start=5, page_end=5)
        assert item.page_range_display == "5"

    def test_page_range_display_range(self):
        from apps.evidence.models.evidence import EvidenceItem

        item = EvidenceItem(page_start=3, page_end=7)
        assert item.page_range_display == "3-7"

    def test_file_size_display_zero(self):
        from apps.evidence.models.evidence import EvidenceItem

        item = EvidenceItem(file_size=0)
        assert item.file_size_display == "-"

    def test_file_size_display_bytes(self):
        from apps.evidence.models.evidence import EvidenceItem

        item = EvidenceItem(file_size=500)
        assert item.file_size_display == "500 B"

    def test_file_size_display_kb(self):
        from apps.evidence.models.evidence import EvidenceItem

        item = EvidenceItem(file_size=2048)
        assert "KB" in item.file_size_display

    def test_file_size_display_mb(self):
        from apps.evidence.models.evidence import EvidenceItem

        item = EvidenceItem(file_size=2 * 1024 * 1024)
        assert "MB" in item.file_size_display


class TestEvidenceGroupModel:
    """EvidenceGroup 模型测试"""

    def test_str(self):
        from apps.evidence.models.group import EvidenceGroup

        group = EvidenceGroup(name="争议焦点一")
        assert str(group) == "争议焦点一"

    def test_meta(self):
        from apps.evidence.models.group import EvidenceGroup

        assert EvidenceGroup._meta.app_label == "evidence"
        assert EvidenceGroup._meta.verbose_name == "证据分组"


class TestHearingNoteModel:
    """HearingNote 模型测试"""

    def test_str(self, db, case):
        from apps.evidence.models.hearing_note import HearingNote

        note = HearingNote(case=case, content="这是一段庭审笔记内容，用于测试显示截断效果的文本")
        assert str(note) == f"{case.id} - 这是一段庭审笔记内容，用于测试显示截断效果的文本"

    def test_meta(self):
        from apps.evidence.models.hearing_note import HearingNote

        assert HearingNote._meta.app_label == "evidence"
        assert HearingNote._meta.verbose_name == "庭审笔记"


# ==================== PageRangeCalculator ====================


class TestPageRangeCalculator:
    """EvidencePageRangeCalculator 测试"""

    def test_calculate_page_ranges_empty_list(self, db, case):
        from apps.evidence.models.evidence import EvidenceList
        from apps.evidence.services.core.page_range_calculator import EvidencePageRangeCalculator

        elist = EvidenceList.objects.create(
            case=case, list_type="list_1", title="清单", total_pages=0
        )
        elist.__dict__["_cached_start_page"] = 1

        calc = EvidencePageRangeCalculator()
        with patch.object(type(elist), 'start_page', new_callable=lambda: property(lambda self: 1)):
            calc.calculate_page_ranges(evidence_list=elist)
        assert elist.total_pages == 0

    def test_calculate_page_ranges_with_items(self, db, case):
        from apps.evidence.models.evidence import EvidenceItem, EvidenceList
        from apps.evidence.services.core.page_range_calculator import EvidencePageRangeCalculator

        elist = EvidenceList.objects.create(
            case=case, list_type="list_1", title="清单", total_pages=0
        )
        elist.__dict__["_cached_start_page"] = 1

        item1 = EvidenceItem.objects.create(
            evidence_list=elist, order=1, name="证据1", purpose="证明", page_count=3
        )
        item2 = EvidenceItem.objects.create(
            evidence_list=elist, order=2, name="证据2", purpose="证明", page_count=2
        )

        calc = EvidencePageRangeCalculator()
        with patch.object(type(elist), 'start_page', new_callable=lambda: property(lambda self: 1)):
            calc.calculate_page_ranges(evidence_list=elist)

        item1.refresh_from_db()
        item2.refresh_from_db()
        assert item1.page_start == 1
        assert item1.page_end == 3
        assert item2.page_start == 4
        assert item2.page_end == 5
        assert elist.total_pages == 5


# ==================== API Schemas ====================


class TestEvidenceApiSchemas:
    """API Schema 测试"""

    def test_reorder_items_request(self):
        from apps.evidence.api.evidence_api import ReorderItemsRequest

        req = ReorderItemsRequest(item_ids=[3, 1, 2])
        assert req.item_ids == [3, 1, 2]

    def test_reorder_items_response(self):
        from apps.evidence.api.evidence_api import ReorderItemsResponse

        resp = ReorderItemsResponse(success=True, message="ok")
        assert resp.success is True

    def test_ai_purpose_request(self):
        from apps.evidence.api.evidence_api import AIPurposeRequest

        req = AIPurposeRequest(cause_of_action="合同纠纷", evidence_name="合同")
        assert req.cause_of_action == "合同纠纷"

    def test_ai_purpose_response(self):
        from apps.evidence.api.evidence_api import AIPurposeResponse

        resp = AIPurposeResponse(suggestions=["证明合同关系", "证明违约"])
        assert len(resp.suggestions) == 2

    def test_ai_cross_exam_request(self):
        from apps.evidence.api.evidence_api import AICrossExamRequest

        req = AICrossExamRequest(cause_of_action="合同纠纷", evidence_name="合同")
        assert req.cause_of_action == "合同纠纷"

    def test_ai_cross_exam_response(self):
        from apps.evidence.api.evidence_api import AICrossExamResponse

        resp = AICrossExamResponse(cross_examination={"opinion": "无异议"})
        assert resp.cross_examination["opinion"] == "无异议"


# ==================== API Endpoints ====================


class TestEvidenceApiEndpoints:
    """API 端点测试"""

    @patch("apps.evidence.api.evidence_api._get_evidence_service")
    def test_reorder_items(self, mock_get_svc):
        from apps.evidence.api.evidence_api import reorder_evidence_items, ReorderItemsRequest

        mock_svc = MagicMock()
        mock_get_svc.return_value = mock_svc

        request = MagicMock()
        data = ReorderItemsRequest(item_ids=[3, 1, 2])
        result = reorder_evidence_items(request, list_id=1, data=data)
        assert result.success is True
        mock_svc.reorder_items.assert_called_once_with(1, [3, 1, 2])

    @patch("apps.evidence.api.evidence_api._get_ai_service")
    def test_ai_suggest_purpose(self, mock_get_svc):
        from apps.evidence.api.evidence_api import ai_suggest_purpose, AIPurposeRequest

        mock_svc = MagicMock()
        mock_svc.suggest_purpose.return_value = ["建议1", "建议2"]
        mock_get_svc.return_value = mock_svc

        request = MagicMock()
        data = AIPurposeRequest(cause_of_action="合同纠纷")
        result = ai_suggest_purpose(request, data)
        assert len(result.suggestions) == 2

    @patch("apps.evidence.api.evidence_api._get_ai_service")
    def test_ai_generate_cross_examination(self, mock_get_svc):
        from apps.evidence.api.evidence_api import ai_generate_cross_examination, AICrossExamRequest

        mock_svc = MagicMock()
        mock_svc.generate_cross_examination.return_value = {"opinion": "对真实性无异议"}
        mock_get_svc.return_value = mock_svc

        request = MagicMock()
        data = AICrossExamRequest(cause_of_action="合同纠纷")
        result = ai_generate_cross_examination(request, data)
        assert result.cross_examination["opinion"] == "对真实性无异议"


# ==================== Wiring ====================


class TestEvidenceWiring:
    """evidence wiring 测试"""

    def test_get_evidence_service(self):
        from apps.evidence.services.wiring import get_evidence_service

        svc = get_evidence_service()
        assert svc is not None
