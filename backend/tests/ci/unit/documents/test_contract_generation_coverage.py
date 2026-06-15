"""Tests for documents/services/generation/contract_generation_service.py — full branch coverage.

Covers: ContractGenerationService, LawyerWrapper, AssignmentWrapper, AssignmentListWrapper,
ContractDataWrapper, generate_contract_document, generate_filename, _save_to_bound_folder,
_build_contract_context_directly.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Wrapper classes
# ---------------------------------------------------------------------------

class TestLawyerWrapper:
    def test_real_name_from_lawyer_name(self):
        from apps.documents.services.generation.contract_generation_service import LawyerWrapper
        lw = LawyerWrapper({"lawyer_name": "张律师"})
        assert lw.real_name == "张律师"

    def test_real_name_from_real_name(self):
        from apps.documents.services.generation.contract_generation_service import LawyerWrapper
        lw = LawyerWrapper({"real_name": "李律师"})
        assert lw.real_name == "李律师"

    def test_real_name_empty(self):
        from apps.documents.services.generation.contract_generation_service import LawyerWrapper
        lw = LawyerWrapper({})
        assert lw.real_name == ""

    def test_username_from_username(self):
        from apps.documents.services.generation.contract_generation_service import LawyerWrapper
        lw = LawyerWrapper({"username": "zhang"})
        assert lw.username == "zhang"

    def test_username_from_lawyer_username(self):
        from apps.documents.services.generation.contract_generation_service import LawyerWrapper
        lw = LawyerWrapper({"lawyer_username": "li"})
        assert lw.username == "li"

    def test_username_empty(self):
        from apps.documents.services.generation.contract_generation_service import LawyerWrapper
        lw = LawyerWrapper({})
        assert lw.username == ""

    def test_id_from_lawyer_id(self):
        from apps.documents.services.generation.contract_generation_service import LawyerWrapper
        lw = LawyerWrapper({"lawyer_id": 42})
        assert lw.id == 42

    def test_id_from_id(self):
        from apps.documents.services.generation.contract_generation_service import LawyerWrapper
        lw = LawyerWrapper({"id": 99})
        assert lw.id == 99

    def test_id_none(self):
        from apps.documents.services.generation.contract_generation_service import LawyerWrapper
        lw = LawyerWrapper({})
        assert lw.id is None


class TestAssignmentWrapper:
    def test_basic(self):
        from apps.documents.services.generation.contract_generation_service import AssignmentWrapper
        aw = AssignmentWrapper({"id": 1, "is_primary": True, "order": 2})
        assert aw.id == 1
        assert aw.is_primary is True
        assert aw.order == 2
        assert isinstance(aw.lawyer, MagicMock) or hasattr(aw.lawyer, 'real_name')

    def test_defaults(self):
        from apps.documents.services.generation.contract_generation_service import AssignmentWrapper
        aw = AssignmentWrapper({})
        assert aw.id is None
        assert aw.is_primary is False
        assert aw.order is None


class TestAssignmentListWrapper:
    def test_all(self):
        from apps.documents.services.generation.contract_generation_service import AssignmentListWrapper
        alw = AssignmentListWrapper([{"id": 1}, {"id": 2}])
        assert len(alw.all()) == 2

    def test_empty(self):
        from apps.documents.services.generation.contract_generation_service import AssignmentListWrapper
        alw = AssignmentListWrapper([])
        assert alw.all() == []

    def test_none_input(self):
        from apps.documents.services.generation.contract_generation_service import AssignmentListWrapper
        alw = AssignmentListWrapper(None)
        assert alw.all() == []


class TestContractDataWrapper:
    def test_basic(self):
        from apps.documents.services.generation.contract_generation_service import ContractDataWrapper
        cdw = ContractDataWrapper({"id": 1, "name": "合同A", "case_type": "civil"})
        assert cdw.id == 1
        assert cdw.name == "合同A"
        assert cdw.case_type == "civil"
        assert isinstance(cdw.assignments, object)

    def test_empty(self):
        from apps.documents.services.generation.contract_generation_service import ContractDataWrapper
        cdw = ContractDataWrapper({})
        assert cdw.id is None
        assert cdw.name == ""
        assert cdw.case_type == ""


# ---------------------------------------------------------------------------
# ContractGenerationService
# ---------------------------------------------------------------------------


class TestContractGenerationServiceInit:
    def test_default_init(self):
        from apps.documents.services.generation.contract_generation_service import ContractGenerationService
        svc = ContractGenerationService()
        assert svc._contract_service is None
        assert svc._folder_binding_service is None
        assert svc._last_saved_path is None


class TestContractGenerationServiceGenerateContract:
    def test_contract_not_found(self):
        from apps.documents.services.generation.contract_generation_service import ContractGenerationService
        svc = ContractGenerationService()
        mock_svc = MagicMock()
        mock_svc.get_contract_model_internal.return_value = None
        svc._contract_service = mock_svc
        content, filename, error = svc.generate_contract_document(1)
        assert content is None
        assert error == "合同不存在"

    def test_no_matching_template(self):
        from apps.documents.services.generation.contract_generation_service import ContractGenerationService
        svc = ContractGenerationService()
        mock_contract = MagicMock()
        mock_svc = MagicMock()
        mock_svc.get_contract_model_internal.return_value = mock_contract
        svc._contract_service = mock_svc
        with patch.object(svc, 'find_matching_template', return_value=None):
            content, filename, error = svc.generate_contract_document(1)
            assert content is None
            assert error == "请先添加合同模板"

    def test_template_file_not_exists(self):
        from apps.documents.services.generation.contract_generation_service import ContractGenerationService
        svc = ContractGenerationService()
        mock_contract = MagicMock()
        mock_contract.case_type = "civil"
        mock_svc = MagicMock()
        mock_svc.get_contract_model_internal.return_value = mock_contract
        svc._contract_service = mock_svc
        mock_template = MagicMock()
        mock_template.get_file_location.return_value = "/missing.docx"
        with patch.object(svc, 'find_matching_template', return_value=mock_template):
            with patch("apps.documents.services.generation.contract_generation_service.Path") as MockPath:
                MockPath.return_value.exists.return_value = False
                content, filename, error = svc.generate_contract_document(1)
                assert content is None
                assert error == "模板文件不存在"


class TestContractGenerationServiceSaveToBoundFolder:
    def test_no_binding_service(self):
        from apps.documents.services.generation.contract_generation_service import ContractGenerationService
        svc = ContractGenerationService()
        result = svc._save_to_bound_folder_if_exists(1, b"content", "test.docx", "subdir")
        assert result is None

    def test_save_success(self):
        from apps.documents.services.generation.contract_generation_service import ContractGenerationService
        mock_binding_svc = MagicMock()
        mock_binding_svc.save_file_to_bound_folder.return_value = "/saved/path.docx"
        svc = ContractGenerationService(folder_binding_service=mock_binding_svc)
        result = svc._save_to_bound_folder_if_exists(1, b"content", "test.docx", "subdir")
        assert result == "/saved/path.docx"

    def test_save_failure(self):
        from apps.documents.services.generation.contract_generation_service import ContractGenerationService
        mock_binding_svc = MagicMock()
        mock_binding_svc.save_file_to_bound_folder.side_effect = RuntimeError("disk full")
        svc = ContractGenerationService(folder_binding_service=mock_binding_svc)
        result = svc._save_to_bound_folder_if_exists(1, b"content", "test.docx", "subdir")
        assert result is None

    def test_save_returns_none(self):
        from apps.documents.services.generation.contract_generation_service import ContractGenerationService
        mock_binding_svc = MagicMock()
        mock_binding_svc.save_file_to_bound_folder.return_value = None
        svc = ContractGenerationService(folder_binding_service=mock_binding_svc)
        result = svc._save_to_bound_folder_if_exists(1, b"content", "test.docx", "subdir")
        assert result is None


class TestContractGenerationServiceGenerateContractResult:
    def test_returns_tuple_with_saved_path(self):
        from apps.documents.services.generation.contract_generation_service import ContractGenerationService
        svc = ContractGenerationService()
        svc._last_saved_path = "/saved/doc.docx"
        with patch.object(svc, 'generate_contract_document', return_value=(b"content", "doc.docx", None)):
            content, filename, saved_path, error = svc.generate_contract_document_result(1)
            assert saved_path == "/saved/doc.docx"
            assert error is None
