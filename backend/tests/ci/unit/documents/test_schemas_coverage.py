"""Tests for documents schemas."""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from apps.documents.schemas import (
    DocumentEnumsOut,
    DocumentTemplateIn,
    DocumentTemplateOut,
    DocumentTemplateUpdate,
    EnumOptionOut,
    FolderBindingOut,
    FolderTemplateIn,
    FolderTemplateOut,
    FolderTemplateUpdate,
    PlaceholderIn,
    PlaceholderOut,
    PlaceholderPreviewOut,
    PlaceholderUpdate,
)


class TestFolderTemplateIn:
    def test_defaults(self) -> None:
        s = FolderTemplateIn(name="Test")
        assert s.name == "Test"
        assert s.template_type == "contract"
        assert s.case_types == []
        assert s.case_stages == []
        assert s.contract_types == []
        assert s.structure == {}
        assert s.is_default is False
        assert s.is_active is True


class TestFolderTemplateUpdate:
    def test_all_none_by_default(self) -> None:
        s = FolderTemplateUpdate()
        assert s.name is None
        assert s.template_type is None
        assert s.case_types is None
        assert s.structure is None


class TestFolderTemplateOut:
    def test_resolve_display_fields(self) -> None:
        obj = MagicMock()
        obj.template_type_display = "合同模板"
        obj.case_types_display = "民事"
        obj.case_stages_display = "一审"
        obj.contract_types_display = "民事合同"

        assert FolderTemplateOut.resolve_template_type_display(obj) == "合同模板"
        assert FolderTemplateOut.resolve_case_types_display(obj) == "民事"
        assert FolderTemplateOut.resolve_case_stages_display(obj) == "一审"
        assert FolderTemplateOut.resolve_contract_types_display(obj) == "民事合同"


class TestDocumentTemplateIn:
    def test_defaults(self) -> None:
        s = DocumentTemplateIn(name="Test")
        assert s.name == "Test"
        assert s.template_type == "contract"
        assert s.contract_sub_type is None
        assert s.case_sub_type is None
        assert s.archive_sub_type is None
        assert s.file_path is None
        assert s.case_types == []
        assert s.case_stages == []
        assert s.contract_types == []
        assert s.is_active is True


class TestDocumentTemplateUpdate:
    def test_all_none_by_default(self) -> None:
        s = DocumentTemplateUpdate()
        assert s.name is None
        assert s.template_type is None
        assert s.contract_sub_type is None


class TestFolderBindingOut:
    def test_fields(self) -> None:
        s = FolderBindingOut(
            id=1,
            folder_template_id=2,
            folder_template_name="Test",
            folder_node_id="node1",
            folder_node_path="path/to/node",
            is_active=True,
        )
        assert s.id == 1
        assert s.folder_template_name == "Test"


class TestDocumentTemplateOut:
    def test_resolve_display_fields(self) -> None:
        obj = MagicMock()
        obj.template_type_display = "合同"
        obj.case_types_display = "民事"
        obj.case_stages_display = "一审"
        obj.contract_types_display = "民事"
        obj.get_file_location.return_value = "/path/to/file.docx"

        assert DocumentTemplateOut.resolve_template_type_display(obj) == "合同"
        assert DocumentTemplateOut.resolve_case_types_display(obj) == "民事"
        assert DocumentTemplateOut.resolve_case_stages_display(obj) == "一审"
        assert DocumentTemplateOut.resolve_contract_types_display(obj) == "民事"
        assert DocumentTemplateOut.resolve_file_location(obj) == "/path/to/file.docx"

    def test_resolve_file_location_empty(self) -> None:
        obj = MagicMock()
        obj.get_file_location.return_value = ""
        assert DocumentTemplateOut.resolve_file_location(obj) is None

    def test_resolve_folder_bindings(self) -> None:
        obj = MagicMock()
        binding = MagicMock()
        binding.id = 1
        binding.folder_template_id = 2
        binding.folder_template.name = "Test Folder"
        binding.folder_node_id = "node1"
        binding.folder_node_path = "path"
        binding.is_active = True
        obj.folder_bindings.all.return_value = [binding]

        result = DocumentTemplateOut.resolve_folder_bindings(obj)
        assert len(result) == 1
        assert result[0].id == 1
        assert result[0].folder_template_name == "Test Folder"


class TestPlaceholderSchemas:
    def test_placeholder_in(self) -> None:
        s = PlaceholderIn(key="test_key", display_name="Test")
        assert s.key == "test_key"
        assert s.example_value == ""
        assert s.is_active is True

    def test_placeholder_update(self) -> None:
        s = PlaceholderUpdate()
        assert s.key is None
        assert s.display_name is None

    def test_placeholder_preview_out(self) -> None:
        s = PlaceholderPreviewOut(contract_id=1, values={"k": "v"}, missing_keys=["m"])
        assert s.contract_id == 1
        assert s.values == {"k": "v"}


class TestEnumSchemas:
    def test_enum_option_out(self) -> None:
        s = EnumOptionOut(value="civil", label="民事")
        assert s.value == "civil"
        assert s.label == "民事"

    def test_document_enums_out(self) -> None:
        s = DocumentEnumsOut(
            case_types=[EnumOptionOut(value="c", label="C")],
            case_stages=[EnumOptionOut(value="s", label="S")],
            contract_types=[EnumOptionOut(value="t", label="T")],
            template_types=[EnumOptionOut(value="tt", label="TT")],
            folder_template_types=[EnumOptionOut(value="ft", label="FT")],
        )
        assert len(s.case_types) == 1
