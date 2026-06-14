"""Round 6 coverage tests - batch 2: services, bindings, query services.

Covers:
- apps/documents/services/template/contract_template/binding_service.py
- apps/documents/services/evidence/evidence_query_service.py (_build_dtos)
- apps/documents/services/evidence/evidence_file_service.py (constants, validation)
- apps/documents/services/evidence/evidence_service.py (calculate_start_order, calculate_start_page)
- apps/documents/services/template/folder_service.py (re-export)
- apps/cases/services/material/case_material_query_service.py
- apps/cases/services/case/repo/case_repo.py (list_cases)
- apps/documents/services/placeholders/litigation/filename_service.py
- apps/documents/services/template/document_template/query_service.py
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, PropertyMock, patch

import pytest


# ============================================================
# documents/services/template/contract_template/binding_service.py
# ============================================================


class TestDocumentTemplateBindingService:
    def test_calculate_folder_path_empty_structure(self) -> None:
        from apps.documents.services.template.contract_template.binding_service import DocumentTemplateBindingService
        svc = DocumentTemplateBindingService()
        ft = SimpleNamespace(structure={})
        assert svc.calculate_folder_path(ft, "node1") == ""

    def test_calculate_folder_path_none_structure(self) -> None:
        from apps.documents.services.template.contract_template.binding_service import DocumentTemplateBindingService
        svc = DocumentTemplateBindingService()
        ft = SimpleNamespace(structure=None)
        assert svc.calculate_folder_path(ft, "node1") == ""

    def test_calculate_folder_path_found(self) -> None:
        from apps.documents.services.template.contract_template.binding_service import DocumentTemplateBindingService
        svc = DocumentTemplateBindingService()
        ft = SimpleNamespace(structure={
            "children": [
                {"id": "node1", "name": "一审"},
                {"id": "node2", "name": "二审"},
            ]
        })
        assert svc.calculate_folder_path(ft, "node1") == "一审"

    def test_calculate_folder_path_nested(self) -> None:
        from apps.documents.services.template.contract_template.binding_service import DocumentTemplateBindingService
        svc = DocumentTemplateBindingService()
        ft = SimpleNamespace(structure={
            "children": [
                {
                    "id": "parent",
                    "name": "一级",
                    "children": [
                        {"id": "child", "name": "二级"},
                    ]
                }
            ]
        })
        assert svc.calculate_folder_path(ft, "child") == "一级/二级"

    def test_calculate_folder_path_not_found(self) -> None:
        from apps.documents.services.template.contract_template.binding_service import DocumentTemplateBindingService
        svc = DocumentTemplateBindingService()
        ft = SimpleNamespace(structure={
            "children": [
                {"id": "node1", "name": "一审"},
            ]
        })
        assert svc.calculate_folder_path(ft, "nonexistent") == ""

    def test_get_case_subdir_path_empty_params(self) -> None:
        from apps.documents.services.template.contract_template.binding_service import DocumentTemplateBindingService
        svc = DocumentTemplateBindingService()
        assert svc.get_case_subdir_path_internal("", "key") is None
        assert svc.get_case_subdir_path_internal("civil", "") is None

    def test_get_contract_subdir_path_empty_params(self) -> None:
        from apps.documents.services.template.contract_template.binding_service import DocumentTemplateBindingService
        svc = DocumentTemplateBindingService()
        assert svc.get_contract_subdir_path_internal("", "sub") is None
        assert svc.get_contract_subdir_path_internal("civil", "") is None

    @patch("apps.documents.services.template.contract_template.binding_service.FolderTemplate")
    @patch("apps.documents.services.template.contract_template.binding_service.FolderTemplateType")
    def test_get_case_subdir_no_matching_template(self, mock_ft_type, mock_ft) -> None:
        from apps.documents.services.template.contract_template.binding_service import DocumentTemplateBindingService
        mock_ft_type.CASE = "case"
        mock_ft.objects.filter.return_value = []
        svc = DocumentTemplateBindingService()
        assert svc.get_case_subdir_path_internal("civil", "key") is None

    @patch("apps.documents.services.template.contract_template.binding_service.DocumentTemplateFolderBinding")
    @patch("apps.documents.services.template.contract_template.binding_service.FolderTemplate")
    @patch("apps.documents.services.template.contract_template.binding_service.FolderTemplateType")
    def test_get_case_subdir_no_binding(self, mock_ft_type, mock_ft, mock_binding) -> None:
        from apps.documents.services.template.contract_template.binding_service import DocumentTemplateBindingService
        mock_ft_type.CASE = "case"
        ft = SimpleNamespace(case_types=["civil"])
        mock_ft.objects.filter.return_value = [ft]
        mock_binding.objects.filter.return_value.first.return_value = None
        svc = DocumentTemplateBindingService()
        assert svc.get_case_subdir_path_internal("civil", "key") is None

    @patch("apps.documents.services.template.contract_template.binding_service.DocumentTemplateFolderBinding")
    @patch("apps.documents.services.template.contract_template.binding_service.FolderTemplate")
    @patch("apps.documents.services.template.contract_template.binding_service.FolderTemplateType")
    def test_get_case_subdir_with_binding(self, mock_ft_type, mock_ft, mock_binding) -> None:
        from apps.documents.services.template.contract_template.binding_service import DocumentTemplateBindingService
        mock_ft_type.CASE = "case"
        ft = SimpleNamespace(case_types=["civil"])
        mock_ft.objects.filter.return_value = [ft]
        binding = SimpleNamespace(folder_node_path="path/to/dir")
        mock_binding.objects.filter.return_value.first.return_value = binding
        svc = DocumentTemplateBindingService()
        assert svc.get_case_subdir_path_internal("civil", "key") == "path/to/dir"

    @patch("apps.documents.services.template.contract_template.binding_service.DocumentTemplateFolderBinding")
    @patch("apps.documents.services.template.contract_template.binding_service.DocumentTemplate")
    @patch("apps.documents.services.template.contract_template.binding_service.DocumentTemplateType")
    @patch("apps.documents.services.template.contract_template.binding_service.FolderTemplate")
    @patch("apps.documents.services.template.contract_template.binding_service.FolderTemplateType")
    def test_get_contract_subdir_full_match(self, mock_ft_type, mock_ft, mock_dt_type, mock_dt, mock_binding) -> None:
        from apps.documents.services.template.contract_template.binding_service import DocumentTemplateBindingService
        mock_ft_type.CONTRACT = "contract"
        mock_dt_type.CONTRACT = "contract"
        ft = SimpleNamespace(contract_types=["civil"])
        mock_ft.objects.filter.return_value = [ft]
        dt = SimpleNamespace(contract_types=["civil"])
        mock_dt.objects.filter.return_value = [dt]
        binding = SimpleNamespace(folder_node_path="contract/path")
        mock_binding.objects.filter.return_value.first.return_value = binding
        svc = DocumentTemplateBindingService()
        assert svc.get_contract_subdir_path_internal("civil", "contract") == "contract/path"

    @patch("apps.documents.services.template.contract_template.binding_service.FolderTemplate")
    @patch("apps.documents.services.template.contract_template.binding_service.FolderTemplateType")
    def test_get_contract_subdir_no_folder_template(self, mock_ft_type, mock_ft) -> None:
        from apps.documents.services.template.contract_template.binding_service import DocumentTemplateBindingService
        mock_ft_type.CONTRACT = "contract"
        mock_ft.objects.filter.return_value = []
        svc = DocumentTemplateBindingService()
        assert svc.get_contract_subdir_path_internal("civil", "contract") is None


# ============================================================
# documents/services/evidence/evidence_query_service.py
# ============================================================


class TestEvidenceQueryServiceBuildDtos:
    def _make_service(self) -> Any:
        from apps.documents.services.evidence.evidence_query_service import EvidenceQueryService
        return EvidenceQueryService()

    @patch("apps.documents.services.evidence.evidence_query_service.EvidenceItem")
    def test_build_dtos_empty(self, mock_model) -> None:
        svc = self._make_service()
        result = svc._build_dtos([])
        assert result == []

    @patch("apps.documents.services.evidence.evidence_query_service.EvidenceItem")
    def test_build_dtos_with_file(self, mock_model) -> None:
        svc = self._make_service()
        file_field = MagicMock()
        file_field.storage.path.return_value = "/path/to/file.pdf"
        mock_model._meta.get_field.return_value = file_field
        items = [{"id": 1, "order": 1, "name": "doc", "purpose": "test", "page_start": 1, "page_end": 5, "file": "file.pdf"}]
        result = svc._build_dtos(items)
        assert len(result) == 1
        assert result[0].id == 1
        assert result[0].file_path == "/path/to/file.pdf"

    @patch("apps.documents.services.evidence.evidence_query_service.EvidenceItem")
    def test_build_dtos_no_file(self, mock_model) -> None:
        svc = self._make_service()
        file_field = MagicMock()
        mock_model._meta.get_field.return_value = file_field
        items = [{"id": 1, "order": 1, "name": "doc", "purpose": "test", "page_start": None, "page_end": None, "file": None}]
        result = svc._build_dtos(items)
        assert result[0].file_path is None

    @patch("apps.documents.services.evidence.evidence_query_service.EvidenceItem")
    def test_build_dtos_file_error(self, mock_model) -> None:
        svc = self._make_service()
        file_field = MagicMock()
        file_field.storage.path.side_effect = OSError("file not found")
        mock_model._meta.get_field.return_value = file_field
        items = [{"id": 1, "order": None, "name": None, "purpose": None, "page_start": None, "page_end": None, "file": "missing.pdf"}]
        result = svc._build_dtos(items)
        assert result[0].file_path is None
        assert result[0].name == ""
        assert result[0].order == 0

    @patch("apps.documents.services.evidence.evidence_query_service.EvidenceItem")
    def test_list_evidence_item_ids_empty(self, mock_model) -> None:
        svc = self._make_service()
        result = svc.list_evidence_item_ids_with_files_internal([])
        assert result == []


# ============================================================
# documents/services/evidence/evidence_file_service.py
# ============================================================


class TestEvidenceFileServiceConstants:
    def test_supported_formats(self) -> None:
        from apps.documents.services.evidence.evidence_file_service import EvidenceFileService
        assert ".pdf" in EvidenceFileService.SUPPORTED_FORMATS
        assert ".docx" in EvidenceFileService.SUPPORTED_FORMATS
        assert ".jpg" in EvidenceFileService.SUPPORTED_FORMATS
        assert ".png" in EvidenceFileService.SUPPORTED_FORMATS

    def test_max_file_size(self) -> None:
        from apps.documents.services.evidence.evidence_file_service import EvidenceFileService
        assert EvidenceFileService.MAX_FILE_SIZE == 50 * 1024 * 1024


# ============================================================
# documents/services/evidence/evidence_service.py
# ============================================================


class TestEvidenceServiceCalculateStartOrder:
    def test_no_previous_list(self) -> None:
        from apps.documents.services.evidence.evidence_service import EvidenceService
        svc = EvidenceService()
        evidence_list = SimpleNamespace(previous_list_id=None, pk=1, previous_list=None)
        assert svc.calculate_start_order(evidence_list) == 1

    def test_single_previous_list(self) -> None:
        from apps.documents.services.evidence.evidence_service import EvidenceService
        svc = EvidenceService()
        prev = SimpleNamespace(pk=2, previous_list_id=None, items=MagicMock())
        prev.items.count.return_value = 3
        evidence_list = SimpleNamespace(previous_list_id=2, pk=1, previous_list=prev)
        assert svc.calculate_start_order(evidence_list) == 4

    def test_circular_reference_detection(self) -> None:
        from apps.documents.services.evidence.evidence_service import EvidenceService
        svc = EvidenceService()
        # Create a circular reference: list A -> list B -> list A
        list_a = SimpleNamespace(pk=1, previous_list_id=2, items=MagicMock())
        list_b = SimpleNamespace(pk=2, previous_list_id=1, items=MagicMock())
        list_b.items.count.return_value = 2
        list_a.previous_list = list_b
        list_b.previous_list = list_a  # circular!
        assert svc.calculate_start_order(list_a) == 1

    def test_chain_of_three(self) -> None:
        from apps.documents.services.evidence.evidence_service import EvidenceService
        svc = EvidenceService()
        list_c = SimpleNamespace(pk=3, previous_list_id=None, items=MagicMock())
        list_c.items.count.return_value = 5
        list_b = SimpleNamespace(pk=2, previous_list_id=3, items=MagicMock())
        list_b.items.count.return_value = 3
        list_b.previous_list = list_c
        list_a = SimpleNamespace(pk=1, previous_list_id=2, items=MagicMock())
        list_a.previous_list = list_b
        # total = 3 + 5 + 1 = 9
        assert svc.calculate_start_order(list_a) == 9


class TestEvidenceServiceCalculateStartPage:
    def test_no_previous_list(self) -> None:
        from apps.documents.services.evidence.evidence_service import EvidenceService
        svc = EvidenceService()
        evidence_list = SimpleNamespace(previous_list_id=None, pk=1, previous_list=None)
        assert svc.calculate_start_page(evidence_list) == 1

    def test_single_previous_list(self) -> None:
        from apps.documents.services.evidence.evidence_service import EvidenceService
        svc = EvidenceService()
        prev = SimpleNamespace(pk=2, previous_list_id=None, total_pages=10)
        evidence_list = SimpleNamespace(previous_list_id=2, pk=1, previous_list=prev)
        assert svc.calculate_start_page(evidence_list) == 11

    def test_circular_reference_detection(self) -> None:
        from apps.documents.services.evidence.evidence_service import EvidenceService
        svc = EvidenceService()
        list_a = SimpleNamespace(pk=1, previous_list_id=2, total_pages=5)
        list_b = SimpleNamespace(pk=2, previous_list_id=1, total_pages=3)
        list_a.previous_list = list_b
        list_b.previous_list = list_a
        assert svc.calculate_start_page(list_a) == 1

    def test_chain_of_three(self) -> None:
        from apps.documents.services.evidence.evidence_service import EvidenceService
        svc = EvidenceService()
        list_c = SimpleNamespace(pk=3, previous_list_id=None, total_pages=10)
        list_b = SimpleNamespace(pk=2, previous_list_id=3, total_pages=5)
        list_b.previous_list = list_c
        list_a = SimpleNamespace(pk=1, previous_list_id=2, total_pages=0)
        list_a.previous_list = list_b
        # total = 5 + 10 + 1 = 16
        assert svc.calculate_start_page(list_a) == 16


class TestEvidenceServiceLazyInit:
    def test_case_service_not_injected_raises(self) -> None:
        from apps.documents.services.evidence.evidence_service import EvidenceService
        svc = EvidenceService()
        with pytest.raises(RuntimeError, match="未注入"):
            _ = svc.case_service

    def test_injected_case_service(self) -> None:
        from apps.documents.services.evidence.evidence_service import EvidenceService
        mock_case = MagicMock()
        svc = EvidenceService(case_service=mock_case)
        assert svc.case_service is mock_case


# ============================================================
# documents/services/placeholders/litigation/filename_service.py
# ============================================================


class TestFilenameServiceReExport:
    def test_importable(self) -> None:
        from apps.documents.services.placeholders.litigation import filename_service
        assert filename_service is not None


# ============================================================
# documents/services/template/document_template/query_service.py
# ============================================================


class TestDocumentTemplateQueryServiceReExport:
    def test_importable(self) -> None:
        from apps.documents.services.template.document_template import query_service
        assert query_service is not None


# ============================================================
# cases/services/material/case_material_query_service.py
# ============================================================


class TestCaseMaterialQueryService:
    def test_case_service_not_injected_raises(self) -> None:
        from apps.cases.services.material.case_material_query_service import CaseMaterialQueryService
        svc = CaseMaterialQueryService()
        with pytest.raises(RuntimeError, match="未注入"):
            _ = svc.case_service

    def test_case_service_injected(self) -> None:
        from apps.cases.services.material.case_material_query_service import CaseMaterialQueryService
        mock_cs = MagicMock()
        svc = CaseMaterialQueryService(case_service=mock_cs)
        assert svc.case_service is mock_cs

    def test_build_group_order_map(self) -> None:
        from apps.cases.services.material.case_material_query_service import CaseMaterialQueryService
        svc = CaseMaterialQueryService()
        rows = [
            SimpleNamespace(category="party", side="our", supervising_authority_id=None, type_id=1),
            SimpleNamespace(category="party", side="our", supervising_authority_id=None, type_id=2),
            SimpleNamespace(category="non_party", side=None, supervising_authority_id=10, type_id=3),
        ]
        result = svc._build_group_order_map(rows)
        assert ("party", "our", 0) in result
        assert result[("party", "our", 0)] == [1, 2]
        assert ("non_party", "", 10) in result

    def test_sorted_groups_ordered(self) -> None:
        from apps.cases.services.material.case_material_query_service import CaseMaterialQueryService
        svc = CaseMaterialQueryService()
        groups = {
            1: {"type_id": 1, "type_name": "甲类", "items": []},
            2: {"type_id": 2, "type_name": "乙类", "items": []},
        }
        order_map = {("party", "our", 0): [2, 1]}
        result = svc._sorted_groups("party", "our", None, groups, order_map)
        assert result[0]["type_id"] == 2
        assert result[1]["type_id"] == 1

    def test_sorted_groups_unordered_remainder(self) -> None:
        from apps.cases.services.material.case_material_query_service import CaseMaterialQueryService
        svc = CaseMaterialQueryService()
        groups = {
            1: {"type_id": 1, "type_name": "乙类", "items": []},
            3: {"type_id": 3, "type_name": "甲类", "items": []},
        }
        # order_map only has type 1, type 3 is remainder
        order_map = {("party", "our", 0): [1]}
        result = svc._sorted_groups("party", "our", None, groups, order_map)
        assert result[0]["type_id"] == 1  # ordered
        assert result[1]["type_id"] == 3  # remainder, sorted by name

    def test_material_item_payload_no_attachment(self) -> None:
        from apps.cases.services.material.case_material_query_service import CaseMaterialQueryService
        svc = CaseMaterialQueryService()
        m = SimpleNamespace(
            id=1,
            source_attachment=None,
            source_attachment_id=None,
            parties=MagicMock(),
        )
        m.parties.all.return_value = []
        result = svc._material_item_payload(m)
        assert result["material_id"] == 1
        assert result["file_name"] == ""
        assert result["file_url"] == ""

    def test_material_item_payload_with_attachment(self) -> None:
        from apps.cases.services.material.case_material_query_service import CaseMaterialQueryService
        svc = CaseMaterialQueryService()
        att = SimpleNamespace(
            original_filename="doc.pdf",
            file=SimpleNamespace(name="doc.pdf", url="http://example.com/doc.pdf"),
            uploaded_at="2024-01-01",
        )
        party = SimpleNamespace(client=SimpleNamespace(name="张三"))
        m = SimpleNamespace(
            id=1,
            source_attachment=att,
            source_attachment_id=10,
            parties=MagicMock(),
        )
        m.parties.all.return_value = [party]
        result = svc._material_item_payload(m)
        assert result["file_name"] == "doc.pdf"
        assert result["party_labels"] == ["张三"]

    def test_material_item_payload_empty_filename_fallback(self) -> None:
        from apps.cases.services.material.case_material_query_service import CaseMaterialQueryService
        svc = CaseMaterialQueryService()
        att = SimpleNamespace(
            original_filename="",
            file=SimpleNamespace(name="path/to/file.docx", url=""),
            uploaded_at=None,
        )
        m = SimpleNamespace(
            id=2,
            source_attachment=att,
            source_attachment_id=20,
            parties=MagicMock(),
        )
        m.parties.all.return_value = []
        result = svc._material_item_payload(m)
        # original_filename is empty, falls back to file.name, then rsplit
        assert result["file_name"] == "file.docx"
