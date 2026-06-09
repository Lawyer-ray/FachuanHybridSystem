"""documents app Model 单元测试

覆盖 DocumentTemplate, GenerationTask, GenerationConfig, EvidenceList,
EvidenceItem, FolderTemplate, Placeholder 的 property、clean()、__str__。
"""

import pytest
from django.core.exceptions import ValidationError

from apps.cases.models import Case
from apps.contracts.models import Contract
from apps.documents.models.choices import (
    DocumentArchiveSubType,
    DocumentCaseFileSubType,
    DocumentCaseStage,
    DocumentCaseType,
    DocumentContractSubType,
    DocumentContractType,
    DocumentTemplateType,
    FolderTemplateType,
    LegalStatusMatchMode,
)
from apps.documents.models.document_template import DocumentTemplate, DocumentTemplateFolderBinding
from apps.evidence.models import EvidenceItem, EvidenceList, ListType, MergeStatus
from apps.documents.models.folder_template import FolderTemplate
from apps.documents.models.generation import GenerationConfig, GenerationMethod, GenerationStatus, GenerationTask
from apps.documents.models.placeholder import Placeholder
from apps.testing.factories import CaseFactory, ContractFactory, LawyerFactory


# ============================================================
# DocumentTemplate
# ============================================================


@pytest.mark.django_db
class TestDocumentTemplate:
    def test_str(self):
        t = DocumentTemplate.objects.create(name="起诉状模板", file_path="templates/complaint.docx")
        assert str(t) == "起诉状模板"

    def test_clean_both_file_and_path_raises(self):
        """同时提供 file 和 file_path 应抛出 ValidationError"""
        t = DocumentTemplate(name="冲突模板", file_path="templates/x.docx")
        # 模拟有 file
        from django.core.files.base import ContentFile

        t.file.save("test.docx", ContentFile(b"data"), save=False)
        with pytest.raises(ValidationError):
            t.clean()

    def test_clean_neither_file_nor_path_raises(self):
        """file 和 file_path 都为空应抛出 ValidationError"""
        t = DocumentTemplate(name="空模板", file_path="")
        t.file = None
        with pytest.raises(ValidationError):
            t.clean()

    def test_clean_file_path_only(self):
        """只提供 file_path 应通过"""
        t = DocumentTemplate(name="路径模板", file_path="templates/x.docx")
        t.file = None
        t.clean()  # 不应抛异常

    def test_template_type_display_contract_with_sub(self):
        t = DocumentTemplate.objects.create(
            name="合同模板",
            file_path="t.docx",
            template_type=DocumentTemplateType.CONTRACT,
            contract_sub_type=DocumentContractSubType.CONTRACT,
        )
        assert "合同文件模板" in t.template_type_display
        assert "合同模板" in t.template_type_display

    def test_template_type_display_case_with_sub(self):
        t = DocumentTemplate.objects.create(
            name="诉状模板",
            file_path="t.docx",
            template_type=DocumentTemplateType.CASE,
            case_sub_type=DocumentCaseFileSubType.PLEADING_MATERIALS,
        )
        assert "案件文件模板" in t.template_type_display
        assert "诉状材料" in t.template_type_display

    def test_template_type_display_archive_with_sub(self):
        t = DocumentTemplate.objects.create(
            name="归档模板",
            file_path="t.docx",
            template_type=DocumentTemplateType.ARCHIVE,
            archive_sub_type=DocumentArchiveSubType.CASE_COVER,
        )
        assert "归档文件模板" in t.template_type_display
        assert "案卷封面" in t.template_type_display

    def test_template_type_display_no_sub(self):
        t = DocumentTemplate.objects.create(
            name="基础模板",
            file_path="t.docx",
            template_type=DocumentTemplateType.CONTRACT,
        )
        assert t.template_type_display == "合同文件模板"

    def test_case_types_display_empty(self):
        t = DocumentTemplate.objects.create(name="t", file_path="t.docx", case_types=[])
        assert t.case_types_display == "-"

    def test_case_types_display_single(self):
        t = DocumentTemplate.objects.create(name="t", file_path="t.docx", case_types=["civil"])
        assert t.case_types_display == "民事"

    def test_case_types_display_multiple(self):
        t = DocumentTemplate.objects.create(name="t", file_path="t.docx", case_types=["civil", "criminal"])
        assert t.case_types_display == "2种类型"

    def test_case_stages_display_empty(self):
        t = DocumentTemplate.objects.create(name="t", file_path="t.docx", case_stages=[])
        assert t.case_stages_display == "-"

    def test_case_stages_display_single(self):
        t = DocumentTemplate.objects.create(name="t", file_path="t.docx", case_stages=["first_trial"])
        assert t.case_stages_display == "一审"

    def test_contract_types_display_empty(self):
        t = DocumentTemplate.objects.create(name="t", file_path="t.docx", contract_types=[])
        assert t.contract_types_display == "-"

    def test_contract_types_display_single(self):
        t = DocumentTemplate.objects.create(name="t", file_path="t.docx", contract_types=["civil"])
        assert t.contract_types_display == "民商事"

    def test_get_legal_statuses_display_empty(self):
        t = DocumentTemplate.objects.create(name="t", file_path="t.docx", legal_statuses=[])
        assert t.get_legal_statuses_display() == "任意"

    def test_absolute_file_path_empty(self):
        t = DocumentTemplate.objects.create(name="t", file_path="")
        assert t.absolute_file_path == ""

    def test_absolute_file_path_with_value(self):
        t = DocumentTemplate.objects.create(name="t", file_path="templates/test.docx")
        path = t.absolute_file_path
        assert path.endswith("test.docx")

    def test_get_file_location_no_file(self):
        t = DocumentTemplate.objects.create(name="t", file_path="")
        assert t.get_file_location() == ""


