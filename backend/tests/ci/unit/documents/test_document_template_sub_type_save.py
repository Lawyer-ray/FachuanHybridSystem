"""文书模板子类型保存回归测试。

背景（2026-10-12）：admin 保存任意 DocumentTemplate 都会炸
``null value in column "contract_sub_type" ... violates not-null constraint``——
prepare_save_data / validate_template_type 对「与 template_type 不匹配」的子类型
写 Python None，而三列自 documents.0016 起为 NOT NULL。修复后非匹配子类型必须归一为空串。
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.documents.admin.document_template_admin import DocumentTemplateForm
from apps.documents.models import DocumentTemplate
from apps.documents.models.choices import DocumentCaseFileSubType, DocumentTemplateType
from apps.documents.services.template.document_template.admin_service import DocumentTemplateAdminService


class TestValidateTemplateTypeNormalizesToEmpty:
    """非本类型子类型必须返回空串，不得返回 None。"""

    def setup_method(self) -> None:
        self.svc = DocumentTemplateAdminService()

    def test_case_template_clears_contract_and_archive(self) -> None:
        result = self.svc.validate_template_type(
            template_type=DocumentTemplateType.CASE,
            contract_sub_type="",
            case_sub_type=DocumentCaseFileSubType.POWER_OF_ATTORNEY_MATERIALS,
            is_editing=True,
            original_template_type=DocumentTemplateType.CASE,
        )
        assert result["is_valid"] is True
        assert result["contract_sub_type"] == ""
        assert result["archive_sub_type"] == ""
        assert result["case_sub_type"] == DocumentCaseFileSubType.POWER_OF_ATTORNEY_MATERIALS.value

    def test_contract_template_clears_case_and_archive(self) -> None:
        result = self.svc.validate_template_type(
            template_type=DocumentTemplateType.CONTRACT,
            contract_sub_type="contract",
            case_sub_type="",
            archive_sub_type="case_cover",
        )
        assert result["is_valid"] is True
        assert result["case_sub_type"] == ""
        assert result["archive_sub_type"] == ""
        assert result["contract_sub_type"] == "contract"

    def test_archive_template_clears_contract_and_case(self) -> None:
        result = self.svc.validate_template_type(
            template_type=DocumentTemplateType.ARCHIVE,
            contract_sub_type="",
            case_sub_type="",
            archive_sub_type="case_cover",
        )
        assert result["is_valid"] is True
        assert result["contract_sub_type"] == ""
        assert result["case_sub_type"] == ""


class TestPrepareSaveDataNormalizesToEmpty:
    def test_case_template_save_data(self) -> None:
        data = self.svc_save(template_type=DocumentTemplateType.CASE)
        assert data["contract_sub_type"] == ""
        assert data["archive_sub_type"] == ""
        assert data["case_sub_type"] == DocumentCaseFileSubType.POWER_OF_ATTORNEY_MATERIALS.value

    def test_contract_template_save_data(self) -> None:
        data = self.svc_save(template_type=DocumentTemplateType.CONTRACT, contract_sub_type="contract")
        assert data["case_sub_type"] == ""
        assert data["archive_sub_type"] == ""

    def svc_save(self, template_type: str, contract_sub_type: str = "") -> dict[str, Any]:
        svc = DocumentTemplateAdminService()
        return svc.prepare_save_data(
            template_type=template_type,
            contract_sub_type=contract_sub_type,
            case_sub_type=DocumentCaseFileSubType.POWER_OF_ATTORNEY_MATERIALS.value,
            archive_sub_type="case_cover",
            contract_types_field=[],
            case_types_field=["all"],
            case_stage_field="first_trial",
            file=None,
            file_path="2-案件材料/4-通用材料/1-授权委托材料/法定代表人身份证明书.docx",
        )


@pytest.fixture
def case_template(db: Any) -> DocumentTemplate:
    """复刻事故模板 #4：案件类、授权委托材料、file_path 引用模板库文件。"""
    return DocumentTemplate.objects.create(
        name="法定代表人身份证明书",
        template_type=DocumentTemplateType.CASE,
        case_sub_type=DocumentCaseFileSubType.POWER_OF_ATTORNEY_MATERIALS,
        file_path="2-案件材料/4-通用材料/1-授权委托材料/法定代表人身份证明书.docx",
        case_types=["all"],
        case_stages=["first_trial"],
    )


@pytest.mark.django_db
class TestAdminFormSaveCaseTemplate:
    """端到端回归：admin 表单保存案件类模板不得写 NULL 子类型。"""

    def _post_data(self, template: DocumentTemplate) -> dict[str, Any]:
        return {
            "name": template.name,
            "template_type": DocumentTemplateType.CASE.value,
            "contract_sub_type": "",
            "case_sub_type": DocumentCaseFileSubType.POWER_OF_ATTORNEY_MATERIALS.value,
            "archive_sub_type": "",
            "case_types_field": ["all"],
            "case_stage_field": "first_trial",
            "legal_status_match_mode": "any",
            "existing_file": "",
            # 与原值相同 → validate_file_sources 走 skip_file_validation 分支
            "file_path": template.file_path,
            "is_active": "on",
        }

    def test_save_case_template_keeps_contract_sub_type_empty(self, case_template: DocumentTemplate) -> None:
        form = DocumentTemplateForm(data=self._post_data(case_template), instance=case_template)
        assert form.is_valid(), form.errors
        form.save()

        case_template.refresh_from_db()
        assert case_template.contract_sub_type == ""
        assert case_template.archive_sub_type == ""
        assert case_template.case_sub_type == DocumentCaseFileSubType.POWER_OF_ATTORNEY_MATERIALS.value
        assert case_template.file_path == "2-案件材料/4-通用材料/1-授权委托材料/法定代表人身份证明书.docx"
