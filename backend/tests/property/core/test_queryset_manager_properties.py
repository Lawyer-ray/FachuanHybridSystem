"""
QuerySet_Manager Property-Based Tests

# Feature: backend-quality-to-10, Property 1: QuerySet 一致性
# Feature: backend-quality-to-10, Property 2: QuerySet 额外预加载包含性

Validates: Requirements 1.4, 1.5

这些测试不访问数据库——仅验证查询集配置（select_related、prefetch_related），
通过 mock ORM manager 避免实际数据库连接。
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from apps.core.querysets import CaseQuerySetManager, ContractQuerySetManager

logger = logging.getLogger(__name__)

# 策略：生成合法的 Django ORM 字段路径字符串（如 "foo__bar"）
_field_name_strategy = st.from_regex(r"[a-z][a-z0-9_]{0,19}", fullmatch=True)
_extra_fields_strategy = st.lists(_field_name_strategy, min_size=0, max_size=5)


def _make_mock_queryset(select_related_config: Any = False) -> MagicMock:
    """
    构造一个模拟 QuerySet，支持链式调用 select_related / prefetch_related。

    每次调用 select_related(*fields) 或 prefetch_related(*fields) 都返回一个新的
    mock，其 query.select_related 和 _prefetch_related_lookups 反映累积的配置。
    """

    def _build(sr_config: Any, prefetch_lookups: tuple[str, ...]) -> MagicMock:
        qs = MagicMock()
        qs.query = MagicMock()
        qs.query.select_related = sr_config
        qs._prefetch_related_lookups = prefetch_lookups

        def _select_related(*fields: str) -> MagicMock:
            new_config: Any = {f: {} for f in fields} if fields else True
            return _build(new_config, prefetch_lookups)

        def _prefetch_related(*fields: str) -> MagicMock:
            return _build(sr_config, prefetch_lookups + fields)

        qs.select_related.side_effect = _select_related
        qs.prefetch_related.side_effect = _prefetch_related
        return qs

    return _build(select_related_config, ())


class TestQuerySetManagerConsistencyProperty:
    """
    Property 1: QuerySet 一致性

    # Feature: backend-quality-to-10, Property 1: QuerySet 一致性
    Validates: Requirements 1.4
    """

    @given(st.integers(min_value=2, max_value=5))
    @settings(max_examples=100)
    def test_case_queryset_standard_prefetch_is_consistent(self, call_count: int) -> None:
        """
        Property 1: QuerySet 一致性 — CaseQuerySetManager

        多次调用 with_standard_prefetch() 返回的查询集应包含完全相同的
        select_related 和 prefetch_related 配置。

        # Feature: backend-quality-to-10, Property 1: QuerySet 一致性
        Validates: Requirements 1.4
        """
        mock_objects = _make_mock_queryset()

        with patch("apps.core.querysets.CaseQuerySetManager.with_standard_prefetch") as mock_method:
            # 让 with_standard_prefetch 每次都通过 mock_objects 构建真实链
            def _real_standard() -> MagicMock:
                return mock_objects.select_related(*CaseQuerySetManager.SELECT_RELATED).prefetch_related(  # type: ignore[no-any-return]
                    *CaseQuerySetManager.PREFETCH_RELATED
                )

            mock_method.side_effect = _real_standard

            first_qs = CaseQuerySetManager.with_standard_prefetch()
            first_select = first_qs.query.select_related
            first_prefetch = tuple(first_qs._prefetch_related_lookups)  # type: ignore[attr-defined]

            for _ in range(call_count - 1):
                qs = CaseQuerySetManager.with_standard_prefetch()
                assert (
                    qs.query.select_related == first_select
                ), "CaseQuerySetManager.with_standard_prefetch() 的 select_related 配置应保持一致"
                assert (
                    tuple(qs._prefetch_related_lookups) == first_prefetch  # type: ignore[attr-defined]
                ), "CaseQuerySetManager.with_standard_prefetch() 的 prefetch_related 配置应保持一致"

    @given(st.integers(min_value=2, max_value=5))
    @settings(max_examples=100)
    def test_contract_queryset_standard_prefetch_is_consistent(self, call_count: int) -> None:
        """
        Property 1: QuerySet 一致性 — ContractQuerySetManager

        多次调用 with_standard_prefetch() 返回的查询集应包含完全相同的
        select_related 和 prefetch_related 配置。

        # Feature: backend-quality-to-10, Property 1: QuerySet 一致性
        Validates: Requirements 1.4
        """
        mock_objects = _make_mock_queryset()

        with patch("apps.core.querysets.ContractQuerySetManager.with_standard_prefetch") as mock_method:

            def _real_standard() -> MagicMock:
                return mock_objects.prefetch_related(*ContractQuerySetManager.PREFETCH_RELATED)  # type: ignore[no-any-return]

            mock_method.side_effect = _real_standard

            first_qs = ContractQuerySetManager.with_standard_prefetch()
            first_select = first_qs.query.select_related
            first_prefetch = tuple(first_qs._prefetch_related_lookups)  # type: ignore[attr-defined]

            for _ in range(call_count - 1):
                qs = ContractQuerySetManager.with_standard_prefetch()
                assert (
                    qs.query.select_related == first_select
                ), "ContractQuerySetManager.with_standard_prefetch() 的 select_related 配置应保持一致"
                assert (
                    tuple(qs._prefetch_related_lookups) == first_prefetch  # type: ignore[attr-defined]
                ), "ContractQuerySetManager.with_standard_prefetch() 的 prefetch_related 配置应保持一致"


class TestQuerySetManagerExtraPrefetchInclusionProperty:
    """
    Property 2: QuerySet 额外预加载包含性

    # Feature: backend-quality-to-10, Property 2: QuerySet 额外预加载包含性
    Validates: Requirements 1.5
    """

    @given(extras=_extra_fields_strategy)
    @settings(max_examples=100)
    def test_case_queryset_extra_prefetch_includes_standard(self, extras: list[str]) -> None:
        """
        Property 2: QuerySet 额外预加载包含性 — CaseQuerySetManager

        with_extra_prefetch(*extras) 返回的查询集应包含标准预加载配置中的所有字段，
        加上 extras 中的所有字段。

        # Feature: backend-quality-to-10, Property 2: QuerySet 额外预加载包含性
        Validates: Requirements 1.5
        """
        mock_objects = _make_mock_queryset()

        def _standard() -> MagicMock:
            return mock_objects.select_related(*CaseQuerySetManager.SELECT_RELATED).prefetch_related(  # type: ignore[no-any-return]
                *CaseQuerySetManager.PREFETCH_RELATED
            )

        def _extra(*extra_fields: str) -> MagicMock:
            return _standard().prefetch_related(*extra_fields)  # type: ignore[no-any-return]

        with (
            patch("apps.core.querysets.CaseQuerySetManager.with_standard_prefetch", side_effect=_standard),
            patch("apps.core.querysets.CaseQuerySetManager.with_extra_prefetch", side_effect=_extra),
        ):
            standard_qs = CaseQuerySetManager.with_standard_prefetch()
            standard_prefetch = set(standard_qs._prefetch_related_lookups)  # type: ignore[attr-defined]
            standard_select: Any = standard_qs.query.select_related

            extra_qs = CaseQuerySetManager.with_extra_prefetch(*extras)
            extra_prefetch = set(extra_qs._prefetch_related_lookups)  # type: ignore[attr-defined]
            extra_select: Any = extra_qs.query.select_related

            assert extra_select == standard_select, "with_extra_prefetch() 不应改变 select_related 配置"
            assert standard_prefetch.issubset(
                extra_prefetch
            ), "with_extra_prefetch() 应包含所有标准 prefetch_related 字段"
            for field in extras:
                assert field in extra_prefetch, f"with_extra_prefetch() 应包含额外字段 {field!r}"

    @given(extras=_extra_fields_strategy)
    @settings(max_examples=100)
    def test_contract_queryset_extra_prefetch_includes_standard(self, extras: list[str]) -> None:
        """
        Property 2: QuerySet 额外预加载包含性 — ContractQuerySetManager

        with_extra_prefetch(*extras) 返回的查询集应包含标准预加载配置中的所有字段，
        加上 extras 中的所有字段。

        # Feature: backend-quality-to-10, Property 2: QuerySet 额外预加载包含性
        Validates: Requirements 1.5
        """
        mock_objects = _make_mock_queryset()

        def _standard() -> MagicMock:
            return mock_objects.prefetch_related(*ContractQuerySetManager.PREFETCH_RELATED)  # type: ignore[no-any-return]

        def _extra(*extra_fields: str) -> MagicMock:
            return _standard().prefetch_related(*extra_fields)  # type: ignore[no-any-return]

        with (
            patch("apps.core.querysets.ContractQuerySetManager.with_standard_prefetch", side_effect=_standard),
            patch("apps.core.querysets.ContractQuerySetManager.with_extra_prefetch", side_effect=_extra),
        ):
            standard_qs = ContractQuerySetManager.with_standard_prefetch()
            standard_prefetch = set(standard_qs._prefetch_related_lookups)  # type: ignore[attr-defined]
            standard_select: Any = standard_qs.query.select_related

            extra_qs = ContractQuerySetManager.with_extra_prefetch(*extras)
            extra_prefetch = set(extra_qs._prefetch_related_lookups)  # type: ignore[attr-defined]
            extra_select: Any = extra_qs.query.select_related

            assert extra_select == standard_select, "with_extra_prefetch() 不应改变 select_related 配置"
            assert standard_prefetch.issubset(
                extra_prefetch
            ), "with_extra_prefetch() 应包含所有标准 prefetch_related 字段"
            for field in extras:
                assert field in extra_prefetch, f"with_extra_prefetch() 应包含额外字段 {field!r}"