# ============================================================
# GenerationTask
# ============================================================


@pytest.mark.django_db
class TestGenerationTask:
    def test_str_with_case(self):
        case = CaseFactory(name="测试案件")
        task = GenerationTask.objects.create(
            case=case, document_type="起诉状", status=GenerationStatus.PENDING
        )
        result = str(task)
        assert "测试案件" in result
        assert "起诉状" in result

    def test_str_with_contract(self):
        contract = ContractFactory(name="测试合同")
        task = GenerationTask.objects.create(
            contract=contract, document_type="合同", status=GenerationStatus.COMPLETED
        )
        result = str(task)
        assert "测试合同" in result

    def test_str_unlinked(self):
        task = GenerationTask.objects.create(document_type="通用", status=GenerationStatus.FAILED)
        assert "未关联" in str(task)

    def test_is_ai_generated_true(self):
        task = GenerationTask(generation_method=GenerationMethod.AI)
        assert task.is_ai_generated is True

    def test_is_ai_generated_false(self):
        task = GenerationTask(generation_method=GenerationMethod.TEMPLATE)
        assert task.is_ai_generated is False

    def test_duration_seconds_no_completed_at(self):
        task = GenerationTask()
        assert task.duration_seconds == 0

    def test_duration_seconds_with_times(self):
        from django.utils import timezone
        from datetime import timedelta

        now = timezone.now()
        task = GenerationTask(created_at=now, completed_at=now + timedelta(seconds=60))
        assert task.duration_seconds == 60

    def test_folder_template_id_property(self):
        task = GenerationTask(metadata={"folder_template_id": 42})
        assert task.folder_template_id == 42

    def test_folder_template_id_setter(self):
        task = GenerationTask(metadata={})
        task.folder_template_id = 99
        assert task.metadata["folder_template_id"] == 99

    def test_output_path_property(self):
        task = GenerationTask(metadata={"output_path": "/tmp/output"})
        assert task.output_path == "/tmp/output"

    def test_output_path_setter(self):
        task = GenerationTask(metadata={})
        task.output_path = "/new/path"
        assert task.metadata["output_path"] == "/new/path"

    def test_generated_files_property(self):
        task = GenerationTask(metadata={"generated_files": ["a.docx", "b.docx"]})
        assert task.generated_files == ["a.docx", "b.docx"]

    def test_generated_files_setter(self):
        task = GenerationTask(metadata={})
        task.generated_files = ["x.docx"]
        assert task.metadata["generated_files"] == ["x.docx"]

    def test_error_logs_property(self):
        task = GenerationTask(metadata={"error_logs": ["err1"]})
        assert task.error_logs == ["err1"]

    def test_error_logs_setter(self):
        task = GenerationTask(metadata={})
        task.error_logs = ["err2"]
        assert task.metadata["error_logs"] == ["err2"]

    def test_folder_template_id_none_metadata(self):
        task = GenerationTask(metadata=None)
        assert task.folder_template_id is None


