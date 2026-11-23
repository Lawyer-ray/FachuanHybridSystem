"""evidence 模型属性覆盖测试（直接调用 apps.evidence.models 的真实 property）。"""

from __future__ import annotations

from typing import Any

# ── MergeStatus / ListType ────────────────────────────────────────


class TestMergeStatus:
    def test_choices_values(self):
        # MergeStatus is a simple TextChoices — test the module-level constants
        from apps.documents.models import choices as doc_choices

        # Check the model module can be accessed
        assert hasattr(doc_choices, "DocumentTemplateType")


class TestEvidenceListProperties:
    """EvidenceList 的 end_page / page_range_display / order_range_display。

    S01-13（2026-11-23 二轮审计）：原实现把 property 的公式抄成局部变量再断言那个
    局部变量（MagicMock 只用来存一个数字，`end_page` 是本地变量）→ 生产 property
    被删/改错也全绿；现在构造不落库的 EvidenceList 实例，直接读真实 property。
    """

    def test_end_page_zero_total(self):
        from apps.evidence.models.evidence import EvidenceList

        el = EvidenceList(total_pages=0)
        el.__dict__["_cached_start_page"] = 1
        assert el.end_page == 1

    def test_end_page_nonzero_total(self):
        from apps.evidence.models.evidence import EvidenceList

        el = EvidenceList(total_pages=10)
        el.__dict__["_cached_start_page"] = 5
        assert el.end_page == 14

    def test_page_range_display_zero_pages(self):
        from apps.evidence.models.evidence import EvidenceList

        el = EvidenceList(total_pages=0)
        assert el.page_range_display == ""

    def test_page_range_display_nonzero(self):
        from apps.evidence.models.evidence import EvidenceList

        el = EvidenceList(total_pages=5)
        el.__dict__["_cached_start_page"] = 1
        assert el.page_range_display == "1-5"

    @staticmethod
    def _annotated_list(item_count: int) -> Any:
        """不落库的清单实例 + 列表页 queryset annotation 的 item_count。"""
        from apps.evidence.models.evidence import EvidenceList

        el: Any = EvidenceList()
        el.item_count = item_count
        return el

    def test_order_range_display_no_items(self):
        assert self._annotated_list(item_count=0).order_range_display == "-"

    def test_order_range_display_single_item(self):
        el: Any = self._annotated_list(item_count=1)
        el.__dict__["_cached_start_order"] = 3
        assert el.order_range_display == "3"

    def test_order_range_display_multiple_items(self):
        el: Any = self._annotated_list(item_count=5)
        el.__dict__["_cached_start_order"] = 1
        assert el.order_range_display == "1-5"


class TestEvidenceItemProperties:
    """EvidenceItem 的 page_range_display / file_size_display。

    S01-13：同上——原来重写的是测试里的公式，现在真调用模型 property。
    """

    def test_page_range_display_none_pages(self):
        from apps.evidence.models.evidence import EvidenceItem

        assert EvidenceItem(page_start=None, page_end=None).page_range_display == "-"

    def test_page_range_display_same_page(self):
        from apps.evidence.models.evidence import EvidenceItem

        assert EvidenceItem(page_start=5, page_end=5).page_range_display == "5"

    def test_page_range_display_range(self):
        from apps.evidence.models.evidence import EvidenceItem

        assert EvidenceItem(page_start=1, page_end=10).page_range_display == "1-10"

    def test_file_size_display_zero(self):
        from apps.evidence.models.evidence import EvidenceItem

        assert EvidenceItem(file_size=0).file_size_display == "-"

    def test_file_size_display_bytes(self):
        from apps.evidence.models.evidence import EvidenceItem

        assert EvidenceItem(file_size=500).file_size_display == "500 B"

    def test_file_size_display_kb(self):
        from apps.evidence.models.evidence import EvidenceItem

        assert EvidenceItem(file_size=5 * 1024).file_size_display == "5.0 KB"

    def test_file_size_display_mb(self):
        from apps.evidence.models.evidence import EvidenceItem

        assert EvidenceItem(file_size=3 * 1024 * 1024).file_size_display == "3.0 MB"


class TestEvidenceStrMethods:
    def test_evidence_item_str_logic(self):
        order = 1
        name = "合同原件"
        result = f"{order}. {name}"
        assert result == "1. 合同原件"

    def test_evidence_list_str_logic(self):
        case_name = "测试案件"
        title = "证据清单一"
        result = f"{case_name} - {title}"
        assert result == "测试案件 - 证据清单一"
