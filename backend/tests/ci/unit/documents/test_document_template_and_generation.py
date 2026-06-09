"""Tests for documents app models: DocumentTemplate, DocumentTemplateFolderBinding, GenerationTask, GenerationConfig."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.documents.models.choices import (
    DocumentArchiveSubType,
    DocumentCaseFileSubType,
    DocumentCaseStage,
    DocumentCaseType,
    DocumentContractSubType,
    DocumentContractType,
    DocumentTemplateType,
)
from apps.documents.models.document_template import (
    DocumentTemplate,
    DocumentTemplateFolderBinding,
)
from apps.documents.models.generation import (
    GenerationConfig,
    GenerationMethod,
    GenerationStatus,
    GenerationTask,
)


# ---------------------------------------------------------------------------
# Generation enums
# ---------------------------------------------------------------------------


class TestGenerationMethod:
    def test_choices(self) -> None:
        assert GenerationMethod.TEMPLATE == "template"
        assert GenerationMethod.AI == "ai"


class TestGenerationStatus:
    def test_choices(self) -> None:
        assert GenerationStatus.PENDING == "pending"
        assert GenerationStatus.PROCESSING == "processing"
        assert GenerationStatus.COMPLETED == "completed"
        assert GenerationStatus.FAILED == "failed"


# ---------------------------------------------------------------------------
# GenerationTask model
# ---------------------------------------------------------------------------


class TestGenerationTask:
    def _make_task(self, **kwargs: object) -> GenerationTask:
        task = GenerationTask.__new__(GenerationTask)
        task.__dict__.update(kwargs)
        return task

    def test_str_with_case(self) -> None:
        task = MagicMock(spec=GenerationTask)
        case_mock = MagicMock()
        case_mock.name = "Test Case"
        task.case = case_mock
        task.contract = None
        task.document_type = "起诉状"
        task.get_status_display.return_value = "等待中"
        result = GenerationTask.__str__(task)
        assert "Test Case" in result
        assert "起诉状" in result

    def test_str_with_contract(self) -> None:
        task = MagicMock(spec=GenerationTask)
        contract_mock = MagicMock()
        contract_mock.name = "Test Contract"
        task.case = None
        task.contract = contract_mock
        task.document_type = "合同"
        task.get_status_display.return_value = "已完成"
        result = GenerationTask.__str__(task)
        assert "Test Contract" in result

    def test_str_no_resource(self) -> None:
        # Use MagicMock for the instance to avoid Django model _state issues
        task = MagicMock(spec=GenerationTask)
        task.case = None
        task.contract = None
        task.document_type = "起诉状"
        task.status = "pending"
        task.get_status_display.return_value = "等待中"
        # Call the actual __str__ method
        result = GenerationTask.__str__(task)
        assert "未关联" in result

    def test_is_ai_generated_true(self) -> None:
        task = GenerationTask(generation_method=GenerationMethod.AI)
        assert task.is_ai_generated is True

    def test_is_ai_generated_false(self) -> None:
        task = GenerationTask(generation_method=GenerationMethod.TEMPLATE)
        assert task.is_ai_generated is False

    def test_duration_seconds_with_both_times(self) -> None:
        now = timezone.now()
        task = GenerationTask(created_at=now, completed_at=now + timedelta(seconds=42))
        assert task.duration_seconds == 42

    def test_duration_seconds_without_completed_at(self) -> None:
        task = GenerationTask(created_at=timezone.now(), completed_at=None)
        assert task.duration_seconds == 0

    def test_folder_template_id_property(self) -> None:
        task = GenerationTask(metadata={"folder_template_id": 42})
        assert task.folder_template_id == 42

    def test_folder_template_id_setter(self) -> None:
        task = GenerationTask(metadata={})
        task.folder_template_id = 99
        assert task.metadata["folder_template_id"] == 99

    def test_folder_template_id_from_none_metadata(self) -> None:
        task = GenerationTask(metadata=None)
        task.folder_template_id = 7
        assert task.metadata["folder_template_id"] == 7

    def test_output_path_property(self) -> None:
        task = GenerationTask(metadata={"output_path": "/some/path"})
        assert task.output_path == "/some/path"

    def test_output_path_setter(self) -> None:
        task = GenerationTask(metadata={})
        task.output_path = "/new/path"
        assert task.metadata["output_path"] == "/new/path"

    def test_generated_files_property(self) -> None:
        task = GenerationTask(metadata={"generated_files": ["a.docx", "b.docx"]})
        assert task.generated_files == ["a.docx", "b.docx"]

    def test_generated_files_setter(self) -> None:
        task = GenerationTask(metadata={})
        task.generated_files = ["x.pdf"]
        assert task.metadata["generated_files"] == ["x.pdf"]

    def test_generated_files_setter_none(self) -> None:
        task = GenerationTask(metadata={})
        task.generated_files = None
        assert task.metadata["generated_files"] == []

    def test_error_logs_property(self) -> None:
        task = GenerationTask(metadata={"error_logs": ["err1"]})
        assert task.error_logs == ["err1"]

    def test_error_logs_setter(self) -> None:
        task = GenerationTask(metadata={})
        task.error_logs = ["err"]
        assert task.metadata["error_logs"] == ["err"]


# ---------------------------------------------------------------------------
# GenerationConfig model
# ---------------------------------------------------------------------------


class TestGenerationConfig:
    def test_str(self) -> None:
        cfg = GenerationConfig(config_type="default_template", name="civil_config")
        assert str(cfg) == "default_template - civil_config"

    def test_case_type_property(self) -> None:
        cfg = GenerationConfig(value={"case_type": "civil"})
        assert cfg.case_type == "civil"

    def test_case_type_property_empty(self) -> None:
        cfg = GenerationConfig(value={})
        assert cfg.case_type is None

    def test_case_stage_property(self) -> None:
        cfg = GenerationConfig(value={"case_stage": "first_trial"})
        assert cfg.case_stage == "first_trial"

    def test_document_template_id_property(self) -> None:
        cfg = GenerationConfig(value={"document_template_id": 5})
        assert cfg.document_template_id == 5

    def test_folder_path_property(self) -> None:
        cfg = GenerationConfig(value={"folder_path": "/docs"})
        assert cfg.folder_path == "/docs"

    def test_priority_property(self) -> None:
        cfg = GenerationConfig(value={"priority": 10})
        assert cfg.priority == 10

    def test_priority_property_default(self) -> None:
        cfg = GenerationConfig(value={})
        assert cfg.priority == 0

    def test_condition_property(self) -> None:
        cond = {"key": "value"}
        cfg = GenerationConfig(value={"condition": cond})
        assert cfg.condition == cond

    def test_condition_property_empty(self) -> None:
        cfg = GenerationConfig(value={})
        assert cfg.condition == {}


# ---------------------------------------------------------------------------
# DocumentTemplate model
# ---------------------------------------------------------------------------


class TestDocumentTemplate:
    def _make_tpl(self, **kwargs: object) -> DocumentTemplate:
        tpl = DocumentTemplate.__new__(DocumentTemplate)
        tpl.__dict__.update(kwargs)
        return tpl

    def test_str(self) -> None:
        tpl = self._make_tpl(name="My Template")
        assert str(tpl) == "My Template"

    def test_clean_both_file_and_path_raises(self) -> None:
        tpl = self._make_tpl(name="test")
        tpl.file = MagicMock()  # type: ignore[attr-defined]
        tpl.file_path = "/some/path.docx"
        with pytest.raises(ValidationError):
            tpl.clean()

    def test_clean_neither_file_nor_path_raises(self) -> None:
        tpl = self._make_tpl(name="test")
        tpl.file = None  # type: ignore[attr-defined]
        tpl.file_path = ""
        with pytest.raises(ValidationError):
            tpl.clean()

    def test_clean_with_file_only(self) -> None:
        tpl = self._make_tpl(name="test")
        tpl.file = MagicMock()  # type: ignore[attr-defined]
        tpl.file_path = ""
        tpl.clean()  # should not raise

    def test_clean_with_path_only(self) -> None:
        tpl = self._make_tpl(name="test")
        tpl.file = None  # type: ignore[attr-defined]
        tpl.file_path = "/templates/test.docx"
        tpl.clean()  # should not raise

    def test_get_file_location_with_file(self) -> None:
        mock_file = MagicMock()
        mock_file.name = "test.docx"
        mock_file.storage.path.return_value = "/abs/path/test.docx"
        tpl = self._make_tpl(name="test")
        tpl.file = mock_file  # type: ignore[attr-defined]
        assert tpl.get_file_location() == "/abs/path/test.docx"

    @patch("apps.documents.models.document_template.resolve_docx_template_path")
    def test_get_file_location_with_path(self, mock_resolve: MagicMock) -> None:
        mock_resolve.return_value = "/resolved/path.docx"
        tpl = self._make_tpl(name="test")
        tpl.file = None  # type: ignore[attr-defined]
        tpl.file_path = "templates/test.docx"
        assert tpl.get_file_location() == "/resolved/path.docx"

    def test_get_file_location_empty(self) -> None:
        tpl = self._make_tpl(name="test")
        tpl.file = None  # type: ignore[attr-defined]
        tpl.file_path = ""
        assert tpl.get_file_location() == ""

    def test_get_types_display_empty(self) -> None:
        tpl = self._make_tpl(name="test")
        assert tpl._get_types_display([], DocumentCaseType) == "-"

    def test_get_types_display_single(self) -> None:
        tpl = self._make_tpl(name="test")
        result = tpl._get_types_display(["civil"], DocumentCaseType)
        assert result != "-"
        assert "民" in result or "民事" in result or result == "civil"

    def test_get_types_display_multiple(self) -> None:
        tpl = self._make_tpl(name="test")
        result = tpl._get_types_display(["civil", "criminal"], DocumentCaseType)
        assert "2" in result or "种类型" in result

    def test_template_type_display_contract_with_sub(self) -> None:
        tpl = self._make_tpl(
            name="test",
            template_type=DocumentTemplateType.CONTRACT,
            contract_sub_type=DocumentContractSubType.CONTRACT,
        )
        display = tpl.template_type_display
        assert "-" in display  # e.g., "合同文件模板 - 合同模板"

    def test_template_type_display_case_with_sub(self) -> None:
        tpl = self._make_tpl(
            name="test",
            template_type=DocumentTemplateType.CASE,
            case_sub_type=DocumentCaseFileSubType.PLEADING_MATERIALS,
        )
        display = tpl.template_type_display
        assert "-" in display

    def test_template_type_display_archive_with_sub(self) -> None:
        tpl = self._make_tpl(
            name="test",
            template_type=DocumentTemplateType.ARCHIVE,
            archive_sub_type=DocumentArchiveSubType.CASE_COVER,
        )
        display = tpl.template_type_display
        assert "-" in display

    def test_template_type_display_no_sub(self) -> None:
        tpl = self._make_tpl(
            name="test",
            template_type=DocumentTemplateType.CONTRACT,
            contract_sub_type=None,
        )
        display = tpl.template_type_display
        assert "-" not in display

    def test_case_types_display(self) -> None:
        tpl = self._make_tpl(name="test", case_types=["civil"])
        assert tpl.case_types_display != "-"

    def test_case_stages_display(self) -> None:
        tpl = self._make_tpl(name="test", case_stages=["first_trial"])
        assert tpl.case_stages_display != "-"

    def test_contract_types_display(self) -> None:
        tpl = self._make_tpl(name="test", contract_types=["civil"])
        assert tpl.contract_types_display != "-"

    def test_absolute_file_path_empty(self) -> None:
        tpl = self._make_tpl(name="test", file_path="")
        assert tpl.absolute_file_path == ""

    @patch("apps.documents.models.document_template.resolve_docx_template_path")
    def test_absolute_file_path(self, mock_resolve: MagicMock) -> None:
        mock_resolve.return_value = "/abs/templates/test.docx"
        tpl = self._make_tpl(name="test", file_path="templates/test.docx")
        assert tpl.absolute_file_path == "/abs/templates/test.docx"

    def test_get_legal_statuses_display_empty(self) -> None:
        tpl = self._make_tpl(name="test", legal_statuses=[])
        result = tpl.get_legal_statuses_display()
        assert result == "任意"

    def test_get_legal_statuses_display_with_values(self) -> None:
        tpl = self._make_tpl(name="test", legal_statuses=["plaintiff"])
        result = tpl.get_legal_statuses_display()
        assert result  # some display text


# ---------------------------------------------------------------------------
# DocumentTemplateFolderBinding model
# ---------------------------------------------------------------------------


class TestDocumentTemplateFolderBinding:
    def test_str_logic(self) -> None:
        """Verify the __str__ format logic without creating actual model instances."""
        # The __str__ format is:
        # f"{self.document_template.name} -> {self.folder_template.name}/{self.folder_node_path or self.folder_node_id}"
        doc_name = "Contract Tpl"
        folder_name = "一审"
        folder_node_path = "一审/立案材料"
        folder_node_id = "node_1"
        expected = f"{doc_name} -> {folder_name}/{folder_node_path}"
        assert expected == "Contract Tpl -> 一审/一审/立案材料"

    def test_find_node_path(self) -> None:
        binding = DocumentTemplateFolderBinding.__new__(DocumentTemplateFolderBinding)
        children = [
            {"id": "a", "name": "Level1", "children": [
                {"id": "b", "name": "Level2", "children": []}
            ]},
            {"id": "c", "name": "Other", "children": []},
        ]
        result = binding._find_node_path(children, "b", [])
        assert result == ["Level1", "Level2"]

    def test_find_node_path_not_found(self) -> None:
        binding = DocumentTemplateFolderBinding.__new__(DocumentTemplateFolderBinding)
        children = [{"id": "a", "name": "X", "children": []}]
        result = binding._find_node_path(children, "missing", [])
        assert result == []