# ============================================================
# GenerationConfig
# ============================================================


@pytest.mark.django_db
class TestGenerationConfig:
    def test_str(self):
        cfg = GenerationConfig.objects.create(name="默认配置", config_type="default", value={})
        assert str(cfg) == "default - 默认配置"

    def test_case_type_property(self):
        cfg = GenerationConfig(value={"case_type": "civil"})
        assert cfg.case_type == "civil"

    def test_case_stage_property(self):
        cfg = GenerationConfig(value={"case_stage": "first_trial"})
        assert cfg.case_stage == "first_trial"

    def test_document_template_id_property(self):
        cfg = GenerationConfig(value={"document_template_id": 5})
        assert cfg.document_template_id == 5

    def test_folder_path_property(self):
        cfg = GenerationConfig(value={"folder_path": "/cases/001"})
        assert cfg.folder_path == "/cases/001"

    def test_priority_property(self):
        cfg = GenerationConfig(value={"priority": 10})
        assert cfg.priority == 10

    def test_priority_default_zero(self):
        cfg = GenerationConfig(value={})
        assert cfg.priority == 0

    def test_condition_property(self):
        cond = {"field": "case_type", "op": "eq", "value": "civil"}
        cfg = GenerationConfig(value={"condition": cond})
        assert cfg.condition == cond

    def test_condition_default_empty(self):
        cfg = GenerationConfig(value={})
        assert cfg.condition == {}

    def test_case_type_none_value(self):
        cfg = GenerationConfig(value=None)
        assert cfg.case_type is None


# ============================================================
# EvidenceList & EvidenceItem
# ============================================================


@pytest.mark.django_db
class TestEvidenceList:
    def test_str(self):
        case = CaseFactory(name="证据案件")
        el = EvidenceList.objects.create(case=case, title="证据清单一", list_type=ListType.LIST_1)
        assert "证据案件" in str(el)
        assert "证据清单一" in str(el)

    def test_end_page_zero_total(self):
        el = EvidenceList(total_pages=0)
        # start_page 委托给 service，这里只测 end_page 分支
        assert el.end_page == el.start_page

    def test_page_range_display_zero_total(self):
        el = EvidenceList(total_pages=0)
        assert el.page_range_display == ""

    def test_merge_status_choices(self):
        assert MergeStatus.PENDING.value == "pending"
        assert MergeStatus.COMPLETED.value == "completed"
        assert MergeStatus.FAILED.value == "failed"


@pytest.mark.django_db
class TestEvidenceItem:
    def test_str(self):
        case = CaseFactory(name="证据案件")
        el = EvidenceList.objects.create(case=case, title="清单", list_type=ListType.LIST_1)
        item = EvidenceItem.objects.create(evidence_list=el, order=1, name="合同原件", purpose="证明合同关系")
        assert str(item) == "1. 合同原件"

    def test_page_range_display_none(self):
        item = EvidenceItem(page_start=None, page_end=None)
        assert item.page_range_display == "-"

    def test_page_range_display_same(self):
        item = EvidenceItem(page_start=5, page_end=5)
        assert item.page_range_display == "5"

    def test_page_range_display_range(self):
        item = EvidenceItem(page_start=1, page_end=10)
        assert item.page_range_display == "1-10"

    def test_file_size_display_zero(self):
        item = EvidenceItem(file_size=0)
        assert item.file_size_display == "-"

    def test_file_size_display_bytes(self):
        item = EvidenceItem(file_size=512)
        assert item.file_size_display == "512 B"

    def test_file_size_display_kb(self):
        item = EvidenceItem(file_size=2048)
        assert item.file_size_display == "2.0 KB"

    def test_file_size_display_mb(self):
        item = EvidenceItem(file_size=2 * 1024 * 1024)
        assert item.file_size_display == "2.0 MB"


