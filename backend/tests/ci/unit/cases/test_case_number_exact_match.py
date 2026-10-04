"""案号精确匹配链路的等值匹配测试。

修复背景：build_case_id_query_by_case_number 原先用 icontains 子串匹配，
`(2025)粤0605民初123号` 会误命中 `民初1234号`，导致短信文书/CaseLog/群通知
落到错误案件。现收紧为归一化变体的精确等值匹配。
宽松搜索入口 build_case_search_queryset（icontains）不在本文件测试范围。
"""

from __future__ import annotations

import pytest

from apps.cases.models import Case, CaseNumber
from apps.cases.services.case.repo.case_search_query_builder import CaseSearchQueryBuilder


@pytest.mark.django_db
class TestCaseNumberExactMatch:
    """build_case_id_query_by_case_number 必须精确等值匹配。"""

    @staticmethod
    def _create_case_with_number(name: str, number: str) -> Case:
        case = Case.objects.create(name=name)
        CaseNumber.objects.create(case=case, number=number)
        return case

    def test_prefix_number_not_matched(self) -> None:
        """`民初123号` 不得命中库里的 `民初1234号`（前缀子串陷阱）。"""
        target = self._create_case_with_number("案件-1234", "（2025）粤0605民初1234号")

        ids = CaseSearchQueryBuilder().build_case_id_query_by_case_number("（2025）粤0605民初123号")

        assert ids == []
        assert target.id not in ids

    def test_exact_number_matched(self) -> None:
        """完全一致的案号必须命中。"""
        case = self._create_case_with_number("案件-123", "（2025）粤0605民初123号")

        ids = CaseSearchQueryBuilder().build_case_id_query_by_case_number("（2025）粤0605民初123号")

        assert ids == [case.id]

    def test_half_width_input_matches_full_width_storage(self) -> None:
        """半角括号输入能命中全角括号存储的案号。"""
        case = self._create_case_with_number("案件-半角输入", "（2025）粤0605民初123号")

        ids = CaseSearchQueryBuilder().build_case_id_query_by_case_number("(2025)粤0605民初123号")

        assert ids == [case.id]

    def test_half_width_storage_matched(self) -> None:
        """全角括号输入能命中半角括号存储的案号。"""
        case = self._create_case_with_number("案件-半角存储", "(2025)粤0605民初123号")

        ids = CaseSearchQueryBuilder().build_case_id_query_by_case_number("（2025）粤0605民初123号")

        assert ids == [case.id]

    def test_input_without_hao_matches_storage_with_hao(self) -> None:
        """不带「号」的输入能命中带「号」存储的案号。"""
        case = self._create_case_with_number("案件-无号输入", "（2025）粤0605民初123号")

        ids = CaseSearchQueryBuilder().build_case_id_query_by_case_number("（2025）粤0605民初123")

        assert ids == [case.id]

    def test_mixed_numbers_only_own_case_matched(self) -> None:
        """库中同时存在 123 与 1234 时，各自输入只命中各自案件。"""
        case_123 = self._create_case_with_number("案件-123", "（2025）粤0605民初123号")
        case_1234 = self._create_case_with_number("案件-1234", "（2025）粤0605民初1234号")

        ids_123 = CaseSearchQueryBuilder().build_case_id_query_by_case_number("（2025）粤0605民初123号")
        ids_1234 = CaseSearchQueryBuilder().build_case_id_query_by_case_number("（2025）粤0605民初1234号")

        assert ids_123 == [case_123.id]
        assert ids_1234 == [case_1234.id]

    def test_empty_input_returns_empty(self) -> None:
        assert CaseSearchQueryBuilder().build_case_id_query_by_case_number("") == []
        assert CaseSearchQueryBuilder().build_case_id_query_by_case_number("   ") == []


class TestBuildExactMatchVariants:
    """变体生成逻辑（纯函数，无数据库）。"""

    def test_variants_cover_full_and_half_width(self) -> None:
        variants = CaseSearchQueryBuilder().build_exact_match_variants("(2025)粤0605民初123号")

        assert "（2025）粤0605民初123号" in variants
        assert "（2025）粤0605民初123" in variants
        assert "(2025)粤0605民初123号" in variants
        assert "(2025)粤0605民初123" in variants

    def test_spaces_removed(self) -> None:
        variants = CaseSearchQueryBuilder().build_exact_match_variants("（2025）粤0605民初 123号")

        assert "（2025）粤0605民初123号" in variants

    def test_empty_returns_empty(self) -> None:
        assert CaseSearchQueryBuilder().build_exact_match_variants("") == []
