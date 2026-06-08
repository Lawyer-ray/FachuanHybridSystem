"""apps/core/models/querysets.py 单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.models.querysets import CaseQuerySetManager, ContractQuerySetManager


class TestCaseQuerySetManager:
    """测试 CaseQuerySetManager。"""

    def test_select_related_tuple(self) -> None:
        """SELECT_RELATED 包含 contract。"""
        assert "contract" in CaseQuerySetManager.SELECT_RELATED

    def test_prefetch_related_tuple(self) -> None:
        """PREFETCH_RELATED 包含 parties__client 等关键字段。"""
        assert "parties__client" in CaseQuerySetManager.PREFETCH_RELATED
        assert "assignments__lawyer" in CaseQuerySetManager.PREFETCH_RELATED
        assert "case_numbers" in CaseQuerySetManager.PREFETCH_RELATED

    @patch("django.apps.apps.get_model")
    def test_with_standard_prefetch_calls_select_related(self, mock_get_model: MagicMock) -> None:
        """with_standard_prefetch 应调用 select_related 和 prefetch_related。"""
        mock_model = MagicMock()
        mock_qs = MagicMock()
        mock_model.objects.select_related.return_value.prefetch_related.return_value = mock_qs
        mock_get_model.return_value = mock_model

        result = CaseQuerySetManager.with_standard_prefetch()

        mock_get_model.assert_called_once_with("cases", "Case")
        mock_model.objects.select_related.assert_called_once_with(*CaseQuerySetManager.SELECT_RELATED)
        assert result is mock_qs

    @patch("django.apps.apps.get_model")
    def test_with_extra_prefetch_appends(self, mock_get_model: MagicMock) -> None:
        """with_extra_prefetch 应在标准预加载基础上追加额外字段。"""
        mock_model = MagicMock()
        mock_base_qs = MagicMock()
        mock_extra_qs = MagicMock()
        mock_model.objects.select_related.return_value.prefetch_related.return_value = mock_base_qs
        mock_base_qs.prefetch_related.return_value = mock_extra_qs
        mock_get_model.return_value = mock_model

        result = CaseQuerySetManager.with_extra_prefetch("extra_field", "another_field")

        mock_base_qs.prefetch_related.assert_called_once_with("extra_field", "another_field")
        assert result is mock_extra_qs


class TestContractQuerySetManager:
    """测试 ContractQuerySetManager。"""

    def test_prefetch_related_tuple(self) -> None:
        """PREFETCH_RELATED 包含 cases 和 contract_parties__client 等。"""
        assert "cases" in ContractQuerySetManager.PREFETCH_RELATED
        assert "contract_parties__client" in ContractQuerySetManager.PREFETCH_RELATED
        assert "payments" in ContractQuerySetManager.PREFETCH_RELATED

    @patch("django.apps.apps.get_model")
    def test_with_standard_prefetch_calls_prefetch_related(self, mock_get_model: MagicMock) -> None:
        """with_standard_prefetch 应调用 prefetch_related（无 select_related）。"""
        mock_model = MagicMock()
        mock_qs = MagicMock()
        mock_model.objects.prefetch_related.return_value = mock_qs
        mock_get_model.return_value = mock_model

        result = ContractQuerySetManager.with_standard_prefetch()

        mock_get_model.assert_called_once_with("contracts", "Contract")
        mock_model.objects.prefetch_related.assert_called_once_with(
            *ContractQuerySetManager.PREFETCH_RELATED
        )
        assert result is mock_qs

    @patch("django.apps.apps.get_model")
    def test_with_extra_prefetch_appends(self, mock_get_model: MagicMock) -> None:
        """with_extra_prefetch 应追加额外预加载字段。"""
        mock_model = MagicMock()
        mock_base_qs = MagicMock()
        mock_extra_qs = MagicMock()
        mock_model.objects.prefetch_related.return_value = mock_base_qs
        mock_base_qs.prefetch_related.return_value = mock_extra_qs
        mock_get_model.return_value = mock_model

        result = ContractQuerySetManager.with_extra_prefetch("supplementary_agreements")

        mock_base_qs.prefetch_related.assert_called_once_with("supplementary_agreements")
        assert result is mock_extra_qs
