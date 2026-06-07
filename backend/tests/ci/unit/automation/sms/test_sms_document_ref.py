"""默认文件夹模板和 SMS 文书引用服务测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from apps.documents.services.folder_template.default_templates import get_default_folder_templates
from apps.automation.services.sms.court_sms_document_reference_service import (
    CourtSMSDocumentReference,
    CourtSMSDocumentReferenceService,
)


class TestDefaultFolderTemplates:
    """默认文件夹模板测试。"""

    def test_get_default_templates_not_empty(self) -> None:
        templates = get_default_folder_templates()
        assert len(templates) > 0

    def test_templates_have_required_fields(self) -> None:
        templates = get_default_folder_templates()
        for template in templates:
            assert "name" in template
            assert "template_type" in template
            assert "structure" in template

    def test_templates_have_structure(self) -> None:
        templates = get_default_folder_templates()
        for template in templates:
            structure = template["structure"]
            assert "children" in structure
            assert isinstance(structure["children"], list)

    def test_contract_template(self) -> None:
        templates = get_default_folder_templates()
        contract = next((t for t in templates if t["template_type"] == "contract"), None)
        assert contract is not None
        assert contract["name"] == "合同文件夹"
        assert contract["is_default"] is True

    def test_civil_first_trial_template(self) -> None:
        templates = get_default_folder_templates()
        civil = next((t for t in templates if t["template_type"] == "case"), None)
        assert civil is not None
        assert "civil" in civil["case_types"]
        assert "first_trial" in civil["case_stages"]

    def test_template_ids_unique(self) -> None:
        """模板中的文件夹 ID 应该唯一。"""
        templates = get_default_folder_templates()
        for template in templates:
            ids = _collect_all_ids(template["structure"])
            assert len(ids) == len(set(ids)), f"模板 {template['name']} 中存在重复 ID"


def _collect_all_ids(structure: dict) -> list[str]:
    """递归收集所有文件夹 ID。"""
    ids: list[str] = []
    if "id" in structure:
        ids.append(structure["id"])
    for child in structure.get("children", []):
        ids.extend(_collect_all_ids(child))
    return ids


class TestCourtSMSDocumentReference:
    """CourtSMSDocumentReference 数据类测试。"""

    def test_creation(self) -> None:
        ref = CourtSMSDocumentReference(
            display_name="判决书",
            file_path="/path/to/judgment.pdf",
            source="court_document",
            court_document_id=1,
            download_status_display="已下载",
        )
        assert ref.display_name == "判决书"
        assert ref.file_path == "/path/to/judgment.pdf"
        assert ref.source == "court_document"
        assert ref.court_document_id == 1
        assert ref.download_status_display == "已下载"

    def test_defaults(self) -> None:
        ref = CourtSMSDocumentReference(
            display_name="test",
            file_path="/path",
            source="test",
        )
        assert ref.court_document_id is None
        assert ref.download_status_display is None

    def test_frozen(self) -> None:
        ref = CourtSMSDocumentReference(display_name="test", file_path="/path", source="test")
        try:
            ref.display_name = "changed"  # type: ignore
            assert False, "应抛出异常"
        except AttributeError:
            pass


class TestCourtSMSDocumentReferenceService:
    """CourtSMSDocumentReferenceService 测试。"""

    def setup_method(self) -> None:
        self.service = CourtSMSDocumentReferenceService()

    def test_has_any_references_no_task(self) -> None:
        """无 scraper_task。"""
        sms = SimpleNamespace(
            document_file_paths=None,
            scraper_task=None,
            case_log=None,
        )
        assert self.service.has_any_references(sms) is False

    def test_has_any_references_with_document_paths(self) -> None:
        """有 document_file_paths。"""
        sms = SimpleNamespace(
            document_file_paths=["/path/doc.pdf"],
            scraper_task=None,
            case_log=None,
        )
        assert self.service.has_any_references(sms) is True

    def test_has_any_references_with_task_result(self) -> None:
        """有 task result 中的文件。"""
        task = SimpleNamespace(
            documents=MagicMock(),
            result={"renamed_files": ["/path/doc.pdf"]},
        )
        task.documents.exists.return_value = False
        sms = SimpleNamespace(
            document_file_paths=None,
            scraper_task=task,
            case_log=None,
        )
        assert self.service.has_any_references(sms) is True

    def test_has_any_references_with_case_log_attachments(self) -> None:
        """有 case_log 附件。"""
        attachments = MagicMock()
        attachments.exists.return_value = True
        case_log = SimpleNamespace(attachments=attachments)
        sms = SimpleNamespace(
            document_file_paths=None,
            scraper_task=None,
            case_log=case_log,
        )
        assert self.service.has_any_references(sms) is True

    def test_collect_empty(self) -> None:
        """空短信返回空列表。"""
        sms = SimpleNamespace(
            scraper_task=None,
            document_file_paths=None,
            case_log=None,
        )
        result = self.service.collect(sms)
        assert result == []
