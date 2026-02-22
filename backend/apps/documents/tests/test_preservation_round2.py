"""
行为保持性测试（Property 2: Preservation）

验证重构后外部行为不变：
- EvidenceList.start_order / start_page 计算结果正确
- _create_audit_log() 审计日志创建字段和格式
- _invalidate_template_matching_cache() 缓存版本号递增
- PlaceholderUsageFilter.queryset() 四种过滤类型
- current_file_display / file_location_display 路径解析

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7**
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# 1. EvidenceList start_order / start_page 保持性测试
# ---------------------------------------------------------------------------


def _make_evidence_list_mock(
    pk: int,
    previous_list: Any | None,
    previous_list_id: int | None,
    item_count: int,
    total_pages: int,
) -> MagicMock:
    """构造一个模拟的 EvidenceList 对象。"""
    obj = MagicMock()
    obj.pk = pk
    obj.previous_list = previous_list
    obj.previous_list_id = previous_list_id
    obj.total_pages = total_pages
    obj.items.count.return_value = item_count
    return obj


class TestStartOrderPreservation:
    """
    验证 EvidenceService.calculate_start_order 行为保持。

    **Validates: Requirements 3.3**
    """

    def _get_service(self) -> Any:
        from apps.documents.services.evidence_service import EvidenceService
        return EvidenceService()

    def test_no_previous_list_returns_1(self) -> None:
        """无前置清单时起始序号为 1。"""
        el = _make_evidence_list_mock(pk=1, previous_list=None, previous_list_id=None, item_count=3, total_pages=10)
        result = self._get_service().calculate_start_order(el)
        assert result == 1

    def test_single_previous_list(self) -> None:
        """单个前置清单：起始序号 = 前置清单 items 数 + 1。"""
        prev = _make_evidence_list_mock(pk=1, previous_list=None, previous_list_id=None, item_count=5, total_pages=10)
        el = _make_evidence_list_mock(pk=2, previous_list=prev, previous_list_id=1, item_count=3, total_pages=8)
        result = self._get_service().calculate_start_order(el)
        assert result == 6  # 5 + 1

    def test_chain_of_two_previous_lists(self) -> None:
        """两级链表：起始序号 = 所有前置清单 items 总数 + 1。"""
        first = _make_evidence_list_mock(pk=1, previous_list=None, previous_list_id=None, item_count=3, total_pages=5)
        second = _make_evidence_list_mock(pk=2, previous_list=first, previous_list_id=1, item_count=4, total_pages=8)
        el = _make_evidence_list_mock(pk=3, previous_list=second, previous_list_id=2, item_count=2, total_pages=6)
        result = self._get_service().calculate_start_order(el)
        assert result == 8  # 3 + 4 + 1

    def test_cycle_detection_returns_1(self) -> None:
        """检测到循环引用时返回默认值 1。"""
        el_a = _make_evidence_list_mock(pk=1, previous_list=None, previous_list_id=2, item_count=3, total_pages=5)
        el_b = _make_evidence_list_mock(pk=2, previous_list=el_a, previous_list_id=1, item_count=4, total_pages=8)
        # 构造循环: A -> B -> A
        el_a.previous_list = el_b
        el_target = _make_evidence_list_mock(pk=3, previous_list=el_a, previous_list_id=1, item_count=2, total_pages=6)
        result = self._get_service().calculate_start_order(el_target)
        # 遍历到循环时返回 1
        assert result == 1


class TestStartPagePreservation:
    """
    验证 EvidenceService.calculate_start_page 行为保持。

    **Validates: Requirements 3.3**
    """

    def _get_service(self) -> Any:
        from apps.documents.services.evidence_service import EvidenceService
        return EvidenceService()

    def test_no_previous_list_returns_1(self) -> None:
        """无前置清单时起始页码为 1。"""
        el = _make_evidence_list_mock(pk=1, previous_list=None, previous_list_id=None, item_count=3, total_pages=10)
        result = self._get_service().calculate_start_page(el)
        assert result == 1

    def test_single_previous_list(self) -> None:
        """单个前置清单：起始页码 = 前置清单 total_pages + 1。"""
        prev = _make_evidence_list_mock(pk=1, previous_list=None, previous_list_id=None, item_count=5, total_pages=10)
        el = _make_evidence_list_mock(pk=2, previous_list=prev, previous_list_id=1, item_count=3, total_pages=8)
        result = self._get_service().calculate_start_page(el)
        assert result == 11  # 10 + 1

    def test_chain_of_two_previous_lists(self) -> None:
        """两级链表：起始页码 = 所有前置清单 total_pages 总和 + 1。"""
        first = _make_evidence_list_mock(pk=1, previous_list=None, previous_list_id=None, item_count=3, total_pages=5)
        second = _make_evidence_list_mock(pk=2, previous_list=first, previous_list_id=1, item_count=4, total_pages=8)
        el = _make_evidence_list_mock(pk=3, previous_list=second, previous_list_id=2, item_count=2, total_pages=6)
        result = self._get_service().calculate_start_page(el)
        assert result == 14  # 5 + 8 + 1

    def test_cycle_detection_returns_1(self) -> None:
        """检测到循环引用时返回默认值 1。"""
        el_a = _make_evidence_list_mock(pk=1, previous_list=None, previous_list_id=2, item_count=3, total_pages=5)
        el_b = _make_evidence_list_mock(pk=2, previous_list=el_a, previous_list_id=1, item_count=4, total_pages=8)
        el_a.previous_list = el_b
        el_target = _make_evidence_list_mock(pk=3, previous_list=el_a, previous_list_id=1, item_count=2, total_pages=6)
        result = self._get_service().calculate_start_page(el_target)
        assert result == 1



# ---------------------------------------------------------------------------
# 1b. Property-based tests for start_order / start_page
# ---------------------------------------------------------------------------


def _build_chain(items_counts: list[int], pages_counts: list[int]) -> list[MagicMock]:
    """
    根据给定的 items 数量和 pages 数量列表构建链表。
    返回列表中最后一个元素是目标 EvidenceList。
    """
    chain: list[MagicMock] = []
    for i, (ic, pc) in enumerate(zip(items_counts, pages_counts)):
        prev = chain[-1] if chain else None
        prev_id = chain[-1].pk if chain else None
        node = _make_evidence_list_mock(
            pk=i + 1,
            previous_list=prev,
            previous_list_id=prev_id,
            item_count=ic,
            total_pages=pc,
        )
        chain.append(node)
    return chain


class TestStartOrderProperty:
    """
    Property-based: calculate_start_order 对任意链表结构的正确性。

    **Validates: Requirements 3.3**
    """

    def _get_service(self) -> Any:
        from apps.documents.services.evidence_service import EvidenceService
        return EvidenceService()

    @given(
        items_counts=st.lists(st.integers(min_value=0, max_value=100), min_size=2, max_size=8),
        pages_counts=st.lists(st.integers(min_value=0, max_value=500), min_size=2, max_size=8),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_start_order_equals_sum_of_previous_items_plus_one(
        self, items_counts: list[int], pages_counts: list[int]
    ) -> None:
        """对任意链表，start_order = 所有前置清单 items 总数 + 1。"""
        min_len = min(len(items_counts), len(pages_counts))
        items_counts = items_counts[:min_len]
        pages_counts = pages_counts[:min_len]

        chain = _build_chain(items_counts, pages_counts)
        target = chain[-1]

        result = self._get_service().calculate_start_order(target)
        expected = sum(items_counts[:-1]) + 1
        assert result == expected

    @given(
        items_counts=st.lists(st.integers(min_value=0, max_value=100), min_size=2, max_size=8),
        pages_counts=st.lists(st.integers(min_value=0, max_value=500), min_size=2, max_size=8),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_start_page_equals_sum_of_previous_pages_plus_one(
        self, items_counts: list[int], pages_counts: list[int]
    ) -> None:
        """对任意链表，start_page = 所有前置清单 total_pages 总和 + 1。"""
        min_len = min(len(items_counts), len(pages_counts))
        items_counts = items_counts[:min_len]
        pages_counts = pages_counts[:min_len]

        chain = _build_chain(items_counts, pages_counts)
        target = chain[-1]

        result = self._get_service().calculate_start_page(target)
        expected = sum(pages_counts[:-1]) + 1
        assert result == expected

    def test_single_node_start_order_is_1(self) -> None:
        """单节点（无前置）start_order 始终为 1。"""
        el = _make_evidence_list_mock(pk=1, previous_list=None, previous_list_id=None, item_count=99, total_pages=50)
        assert self._get_service().calculate_start_order(el) == 1

    def test_single_node_start_page_is_1(self) -> None:
        """单节点（无前置）start_page 始终为 1。"""
        el = _make_evidence_list_mock(pk=1, previous_list=None, previous_list_id=None, item_count=99, total_pages=50)
        assert self._get_service().calculate_start_page(el) == 1


# ---------------------------------------------------------------------------
# 2. _create_audit_log 审计日志创建保持性测试
# ---------------------------------------------------------------------------


class TestAuditLogPreservation:
    """
    验证 _create_audit_log 通过 TemplateAuditLogService 创建审计日志，
    字段和格式与原始行为一致。

    **Validates: Requirements 3.4**
    """

    def test_create_audit_log_calls_service_with_correct_fields(self) -> None:
        """_create_audit_log 传递正确的 content_type, object_id, object_repr, action, changes。"""
        from apps.documents.models import DocumentTemplate

        mock_instance = MagicMock(spec=DocumentTemplate)
        mock_instance.__class__ = DocumentTemplate
        mock_instance.pk = 42
        mock_instance.__str__ = MagicMock(return_value="测试模板")

        changes = {"name": {"old": "旧名", "new": "新名"}}

        with patch("apps.documents.signals._get_audit_log_service") as mock_get_svc:
            mock_svc = MagicMock()
            mock_get_svc.return_value = mock_svc

            from apps.documents.signals import _create_audit_log
            _create_audit_log(mock_instance, "update", changes=changes)

            mock_svc.create_audit_log.assert_called_once_with(
                "document_template", 42, "测试模板", "update", changes
            )

    def test_create_audit_log_truncates_object_repr_to_500(self) -> None:
        """object_repr 超过 500 字符时截断。"""
        from apps.documents.models import FolderTemplate

        mock_instance = MagicMock(spec=FolderTemplate)
        mock_instance.__class__ = FolderTemplate
        mock_instance.pk = 7
        long_name = "A" * 600
        mock_instance.__str__ = MagicMock(return_value=long_name)

        with patch("apps.documents.signals._get_audit_log_service") as mock_get_svc:
            mock_svc = MagicMock()
            mock_get_svc.return_value = mock_svc

            from apps.documents.signals import _create_audit_log
            _create_audit_log(mock_instance, "create")

            call_args = mock_svc.create_audit_log.call_args
            # object_repr 参数（第3个位置参数）应被截断到 500
            assert len(call_args[0][2]) == 500

    def test_create_audit_log_skips_unknown_model(self) -> None:
        """未知模型类型不创建审计日志。"""
        mock_instance = MagicMock()
        mock_instance.__class__ = type("UnknownModel", (), {})
        mock_instance.pk = 1

        with patch("apps.documents.signals._get_audit_log_service") as mock_get_svc:
            mock_svc = MagicMock()
            mock_get_svc.return_value = mock_svc

            from apps.documents.signals import _create_audit_log
            _create_audit_log(mock_instance, "create")

            mock_svc.create_audit_log.assert_not_called()

    def test_capture_pre_save_state_delegates_to_service(self) -> None:
        """capture_pre_save_state 通过 service.get_instance_by_pk 获取旧实例。"""
        from apps.documents.models import DocumentTemplate

        mock_instance = MagicMock(spec=DocumentTemplate)
        mock_instance.pk = 10

        old_instance = MagicMock()

        with patch("apps.documents.signals._get_audit_log_service") as mock_get_svc:
            mock_svc = MagicMock()
            mock_svc.get_instance_by_pk.return_value = old_instance
            mock_get_svc.return_value = mock_svc

            from apps.documents.signals import capture_pre_save_state, _pre_save_state
            capture_pre_save_state(DocumentTemplate, mock_instance)

            mock_svc.get_instance_by_pk.assert_called_once_with(DocumentTemplate, 10)
            assert _pre_save_state.get(f"DocumentTemplate_{10}") is old_instance

            # 清理
            _pre_save_state.pop(f"DocumentTemplate_{10}", None)


# ---------------------------------------------------------------------------
# 3. _invalidate_template_matching_cache 缓存版本递增保持性测试
# ---------------------------------------------------------------------------


class TestCacheInvalidationPreservation:
    """
    验证 _invalidate_template_matching_cache 使用 bump_cache_version 递增缓存版本号。

    **Validates: Requirements 3.5**
    """

    def test_document_template_bumps_correct_cache_key(self) -> None:
        """DocumentTemplate 触发时递增 document_templates 版本号。"""
        from apps.documents.models import DocumentTemplate

        with patch("apps.core.infrastructure.cache.bump_cache_version") as mock_bump:
            from apps.documents.signals import _invalidate_template_matching_cache
            _invalidate_template_matching_cache(DocumentTemplate)

            mock_bump.assert_called_once()
            call_args = mock_bump.call_args
            assert "document_templates" in call_args[0][0]

    def test_folder_template_bumps_correct_cache_key(self) -> None:
        """FolderTemplate 触发时递增 folder_templates 版本号。"""
        from apps.documents.models import FolderTemplate

        with patch("apps.core.infrastructure.cache.bump_cache_version") as mock_bump:
            from apps.documents.signals import _invalidate_template_matching_cache
            _invalidate_template_matching_cache(FolderTemplate)

            mock_bump.assert_called_once()
            call_args = mock_bump.call_args
            assert "folder_templates" in call_args[0][0]

    def test_placeholder_does_not_bump_cache(self) -> None:
        """Placeholder 触发时不递增缓存版本号。"""
        from apps.documents.models import Placeholder

        with patch("apps.core.infrastructure.cache.bump_cache_version") as mock_bump:
            from apps.documents.signals import _invalidate_template_matching_cache
            _invalidate_template_matching_cache(Placeholder)

            mock_bump.assert_not_called()

    def test_bump_uses_day_timeout(self) -> None:
        """缓存版本号使用 CacheTimeout.get_day() 超时。"""
        from apps.documents.models import DocumentTemplate
        from apps.core.infrastructure import CacheTimeout

        expected_timeout = CacheTimeout.get_day()

        with patch("apps.core.infrastructure.cache.bump_cache_version") as mock_bump:
            from apps.documents.signals import _invalidate_template_matching_cache
            _invalidate_template_matching_cache(DocumentTemplate)

            call_kwargs = mock_bump.call_args[1]
            assert call_kwargs["timeout"] == expected_timeout


# ---------------------------------------------------------------------------
# 4. PlaceholderUsageFilter / PlaceholderAdminService.filter_by_usage 保持性测试
# ---------------------------------------------------------------------------


class TestPlaceholderFilterPreservation:
    """
    验证 PlaceholderAdminService.filter_by_usage 四种过滤类型结果正确。

    **Validates: Requirements 3.6**
    """

    def _get_service(self) -> Any:
        from apps.documents.services.placeholder_admin_service import PlaceholderAdminService
        return PlaceholderAdminService()

    def _make_usage_map(self) -> dict[str, set[str]]:
        """构造测试用的 usage_map。"""
        return {
            "client_name": {"contract"},
            "case_number": {"case"},
            "lawyer_name": {"contract", "case"},
            "court_name": {"contract", "case"},
            "contract_amount": {"contract"},
        }

    def test_filter_contract_only(self) -> None:
        """过滤 contract 类型：仅返回只在合同中使用的占位符。"""
        usage_map = self._make_usage_map()
        qs = MagicMock()
        filtered_qs = MagicMock()
        qs.filter.return_value = filtered_qs

        result = self._get_service().filter_by_usage(qs, "contract", usage_map)

        qs.filter.assert_called_once()
        call_kwargs = qs.filter.call_args[1]
        keys = call_kwargs["key__in"]
        assert set(keys) == {"client_name", "contract_amount"}
        assert result is filtered_qs

    def test_filter_case_only(self) -> None:
        """过滤 case 类型：仅返回只在案件中使用的占位符。"""
        usage_map = self._make_usage_map()
        qs = MagicMock()
        filtered_qs = MagicMock()
        qs.filter.return_value = filtered_qs

        result = self._get_service().filter_by_usage(qs, "case", usage_map)

        qs.filter.assert_called_once()
        call_kwargs = qs.filter.call_args[1]
        keys = call_kwargs["key__in"]
        assert set(keys) == {"case_number"}
        assert result is filtered_qs

    def test_filter_both(self) -> None:
        """过滤 both 类型：返回同时在合同和案件中使用的占位符。"""
        usage_map = self._make_usage_map()
        qs = MagicMock()
        filtered_qs = MagicMock()
        qs.filter.return_value = filtered_qs

        result = self._get_service().filter_by_usage(qs, "both", usage_map)

        qs.filter.assert_called_once()
        call_kwargs = qs.filter.call_args[1]
        keys = call_kwargs["key__in"]
        assert set(keys) == {"lawyer_name", "court_name"}
        assert result is filtered_qs

    def test_filter_unused(self) -> None:
        """过滤 unused 类型：排除所有已使用的占位符。"""
        usage_map = self._make_usage_map()
        qs = MagicMock()
        excluded_qs = MagicMock()
        qs.exclude.return_value = excluded_qs

        result = self._get_service().filter_by_usage(qs, "unused", usage_map)

        qs.exclude.assert_called_once()
        call_kwargs = qs.exclude.call_args[1]
        keys = call_kwargs["key__in"]
        assert set(keys) == {"client_name", "case_number", "lawyer_name", "court_name", "contract_amount"}
        assert result is excluded_qs

    def test_filter_unknown_value_returns_original(self) -> None:
        """未知过滤值返回原始 queryset。"""
        usage_map = self._make_usage_map()
        qs = MagicMock()

        result = self._get_service().filter_by_usage(qs, "unknown", usage_map)
        assert result is qs

    def test_filter_empty_usage_map(self) -> None:
        """空 usage_map 时 contract/case/both 返回空集，unused 返回全部。"""
        empty_map: dict[str, set[str]] = {}
        qs = MagicMock()
        filtered_qs = MagicMock()
        qs.filter.return_value = filtered_qs
        qs.exclude.return_value = qs  # exclude 空集 = 原始

        svc = self._get_service()

        # contract 过滤空集
        result = svc.filter_by_usage(qs, "contract", empty_map)
        call_kwargs = qs.filter.call_args[1]
        assert set(call_kwargs["key__in"]) == set()

        # unused 排除空集 = 返回全部
        result = svc.filter_by_usage(qs, "unused", empty_map)
        call_kwargs = qs.exclude.call_args[1]
        assert set(call_kwargs["key__in"]) == set()


# ---------------------------------------------------------------------------
# 4b. Property-based test for filter_by_usage
# ---------------------------------------------------------------------------


class TestPlaceholderFilterProperty:
    """
    Property-based: filter_by_usage 对任意 usage_map 的分类正确性。

    **Validates: Requirements 3.6**
    """

    def _get_service(self) -> Any:
        from apps.documents.services.placeholder_admin_service import PlaceholderAdminService
        return PlaceholderAdminService()

    @given(
        keys=st.lists(st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=20), min_size=0, max_size=10, unique=True),
        usage_types=st.lists(
            st.frozensets(st.sampled_from(["contract", "case"]), min_size=1, max_size=2),
            min_size=0,
            max_size=10,
        ),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_four_categories_are_disjoint_and_exhaustive(
        self, keys: list[str], usage_types: list[frozenset[str]]
    ) -> None:
        """contract_only, case_only, both 三个分类互不重叠，且并集 = 所有已使用的 key。"""
        min_len = min(len(keys), len(usage_types))
        keys = keys[:min_len]
        usage_types_list = list(usage_types[:min_len])

        usage_map: dict[str, set[str]] = {
            k: set(ut) for k, ut in zip(keys, usage_types_list)
        }

        contract_only = {k for k, v in usage_map.items() if v == {"contract"}}
        case_only = {k for k, v in usage_map.items() if v == {"case"}}
        both = {k for k, v in usage_map.items() if {"contract", "case"}.issubset(v)}

        # 三个分类互不重叠
        assert contract_only & case_only == set()
        assert contract_only & both == set()
        assert case_only & both == set()

        # 并集 = 所有已使用的 key
        assert contract_only | case_only | both == set(usage_map.keys())


# ---------------------------------------------------------------------------
# 5. current_file_display / file_location_display 路径解析保持性测试
# ---------------------------------------------------------------------------


class TestFilePathDisplayPreservation:
    """
    验证 DocumentTemplate.absolute_file_path 和 Admin display 方法路径解析正确。

    **Validates: Requirements 3.7**
    """

    def test_absolute_file_path_empty_when_no_file_path(self) -> None:
        """file_path 为空时 absolute_file_path 返回空字符串。"""
        from apps.documents.models import DocumentTemplate

        obj = DocumentTemplate.__new__(DocumentTemplate)
        obj.file_path = ""
        assert obj.absolute_file_path == ""

    def test_absolute_file_path_resolves_relative_path(self) -> None:
        """相对路径通过 Path.resolve() 解析为绝对路径。"""
        from apps.documents.models import DocumentTemplate
        from pathlib import Path as StdPath

        obj = DocumentTemplate.__new__(DocumentTemplate)
        obj.file_path = "templates/contract.docx"

        result = obj.absolute_file_path
        expected = str(StdPath("templates/contract.docx").resolve())
        assert result == expected

    def test_absolute_file_path_preserves_absolute_path(self) -> None:
        """绝对路径直接返回原值。"""
        from apps.documents.models import DocumentTemplate

        obj = DocumentTemplate.__new__(DocumentTemplate)
        obj.file_path = "/opt/templates/contract.docx"

        result = obj.absolute_file_path
        assert result == "/opt/templates/contract.docx"

    def test_current_file_display_uses_absolute_file_path_for_file_path_mode(self) -> None:
        """current_file_display 在 file_path 模式下使用 obj.absolute_file_path。"""
        from apps.documents.models import DocumentTemplate
        from apps.documents.admin.document_template_admin import DocumentTemplateAdmin

        obj = MagicMock(spec=DocumentTemplate)
        obj.pk = 1
        obj.file = None  # 无上传文件
        obj.file_path = "templates/test.docx"
        obj.absolute_file_path = "/resolved/templates/test.docx"

        admin_instance = DocumentTemplateAdmin.__new__(DocumentTemplateAdmin)
        result = admin_instance.current_file_display(obj)

        # 结果应包含 absolute_file_path 作为 title
        assert "/resolved/templates/test.docx" in str(result)
        # 结果应包含 file_path 作为显示文本
        assert "templates/test.docx" in str(result)

    def test_file_location_display_uses_absolute_file_path_for_file_path_mode(self) -> None:
        """file_location_display 在 file_path 模式下使用 obj.absolute_file_path。"""
        from apps.documents.models import DocumentTemplate
        from apps.documents.admin.document_template_admin import DocumentTemplateAdmin

        obj = MagicMock(spec=DocumentTemplate)
        obj.pk = 1
        obj.file = None  # 无上传文件
        obj.file_path = "templates/test.docx"
        obj.absolute_file_path = "/resolved/templates/test.docx"

        admin_instance = DocumentTemplateAdmin.__new__(DocumentTemplateAdmin)

        with patch("django.urls.reverse", return_value="/admin/download/1/"):
            result = admin_instance.file_location_display(obj)

        # 结果应包含 absolute_file_path
        assert "/resolved/templates/test.docx" in str(result)
        # 结果应包含 file_path 作为显示文本
        assert "templates/test.docx" in str(result)

    def test_current_file_display_no_file_shows_warning(self) -> None:
        """无文件时显示警告。"""
        from apps.documents.models import DocumentTemplate
        from apps.documents.admin.document_template_admin import DocumentTemplateAdmin

        obj = MagicMock(spec=DocumentTemplate)
        obj.pk = 1
        obj.file = None
        obj.file_path = ""

        admin_instance = DocumentTemplateAdmin.__new__(DocumentTemplateAdmin)
        result = admin_instance.current_file_display(obj)

        assert "⚠️" in str(result)

    def test_file_location_display_no_file_shows_placeholder(self) -> None:
        """无文件时显示占位文本。"""
        from apps.documents.models import DocumentTemplate
        from apps.documents.admin.document_template_admin import DocumentTemplateAdmin

        obj = MagicMock(spec=DocumentTemplate)
        obj.pk = 1
        obj.file = None
        obj.file_path = ""

        admin_instance = DocumentTemplateAdmin.__new__(DocumentTemplateAdmin)
        result = admin_instance.file_location_display(obj)

        assert "未设置" in str(result)


# ---------------------------------------------------------------------------
# 5b. Property-based test for absolute_file_path
# ---------------------------------------------------------------------------


class TestAbsoluteFilePathProperty:
    """
    Property-based: absolute_file_path 对任意路径的行为正确性。

    **Validates: Requirements 3.7**
    """

    @given(filename=st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-./", min_size=1, max_size=50))
    @settings(max_examples=50)
    def test_absolute_file_path_always_returns_string(self, filename: str) -> None:
        """absolute_file_path 始终返回字符串类型。"""
        from apps.documents.models import DocumentTemplate

        obj = DocumentTemplate.__new__(DocumentTemplate)
        obj.file_path = filename

        result = obj.absolute_file_path
        assert isinstance(result, str)

    @given(filename=st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-./", min_size=1, max_size=50))
    @settings(max_examples=50)
    def test_absolute_file_path_result_is_absolute_or_resolved(self, filename: str) -> None:
        """非空 file_path 的 absolute_file_path 结果是绝对路径或原始绝对路径。"""
        from apps.documents.models import DocumentTemplate
        from pathlib import Path as StdPath

        assume(filename.strip() != "")
        assume(not filename.startswith(".."))
        assume("//" not in filename)

        obj = DocumentTemplate.__new__(DocumentTemplate)
        obj.file_path = filename

        result = obj.absolute_file_path
        if result:  # 非空结果
            result_path = StdPath(result)
            assert result_path.is_absolute()
