"""Unit tests for cases.services.template.folder_binding_service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.core.exceptions import NotFoundError, PermissionDenied


class TestCaseFolderBindingServiceInit:
    """Test constructor and property defaults."""

    def test_init_with_defaults(self) -> None:
        from apps.cases.services.template.folder_binding_service import CaseFolderBindingService

        svc = CaseFolderBindingService()
        assert svc._document_service is None
        assert svc._case_service is None

    def test_init_with_injected_services(self) -> None:
        from apps.cases.services.template.folder_binding_service import CaseFolderBindingService

        doc_svc = MagicMock()
        case_svc = MagicMock()
        svc = CaseFolderBindingService(document_service=doc_svc, case_service=case_svc)
        assert svc._document_service is doc_svc
        assert svc._case_service is case_svc

    def test_document_service_property_raises_if_not_injected(self) -> None:
        from apps.cases.services.template.folder_binding_service import CaseFolderBindingService

        svc = CaseFolderBindingService()
        with pytest.raises(RuntimeError, match="未注入"):
            _ = svc.document_service

    def test_case_service_property_raises_if_not_injected(self) -> None:
        from apps.cases.services.template.folder_binding_service import CaseFolderBindingService

        svc = CaseFolderBindingService()
        with pytest.raises(RuntimeError, match="未注入"):
            _ = svc.case_service

    def test_document_service_property_returns_injected(self) -> None:
        from apps.cases.services.template.folder_binding_service import CaseFolderBindingService

        doc_svc = MagicMock()
        svc = CaseFolderBindingService(document_service=doc_svc)
        assert svc.document_service is doc_svc

    def test_case_service_property_returns_injected(self) -> None:
        from apps.cases.services.template.folder_binding_service import CaseFolderBindingService

        case_svc = MagicMock()
        svc = CaseFolderBindingService(case_service=case_svc)
        assert svc.case_service is case_svc


class TestCaseFolderBindingServiceAccessPolicy:
    """Test access_policy property."""

    def test_access_policy_created_lazily(self) -> None:
        from apps.cases.services.template.folder_binding_service import CaseFolderBindingService

        with patch(
            "apps.cases.services.template.folder_binding_service.CaseAccessPolicy"
        ) as mock_policy_cls:
            mock_policy_cls.return_value = MagicMock()
            svc = CaseFolderBindingService()
            policy = svc.access_policy
            assert policy is not None


class TestCaseFolderBindingServiceRequireAdmin:
    """require_admin tests."""

    def test_unauthenticated_raises(self) -> None:
        from apps.cases.services.template.folder_binding_service import CaseFolderBindingService

        svc = CaseFolderBindingService()
        ctx = MagicMock()
        ctx.user = None
        with pytest.raises(PermissionDenied, match="需要登录"):
            svc.require_admin(ctx)

    def test_unauthenticated_user_raises(self) -> None:
        from apps.cases.services.template.folder_binding_service import CaseFolderBindingService

        svc = CaseFolderBindingService()
        ctx = MagicMock()
        ctx.user = MagicMock()
        ctx.user.is_authenticated = False
        with pytest.raises(PermissionDenied, match="需要登录"):
            svc.require_admin(ctx)

    def test_authenticated_user_passes(self) -> None:
        from apps.cases.services.template.folder_binding_service import CaseFolderBindingService

        svc = CaseFolderBindingService()
        ctx = MagicMock()
        ctx.user = MagicMock()
        ctx.user.is_authenticated = True
        # Should not raise
        svc.require_admin(ctx)


class TestCaseFolderBindingServiceGetCaseInternal:
    """_get_case_internal tests."""

    def test_case_not_found(self) -> None:
        from apps.cases.services.template.folder_binding_service import CaseFolderBindingService

        svc = CaseFolderBindingService()
        with patch("apps.cases.services.template.folder_binding_service.Case") as mock_cls:
            mock_cls.DoesNotExist = type("DoesNotExist", (Exception,), {})
            mock_cls.objects.get.side_effect = mock_cls.DoesNotExist()
            result = svc._get_case_internal(1)
            assert result is None

    def test_case_found(self) -> None:
        from apps.cases.services.template.folder_binding_service import CaseFolderBindingService

        svc = CaseFolderBindingService()
        mock_case = MagicMock()
        with patch("apps.cases.services.template.folder_binding_service.Case") as mock_cls:
            mock_cls.objects.get.return_value = mock_case
            result = svc._get_case_internal(1)
            assert result is mock_case


class TestCaseFolderBindingServiceGetContractFolderPath:
    """get_contract_folder_path tests."""

    def test_case_not_found(self) -> None:
        from apps.cases.services.template.folder_binding_service import CaseFolderBindingService

        svc = CaseFolderBindingService()
        with patch("apps.cases.services.template.folder_binding_service.Case") as mock_cls:
            mock_cls.DoesNotExist = type("DoesNotExist", (Exception,), {})
            mock_cls.objects.select_related.return_value.get.side_effect = mock_cls.DoesNotExist()
            result = svc.get_contract_folder_path(1)
            assert result is None

    def test_no_contract(self) -> None:
        from apps.cases.services.template.folder_binding_service import CaseFolderBindingService

        svc = CaseFolderBindingService()
        mock_case = MagicMock()
        mock_case.contract_id = None
        with patch("apps.cases.services.template.folder_binding_service.Case") as mock_cls:
            mock_cls.objects.select_related.return_value.get.return_value = mock_case
            result = svc.get_contract_folder_path(1)
            assert result is None

    def test_no_folder_binding(self) -> None:
        from apps.cases.services.template.folder_binding_service import CaseFolderBindingService

        svc = CaseFolderBindingService()
        mock_case = MagicMock()
        mock_case.contract_id = 10
        mock_case.contract = MagicMock()
        mock_case.contract.folder_binding = None
        with patch("apps.cases.services.template.folder_binding_service.Case") as mock_cls:
            mock_cls.objects.select_related.return_value.get.return_value = mock_case
            result = svc.get_contract_folder_path(1)
            assert result is None

    def test_returns_folder_path(self) -> None:
        from apps.cases.services.template.folder_binding_service import CaseFolderBindingService

        svc = CaseFolderBindingService()
        mock_case = MagicMock()
        mock_case.contract_id = 10
        mock_case.contract = MagicMock()
        mock_case.contract.folder_binding = MagicMock()
        mock_case.contract.folder_binding.folder_path = "/path/to/contract"
        with patch("apps.cases.services.template.folder_binding_service.Case") as mock_cls:
            mock_cls.objects.select_related.return_value.get.return_value = mock_case
            result = svc.get_contract_folder_path(1)
            assert result == "/path/to/contract"


class TestCaseFolderBindingServiceGetContractBinding:
    """_get_contract_binding tests."""

    def test_no_contract(self) -> None:
        from apps.cases.services.template.folder_binding_service import CaseFolderBindingService

        svc = CaseFolderBindingService()
        binding = MagicMock()
        binding.case.contract_id = None
        result = svc._get_contract_binding(binding)
        assert result is None

    def test_no_folder_binding_on_contract(self) -> None:
        from apps.cases.services.template.folder_binding_service import CaseFolderBindingService

        svc = CaseFolderBindingService()
        binding = MagicMock()
        binding.case.contract_id = 10
        binding.case.contract = MagicMock(spec=[])  # no folder_binding attribute
        result = svc._get_contract_binding(binding)
        assert result is None

    def test_returns_contract_folder_binding(self) -> None:
        from apps.cases.services.template.folder_binding_service import CaseFolderBindingService

        svc = CaseFolderBindingService()
        contract_binding = MagicMock()
        binding = MagicMock()
        binding.case.contract_id = 10
        binding.case.contract = MagicMock()
        binding.case.contract.folder_binding = contract_binding
        result = svc._get_contract_binding(binding)
        assert result is contract_binding


class TestCaseFolderBindingServiceCheckAndRepairContractPath:
    """check_and_repair_contract_path tests."""

    def test_no_contract_binding_returns_false(self) -> None:
        from apps.cases.services.template.folder_binding_service import CaseFolderBindingService

        svc = CaseFolderBindingService()
        binding = MagicMock()
        binding.case.contract_id = None
        result = svc.check_and_repair_contract_path(binding)
        assert result is False

    def test_repair_delegates_to_check_and_repair_path(self) -> None:
        from apps.cases.services.template.folder_binding_service import CaseFolderBindingService

        svc = CaseFolderBindingService()
        contract_binding = MagicMock()
        binding = MagicMock()
        binding.case.contract_id = 10
        binding.case.contract = MagicMock()
        binding.case.contract.folder_binding = contract_binding

        with patch.object(svc, "check_and_repair_path", return_value=({}, True)):
            result = svc.check_and_repair_contract_path(binding)
            assert result is True
            svc.check_and_repair_path.assert_called_once_with(contract_binding)


class TestCaseFolderBindingServiceResolveSubdirPath:
    """_resolve_subdir_path tests."""

    def test_no_folder_node_path(self) -> None:
        from apps.cases.services.template.folder_binding_service import CaseFolderBindingService

        svc = CaseFolderBindingService(document_service=MagicMock())
        svc._document_service.get_folder_binding_path.return_value = None
        result = svc._resolve_subdir_path(owner_type="case", subdir_key="case_documents")
        assert result is None

    def test_returns_normalized_path(self) -> None:
        from apps.cases.services.template.folder_binding_service import CaseFolderBindingService

        svc = CaseFolderBindingService(document_service=MagicMock())
        svc._document_service.get_folder_binding_path.return_value = "/some/path"
        with patch(
            "apps.core.filesystem.folder_node_path.normalize_folder_node_path",
            return_value="/normalized/path",
        ):
            result = svc._resolve_subdir_path(owner_type="case", subdir_key="case_documents")
            assert result == "/normalized/path"


class TestCaseFolderBindingServiceDefaultSubdirs:
    """DEFAULT_SUBDIRS constant test."""

    def test_has_expected_keys(self) -> None:
        from apps.cases.services.template.folder_binding_service import CaseFolderBindingService

        expected_keys = {"case_documents", "trial_materials", "judgments", "execution_documents", "other_files"}
        assert set(CaseFolderBindingService.DEFAULT_SUBDIRS.keys()) == expected_keys