# ============================================================
# FolderTemplate
# ============================================================


@pytest.mark.django_db
class TestFolderTemplate:
    def test_str(self):
        ft = FolderTemplate.objects.create(
            name="一审案件模板",
            template_type=FolderTemplateType.CASE,
            case_types=["civil"],
            structure={},
        )
        result = str(ft)
        assert "一审案件模板" in result
        assert "案件文件夹模板" in result

    def test_template_type_display(self):
        ft = FolderTemplate(template_type=FolderTemplateType.CASE)
        assert ft.template_type_display == "案件文件夹模板"

    def test_case_types_display_empty(self):
        ft = FolderTemplate(case_types=[])
        assert ft.case_types_display == "-"

    def test_case_types_display_single(self):
        ft = FolderTemplate(case_types=["civil"])
        assert "民事" in ft.case_types_display

    def test_case_stages_display_empty(self):
        ft = FolderTemplate(case_stages=[])
        assert ft.case_stages_display == "-"

    def test_contract_types_display_empty(self):
        ft = FolderTemplate(contract_types=[])
        assert ft.contract_types_display == "-"

    def test_case_type_property(self):
        ft = FolderTemplate(case_types=["civil", "criminal"])
        assert ft.case_type == "civil"

    def test_case_type_property_empty(self):
        ft = FolderTemplate(case_types=[])
        assert ft.case_type is None

    def test_case_stage_property(self):
        ft = FolderTemplate(case_stages=["first_trial"])
        assert ft.case_stage == "first_trial"

    def test_case_stage_property_empty(self):
        ft = FolderTemplate(case_stages=[])
        assert ft.case_stage is None

    def test_legal_statuses_display_empty(self):
        ft = FolderTemplate(legal_statuses=[])
        assert ft.legal_statuses_display == "-"

    def test_get_legal_statuses_display_empty(self):
        ft = FolderTemplate(legal_statuses=[])
        assert ft.get_legal_statuses_display() == ""


# ============================================================
# Placeholder
# ============================================================


@pytest.mark.django_db
class TestPlaceholder:
    def test_str(self):
        p = Placeholder.objects.create(key="case_name", display_name="案件名称")
        assert str(p) == "案件名称 (case_name)"

    def test_data_path_default(self):
        p = Placeholder(key="x", display_name="X")
        assert p.data_path == ""

    def test_data_path_setter(self):
        p = Placeholder(key="x", display_name="X")
        p.data_path = "case.name"
        assert p.data_path == "case.name"

    def test_category_default(self):
        p = Placeholder(key="x", display_name="X")
        assert p.category == ""

    def test_category_setter(self):
        p = Placeholder(key="x", display_name="X")
        p.category = "case"
        assert p.category == "case"


# ============================================================
# DocumentTemplateFolderBinding
# ============================================================


@pytest.mark.django_db
class TestDocumentTemplateFolderBinding:
    def test_str(self):
        dt = DocumentTemplate.objects.create(name="起诉状", file_path="t.docx")
        ft = FolderTemplate.objects.create(
            name="一审模板",
            template_type=FolderTemplateType.CASE,
            structure={"children": [{"id": "n1", "name": "立案材料"}]},
        )
        binding = DocumentTemplateFolderBinding.objects.create(
            document_template=dt,
            folder_template=ft,
            folder_node_id="n1",
        )
        result = str(binding)
        assert "起诉状" in result
        assert "一审模板" in result
