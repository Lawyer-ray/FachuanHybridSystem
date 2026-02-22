"""
Property 5/6: 适配器返回 None vs 核心 Service 抛 NotFoundError

**Validates: Requirements 4.1, 4.2**
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.cases.services import CaseService, CaseServiceAdapter
from apps.core.exceptions import NotFoundError

# 使用不可能存在的大 ID 范围
_NONEXISTENT_ID_STRATEGY = st.integers(min_value=10_000_000, max_value=99_999_999)


@pytest.mark.django_db
class TestAdapterReturnsNoneOnNotFound:
    """Property 5: 适配器查询未找到返回 None"""

    @given(case_id=_NONEXISTENT_ID_STRATEGY)
    @settings(max_examples=10)
    def test_adapter_get_case_returns_none_for_nonexistent_id(self, case_id: int) -> None:
        """
        Property 5: 适配器查询未找到返回 None

        对于任意不存在的案件 ID，CaseServiceAdapter.get_case 应返回 None 而非抛出异常。

        **Validates: Requirements 4.1**
        """
        adapter = CaseServiceAdapter()
        result = adapter.get_case(case_id)
        assert result is None

    @given(case_id=_NONEXISTENT_ID_STRATEGY)
    @settings(max_examples=10)
    def test_adapter_get_case_by_id_internal_returns_none_for_nonexistent_id(self, case_id: int) -> None:
        """
        Property 5: 适配器内部查询未找到返回 None

        **Validates: Requirements 4.1**
        """
        adapter = CaseServiceAdapter()
        result = adapter.get_case_by_id_internal(case_id)
        assert result is None

    @given(case_id=_NONEXISTENT_ID_STRATEGY)
    @settings(max_examples=10)
    def test_adapter_get_case_current_stage_returns_none_for_nonexistent_id(self, case_id: int) -> None:
        """
        Property 5: 适配器阶段查询未找到返回 None

        **Validates: Requirements 4.1**
        """
        adapter = CaseServiceAdapter()
        result = adapter.get_case_current_stage(case_id)
        assert result is None


@pytest.mark.django_db
class TestCoreServiceRaisesNotFoundError:
    """Property 6: 核心 Service 查询未找到抛 NotFoundError"""

    @given(case_id=_NONEXISTENT_ID_STRATEGY)
    @settings(max_examples=10)
    def test_core_service_get_case_raises_not_found_for_nonexistent_id(self, case_id: int) -> None:
        """
        Property 6: 核心 Service 查询未找到抛 NotFoundError

        对于任意不存在的案件 ID，CaseService.get_case 应抛出 NotFoundError。

        **Validates: Requirements 4.2**
        """
        from unittest.mock import Mock

        service = CaseService()
        mock_user = Mock()
        mock_user.is_authenticated = True
        mock_user.is_admin = True

        with pytest.raises(NotFoundError):
            service.get_case(case_id=case_id, user=mock_user, org_access=None, perm_open_access=True)
