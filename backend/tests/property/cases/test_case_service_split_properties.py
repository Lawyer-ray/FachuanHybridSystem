"""
Service 拆分后导入兼容性属性测试

# Feature: backend-perfect-score, Property 3: Service 拆分后导入兼容性
Validates: Requirements 3.4
"""

from __future__ import annotations

import inspect

from hypothesis import given, settings
from hypothesis import strategies as st


class TestServiceSplitImportCompatibilityProperty:
    """
    Property 3: Service 拆分后导入兼容性

    # Feature: backend-perfect-score, Property 3: Service 拆分后导入兼容性
    Validates: Requirements 3.4
    """

    @given(st.none())
    @settings(max_examples=100)
    def test_case_service_importable(self, _: None) -> None:
        """
        Property 3a: `from apps.cases.services import CaseService` 仍可用。

        # Feature: backend-perfect-score, Property 3: Service 拆分后导入兼容性
        Validates: Requirements 3.4
        """
        from apps.cases.services import CaseService  # noqa: F401

        assert CaseService is not None

    @given(st.none())
    @settings(max_examples=100)
    def test_split_services_importable(self, _: None) -> None:
        """
        Property 3b: CaseQueryService、CaseCommandService、CaseServiceAdapter 均可从
        `apps.cases.services` 导入。

        # Feature: backend-perfect-score, Property 3: Service 拆分后导入兼容性
        Validates: Requirements 3.4
        """
        from apps.cases.services import CaseCommandService, CaseQueryService, CaseServiceAdapter  # noqa: F401

        assert CaseQueryService is not None
        assert CaseCommandService is not None
        assert CaseServiceAdapter is not None

    @given(st.none())
    @settings(max_examples=100)
    def test_case_service_inherits_from_both(self, _: None) -> None:
        """
        Property 3c: CaseService 继承自 CaseQueryService 和 CaseCommandService。

        # Feature: backend-perfect-score, Property 3: Service 拆分后导入兼容性
        Validates: Requirements 3.4
        """
        from apps.cases.services import CaseCommandService, CaseQueryService, CaseService

        assert issubclass(CaseService, CaseQueryService), "CaseService 必须继承 CaseQueryService"
        assert issubclass(CaseService, CaseCommandService), "CaseService 必须继承 CaseCommandService"

    @given(st.none())
    @settings(max_examples=100)
    def test_case_service_has_query_methods(self, _: None) -> None:
        """
        Property 3d: CaseService 拥有 CaseQueryService 的所有公开方法。

        # Feature: backend-perfect-score, Property 3: Service 拆分后导入兼容性
        Validates: Requirements 3.4
        """
        from apps.cases.services import CaseQueryService, CaseService

        query_methods = {
            name
            for name, _ in inspect.getmembers(CaseQueryService, predicate=inspect.isfunction)
            if not name.startswith("_")
        }
        case_service_methods = {
            name
            for name, _ in inspect.getmembers(CaseService, predicate=inspect.isfunction)
            if not name.startswith("_")
        }

        missing = query_methods - case_service_methods
        assert not missing, f"CaseService 缺少 CaseQueryService 的方法: {missing}"

    @given(st.none())
    @settings(max_examples=100)
    def test_case_service_has_command_methods(self, _: None) -> None:
        """
        Property 3e: CaseService 拥有 CaseCommandService 的所有公开方法。

        # Feature: backend-perfect-score, Property 3: Service 拆分后导入兼容性
        Validates: Requirements 3.4
        """
        from apps.cases.services import CaseCommandService, CaseService

        command_methods = {
            name
            for name, _ in inspect.getmembers(CaseCommandService, predicate=inspect.isfunction)
            if not name.startswith("_")
        }
        case_service_methods = {
            name
            for name, _ in inspect.getmembers(CaseService, predicate=inspect.isfunction)
            if not name.startswith("_")
        }

        missing = command_methods - case_service_methods
        assert not missing, f"CaseService 缺少 CaseCommandService 的方法: {missing}"
