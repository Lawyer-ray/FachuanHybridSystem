"""
Unit tests for FolderGenerationService.

Covers:
  - __init__, contract_service, folder_binding_service
  - fetch_case_for_folder, fetch_template_by_id
  - find_matching_folder_template
  - format_root_folder_name
  - generate_folder_structure (with name, without name)
  - get_document_placements (filtering by case_type, inactive templates)
  - _find_contract_folder_path / _find_folder_by_name
  - create_zip_package
  - generate_folder_with_documents (contract not found, no template, success, zip fail)
  - generate_folder_with_documents_result
  - generate_case_folder_with_documents (basic, wrap_folder_name)
  - _find_special_folder_paths (identity, attorney, execution, nested)
  - _extract_to_bound_folder_if_exists (no binding, success, exception)
  - _create_folders_in_zip (basic, empty, no name)
  - _generate_document_filename
"""

from __future__ import annotations

import zipfile
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.core.exceptions import NotFoundError, ValidationException
from apps.documents.services.generation.folder_generation_service import (
    DocumentPlacement,
    FolderGenerationService,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service(**kwargs: Any) -> FolderGenerationService:
    defaults = dict(contract_service=MagicMock(), folder_binding_service=MagicMock())
    defaults.update(kwargs)
    return FolderGenerationService(**defaults)


def _make_folder_template(structure: dict | None = None) -> MagicMock:
    tpl = MagicMock()
    if structure is None:
        structure = {
            "name": "root",
            "children": [
                {"name": "子文件夹1", "children": []},
                {"name": "子文件夹2", "children": [{"name": "合同", "children": []}]},
            ],
        }
    tpl.structure = structure
    return tpl


# ===========================================================================
# Tests
# ===========================================================================


class TestInit:
    def test_init_with_deps(self) -> None:
        cs = MagicMock()
        fbs = MagicMock()
        svc = FolderGenerationService(contract_service=cs, folder_binding_service=fbs)
        assert svc.contract_service is cs
        assert svc.folder_binding_service is fbs

    def test_init_defaults(self) -> None:
        svc = FolderGenerationService()
        assert svc._contract_service is None
        assert svc._folder_binding_service is None

    def test_contract_service_not_injected_raises(self) -> None:
        svc = FolderGenerationService()
        with pytest.raises(RuntimeError, match="未注入"):
            _ = svc.contract_service


class TestFormatRootFolderName:
    def test_basic(self) -> None:
        svc = _make_service()
        contract = MagicMock()
        contract.case_type = "civil"
        contract.name = "测试合同"
        result = svc.format_root_folder_name(contract)
        today = date.today().strftime("%Y.%m.%d")
        assert result == f"{today}-[民商事]测试合同"

    def test_no_name(self) -> None:
        svc = _make_service()
        contract = MagicMock()
        contract.case_type = "criminal"
        contract.name = None
        result = svc.format_root_folder_name(contract)
        assert "未命名合同" in result

    def test_unknown_type(self) -> None:
        svc = _make_service()
        contract = MagicMock()
        contract.case_type = "unknown_type"
        contract.name = "X"
        result = svc.format_root_folder_name(contract)
        assert "unknown_type" in result


class TestGenerateFolderStructure:
    def test_with_root_name(self) -> None:
        svc = _make_service()
        tpl = _make_folder_template({"name": "old_root", "children": [{"name": "a"}]})
        result = svc.generate_folder_structure(tpl, "new_root")
        assert result["name"] == "new_root"
        assert result["children"] == [{"name": "a"}]

    def test_without_root_name(self) -> None:
        svc = _make_service()
        tpl = _make_folder_template({"children": [{"name": "a"}]})
        result = svc.generate_folder_structure(tpl, "root_name")
        assert result["name"] == "root_name"
        assert result["children"] == [{"name": "a"}]

    def test_empty_structure(self) -> None:
        svc = _make_service()
        tpl = _make_folder_template({})
        result = svc.generate_folder_structure(tpl, "root")
        assert result["name"] == "root"


class TestFindMatchingFolderTemplate:
    def test_delegates_to_matcher(self) -> None:
        svc = _make_service()
        tpl = MagicMock()
        with patch(
            "apps.documents.services.generation.pipeline.TemplateMatcher"
        ) as mock_matcher_cls:
            mock_matcher_cls.return_value.match_folder_template.return_value = tpl
            result = svc.find_matching_folder_template("civil")
        assert result is tpl


class TestGetDocumentPlacements:
    def test_filters_by_case_type(self) -> None:
        svc = _make_service()
        contract = MagicMock()
        contract.case_type = "civil"
        tpl = MagicMock()
        tpl.name = "tpl1"
        tpl.is_active = True
        tpl.contract_types = ["civil", "criminal"]
        tpl.get_file_location.return_value = "/tmp/file.docx"

        binding = MagicMock()
        binding.document_template = tpl
        binding.folder_node_path = "path/to/folder"
        binding.folder_node_id = 1

        with patch(
            "apps.documents.models.DocumentTemplateFolderBinding"
        ) as mock_binding_cls:
            mock_binding_cls.objects.filter.return_value.select_related.return_value = [binding]
            with patch.object(svc, "_generate_document_filename", return_value="output.docx"):
                result = svc.get_document_placements(contract, tpl)

        assert len(result) == 1
        assert result[0].folder_path == "path/to/folder"
        assert result[0].file_name == "output.docx"

    def test_skips_inactive_template(self) -> None:
        svc = _make_service()
        contract = MagicMock()
        contract.case_type = "civil"
        tpl = MagicMock()
        tpl.name = "tpl1"
        tpl.is_active = False
        tpl.contract_types = ["civil"]

        binding = MagicMock()
        binding.document_template = tpl
        binding.folder_node_path = "path"

        with patch(
            "apps.documents.models.DocumentTemplateFolderBinding"
        ) as mock_binding_cls:
            mock_binding_cls.objects.filter.return_value.select_related.return_value = [binding]
            result = svc.get_document_placements(contract, MagicMock())

        assert len(result) == 0

    def test_skips_non_matching_type(self) -> None:
        svc = _make_service()
        contract = MagicMock()
        contract.case_type = "civil"
        tpl = MagicMock()
        tpl.name = "tpl1"
        tpl.is_active = True
        tpl.contract_types = ["criminal"]

        binding = MagicMock()
        binding.document_template = tpl
        binding.folder_node_path = "path"

        with patch(
            "apps.documents.models.DocumentTemplateFolderBinding"
        ) as mock_binding_cls:
            mock_binding_cls.objects.filter.return_value.select_related.return_value = [binding]
            result = svc.get_document_placements(contract, MagicMock())

        assert len(result) == 0

    def test_accepts_all_type(self) -> None:
        svc = _make_service()
        contract = MagicMock()
        contract.case_type = "anything"
        tpl = MagicMock()
        tpl.name = "tpl1"
        tpl.is_active = True
        tpl.contract_types = ["all"]

        binding = MagicMock()
        binding.document_template = tpl
        binding.folder_node_path = ""

        with patch(
            "apps.documents.models.DocumentTemplateFolderBinding"
        ) as mock_binding_cls:
            mock_binding_cls.objects.filter.return_value.select_related.return_value = [binding]
            with patch.object(svc, "_generate_document_filename", return_value="doc.docx"):
                result = svc.get_document_placements(contract, MagicMock())

        assert len(result) == 1


class TestFindContractFolderPath:
    def test_found(self) -> None:
        svc = _make_service()
        tpl = _make_folder_template({
            "children": [{"name": "1-律师资料", "children": [{"name": "1-合同"}]}]
        })
        result = svc._find_contract_folder_path(tpl)
        assert result == "1-律师资料/1-合同"

    def test_not_found(self) -> None:
        svc = _make_service()
        tpl = _make_folder_template({"children": [{"name": "其他文件夹"}]})
        result = svc._find_contract_folder_path(tpl)
        assert result == ""

    def test_excludes_supplementary(self) -> None:
        svc = _make_service()
        tpl = _make_folder_template({
            "children": [{"name": "合同补充协议"}]
        })
        result = svc._find_contract_folder_path(tpl)
        assert result == ""

    def test_empty_structure(self) -> None:
        svc = _make_service()
        tpl = _make_folder_template({})
        result = svc._find_contract_folder_path(tpl)
        assert result == ""


class TestFindFolderByName:
    def test_found(self) -> None:
        svc = _make_service()
        children = [{"name": "A", "children": [{"name": "B"}]}]
        result = svc._find_folder_by_name(children, "B", [])
        assert result == ["A", "B"]

    def test_not_found(self) -> None:
        svc = _make_service()
        children = [{"name": "A"}]
        result = svc._find_folder_by_name(children, "Z", [])
        assert result == []


class TestCreateZipPackage:
    def test_creates_valid_zip(self) -> None:
        svc = _make_service()
        structure = {"name": "root", "children": []}
        docs = [("root", b"content1", "file1.txt"), ("root/sub", b"content2", "file2.txt")]

        with patch(
            "apps.documents.services.generation.pipeline.ZipPackager"
        ) as mock_packager_cls:
            mock_packager_cls.return_value.create.return_value = b"zip_content"
            result = svc.create_zip_package(structure, docs)
        assert result == b"zip_content"


class TestGenerateFolderWithDocuments:
    def test_contract_not_found(self) -> None:
        svc = _make_service()
        svc._contract_service.get_contract_with_details_internal.return_value = None
        with pytest.raises(NotFoundError):
            svc.generate_folder_with_documents(1)

    def test_no_matching_template(self) -> None:
        svc = _make_service()
        svc._contract_service.get_contract_with_details_internal.return_value = MagicMock(case_type="x", name="n")
        with patch.object(svc, "find_matching_folder_template", return_value=None):
            with pytest.raises(ValidationException) as exc_info:
                svc.generate_folder_with_documents(1)
        assert "NO_FOLDER_TEMPLATE" in exc_info.value.code

    def test_success(self) -> None:
        svc = _make_service()
        contract_data = MagicMock(case_type="civil", name="测试合同", law_firm_oa_case_number="")
        svc._contract_service.get_contract_with_details_internal.return_value = contract_data
        svc._contract_service.get_contract_model_internal.return_value = MagicMock()

        tpl = _make_folder_template()
        with patch.object(svc, "find_matching_folder_template", return_value=tpl), \
             patch.object(svc, "get_document_placements", return_value=[]), \
             patch.object(svc, "create_zip_package", return_value=b"zip"), \
             patch.object(svc, "_extract_to_bound_folder_if_exists", return_value=None):
            content, filename, error = svc.generate_folder_with_documents(1)

        assert content == b"zip"
        assert filename is not None
        assert error is None

    def test_zip_creation_exception(self) -> None:
        svc = _make_service()
        contract_data = MagicMock(case_type="civil", name="n")
        svc._contract_service.get_contract_with_details_internal.return_value = contract_data
        svc._contract_service.get_contract_model_internal.return_value = MagicMock()

        tpl = _make_folder_template()
        with patch.object(svc, "find_matching_folder_template", return_value=tpl), \
             patch.object(svc, "get_document_placements", return_value=[]), \
             patch.object(svc, "create_zip_package", side_effect=Exception("zip fail")):
            with pytest.raises(ValidationException):
                svc.generate_folder_with_documents(1)


class TestGenerateFolderWithDocumentsResult:
    def test_returns_extract_path(self) -> None:
        svc = _make_service()
        with patch.object(svc, "generate_folder_with_documents", return_value=(b"zip", "file.zip", None)):
            svc._last_extract_path = "/bound/path"
            content, filename, extract_path, error = svc.generate_folder_with_documents_result(1)
        assert extract_path == "/bound/path"


class TestExtractToBoundFolderIfExists:
    def test_no_binding_service(self) -> None:
        svc = FolderGenerationService(contract_service=MagicMock(), folder_binding_service=None)
        result = svc._extract_to_bound_folder_if_exists(1, b"zip")
        assert result is None

    def test_success(self) -> None:
        svc = _make_service()
        svc._folder_binding_service.extract_zip_to_bound_folder.return_value = "/extracted"
        result = svc._extract_to_bound_folder_if_exists(1, b"zip")
        assert result == "/extracted"

    def test_exception_returns_none(self) -> None:
        svc = _make_service()
        svc._folder_binding_service.extract_zip_to_bound_folder.side_effect = Exception("fail")
        result = svc._extract_to_bound_folder_if_exists(1, b"zip")
        assert result is None


class TestFindSpecialFolderPaths:
    def test_identity_path(self) -> None:
        svc = _make_service()
        structure = {
            "name": "root",
            "children": [{"name": "身份证明", "children": []}]
        }
        result = svc._find_special_folder_paths(structure)
        assert len(result["身份证明"]) == 1
        assert "身份证明" in result["身份证明"][0]

    def test_attorney_path(self) -> None:
        svc = _make_service()
        structure = {
            "name": "root",
            "children": [{"name": "委托材料", "children": []}]
        }
        result = svc._find_special_folder_paths(structure)
        assert len(result["委托材料"]) == 1

    def test_execution_path(self) -> None:
        svc = _make_service()
        structure = {
            "name": "root",
            "children": [{"name": "执行依据及生效证明", "children": []}]
        }
        result = svc._find_special_folder_paths(structure)
        assert len(result["执行依据及生效证明"]) == 1

    def test_empty(self) -> None:
        svc = _make_service()
        result = svc._find_special_folder_paths({})
        assert all(len(v) == 0 for v in result.values())

    def test_nested(self) -> None:
        svc = _make_service()
        structure = {
            "name": "root",
            "children": [
                {"name": "A", "children": [{"name": "身份证明", "children": []}]}
            ]
        }
        result = svc._find_special_folder_paths(structure)
        assert len(result["身份证明"]) == 1
        assert "A/身份证明" in result["身份证明"][0]


class TestCreateFoldersInZip:
    def test_basic(self) -> None:
        svc = _make_service()
        structure = {
            "name": "root",
            "children": [{"name": "child", "children": []}]
        }
        with patch("zipfile.ZipFile") as mock_zip:
            svc._create_folders_in_zip(mock_zip, structure, "")
        # root/, root/child/
        assert mock_zip.writestr.call_count == 2

    def test_empty_structure(self) -> None:
        svc = _make_service()
        with patch("zipfile.ZipFile") as mock_zip:
            svc._create_folders_in_zip(mock_zip, {}, "")
        mock_zip.writestr.assert_not_called()

    def test_no_name(self) -> None:
        svc = _make_service()
        with patch("zipfile.ZipFile") as mock_zip:
            svc._create_folders_in_zip(mock_zip, {"name": "", "children": []}, "")
        mock_zip.writestr.assert_not_called()


class TestGenerateDocumentFilename:
    def test_delegates_to_contract_generation_service(self) -> None:
        svc = _make_service()
        contract = MagicMock()
        template = MagicMock()

        with patch(
            "apps.documents.services.generation.contract_generation_service.ContractGenerationService"
        ) as mock_cgs_cls:
            mock_cgs_cls.return_value.generate_filename.return_value = "output.docx"
            result = svc._generate_document_filename(contract, template)

        assert result == "output.docx"


class TestDocumentPlacementDataclass:
    def test_fields(self) -> None:
        tpl = MagicMock()
        dp = DocumentPlacement(document_template=tpl, folder_path="a/b", file_name="c.docx")
        assert dp.document_template is tpl
        assert dp.folder_path == "a/b"
        assert dp.file_name == "c.docx"
