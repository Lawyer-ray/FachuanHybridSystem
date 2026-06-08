"""apps/core/dependencies/business_import.py 单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestBuildCaseAndContractImportServicesForAdmin:
    """测试 build_case_and_contract_import_services_for_admin。"""

    def test_returns_tuple_of_two_services(self) -> None:
        """返回 (CaseImportService, ContractImportService) 元组。"""
        from apps.core.dependencies.business_import import (
            build_case_and_contract_import_services_for_admin,
        )

        mock_case_cls = MagicMock()
        mock_case_instance = MagicMock()
        mock_case_cls.return_value = mock_case_instance

        mock_contract_cls = MagicMock()
        mock_contract_instance = MagicMock()
        mock_contract_cls.return_value = mock_contract_instance

        mock_client_cls = MagicMock()
        mock_lawyer_cls = MagicMock()

        with (
            patch("apps.cases.services.case_import_service.CaseImportService", mock_case_cls),
            patch("apps.contracts.services.contract_import_service.ContractImportService", mock_contract_cls),
            patch("apps.client.services.client_resolve_service.ClientResolveService", mock_client_cls),
            patch("apps.organization.services.lawyer_resolve_service.LawyerResolveService", mock_lawyer_cls),
        ):
            result = build_case_and_contract_import_services_for_admin()

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert result[0] is mock_case_instance
        assert result[1] is mock_contract_instance

    def test_case_service_binds_contract_import(self) -> None:
        """CaseImportService 应调用 bind_contract_import 绑定 ContractImportService。"""
        from apps.core.dependencies.business_import import (
            build_case_and_contract_import_services_for_admin,
        )

        mock_case_cls = MagicMock()
        mock_case_instance = MagicMock()
        mock_case_cls.return_value = mock_case_instance

        mock_contract_cls = MagicMock()
        mock_contract_instance = MagicMock()
        mock_contract_cls.return_value = mock_contract_instance

        mock_client_cls = MagicMock()
        mock_lawyer_cls = MagicMock()

        with (
            patch("apps.cases.services.case_import_service.CaseImportService", mock_case_cls),
            patch("apps.contracts.services.contract_import_service.ContractImportService", mock_contract_cls),
            patch("apps.client.services.client_resolve_service.ClientResolveService", mock_client_cls),
            patch("apps.organization.services.lawyer_resolve_service.LawyerResolveService", mock_lawyer_cls),
        ):
            build_case_and_contract_import_services_for_admin()

        mock_case_instance.bind_contract_import.assert_called_once_with(mock_contract_instance)

    def test_contract_service_receives_case_import_fn(self) -> None:
        """ContractImportService 初始化时应接收 case_svc.import_one 作为 case_import_fn。"""
        from apps.core.dependencies.business_import import (
            build_case_and_contract_import_services_for_admin,
        )

        mock_case_cls = MagicMock()
        mock_case_instance = MagicMock()
        mock_case_cls.return_value = mock_case_instance

        mock_contract_cls = MagicMock()
        mock_contract_instance = MagicMock()
        mock_contract_cls.return_value = mock_contract_instance

        mock_client_cls = MagicMock()
        mock_lawyer_cls = MagicMock()

        with (
            patch("apps.cases.services.case_import_service.CaseImportService", mock_case_cls),
            patch("apps.contracts.services.contract_import_service.ContractImportService", mock_contract_cls),
            patch("apps.client.services.client_resolve_service.ClientResolveService", mock_client_cls),
            patch("apps.organization.services.lawyer_resolve_service.LawyerResolveService", mock_lawyer_cls),
        ):
            build_case_and_contract_import_services_for_admin()

        # ContractImportService 应收到 case_import_fn 参数
        call_kwargs = mock_contract_cls.call_args
        assert "case_import_fn" in call_kwargs.kwargs or "case_import_fn" in (call_kwargs[1] if len(call_kwargs) > 1 else {})
