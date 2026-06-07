"""其他 Admin 测试 - 未分类 app 的 admin 测试"""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory

# 导入各 app 的 admin
from apps.chat_records.admin.chat_record_admin import (
    ChatRecordProjectAdmin,
    ChatRecordScreenshotAdmin,
    ChatRecordExportTaskAdmin,
    ChatRecordRecordingAdmin,
)
from apps.doc_convert.admin.doc_convert_tool_admin import DocConvertToolAdmin
from apps.doc_converter.admin.doc_converter_admin import DocConverterJobAdmin, DocConverterToolAdmin
from apps.document_recognition.admin.document_recognition_admin import (
    DocumentRecognitionToolAdmin,
    DocumentRecognitionTaskAdmin,
)
from apps.documents.admin.document_template_admin import DocumentTemplateAdmin
from apps.documents.admin.external_template_admin import ExternalTemplateAdmin
from apps.documents.admin.folder_binding_admin import DocumentTemplateFolderBindingAdmin
from apps.documents.admin.folder_template_admin import FolderTemplateAdmin
from apps.documents.admin.proxy_matter_rule_admin import ProxyMatterRuleAdmin
from apps.enterprise_data.admin.mcp_workbench_admin import McpWorkbenchAdmin
from apps.evidence_sorting.admin.evidence_sorting_admin import EvidenceSortingAdmin
from apps.express_query.admin.express_query_task_admin import ExpressQueryToolAdmin, ExpressQueryTaskAdmin
from apps.fee_notice.admin.fee_notice_admin import FeeNoticeAdmin
from apps.image_rotation.admin.image_rotation_admin import ImageRotationAdmin
from apps.invoice_recognition.admin.invoice_recognition_admin import InvoiceRecognitionTaskAdmin
from apps.legal_research.admin.task_admin import LegalResearchTaskAdmin
from apps.legal_research.admin.result_admin import LegalResearchResultAdmin
from apps.legal_solution.admin.task_admin import SolutionTaskAdmin
from apps.preservation_date.admin.preservation_date_admin import PreservationDateAdmin
from apps.contract_review.admin.format_normalize_admin import FormatNormalizeAdmin
from apps.contract_review.admin.review_task_admin import ReviewTaskAdmin

# 导入模型
from apps.chat_records.models import ChatRecordProject, ChatRecordScreenshot, ChatRecordExportTask, ChatRecordRecording
from apps.doc_convert.models import DocConvertTool
from apps.doc_converter.models import DocConverterJob, DocConverterTool
from apps.document_recognition.models import DocumentRecognitionTool, DocumentRecognitionTask
from apps.documents.models import (
    DocumentTemplate,
    ExternalTemplate,
    DocumentTemplateFolderBinding,
    FolderTemplate,
    ProxyMatterRule,
)
from apps.enterprise_data.models import McpWorkbench
from apps.evidence_sorting.models import EvidenceSorting
from apps.express_query.models import ExpressQueryTool, ExpressQueryTask
from apps.fee_notice.models import FeeNoticeTool
from apps.image_rotation.models import ImageRotationTool
from apps.invoice_recognition.models import InvoiceRecognitionTask
from apps.legal_research.models import LegalResearchResult, LegalResearchTask
from apps.legal_solution.models import SolutionTask
from apps.preservation_date.models import PreservationDateTool
from apps.contract_review.models import FormatNormalize, ReviewTask

User = get_user_model()


def _make_request(path: str = "/admin/") -> Any:
    factory = RequestFactory()
    request = factory.get(path)
    request.user = User(is_superuser=True, is_staff=True)
    return request


@pytest.mark.django_db
class TestChatRecordAdmins:
    """聊天记录 Admin 测试"""

    def test_project_admin_list_display(self) -> None:
        """ChatRecordProjectAdmin list_display"""
        admin_obj = ChatRecordProjectAdmin(ChatRecordProject, AdminSite())
        assert "id" in admin_obj.list_display
        assert "name" in admin_obj.list_display

    def test_screenshot_admin_list_display(self) -> None:
        """ChatRecordScreenshotAdmin list_display"""
        admin_obj = ChatRecordScreenshotAdmin(ChatRecordScreenshot, AdminSite())
        assert "id" in admin_obj.list_display

    def test_export_task_admin_list_display(self) -> None:
        """ChatRecordExportTaskAdmin list_display"""
        admin_obj = ChatRecordExportTaskAdmin(ChatRecordExportTask, AdminSite())
        assert "id" in admin_obj.list_display

    def test_recording_admin_list_display(self) -> None:
        """ChatRecordRecordingAdmin list_display"""
        admin_obj = ChatRecordRecordingAdmin(ChatRecordRecording, AdminSite())
        assert "id" in admin_obj.list_display


@pytest.mark.django_db
class TestDocConvertAdmins:
    """文档转换 Admin 测试"""

    def test_doc_convert_tool_admin_list_display(self) -> None:
        """DocConvertToolAdmin list_display"""
        admin_obj = DocConvertToolAdmin(DocConvertTool, AdminSite())
        # Tool models typically use __str__ as list_display
        assert len(admin_obj.list_display) > 0

    def test_doc_converter_job_admin_list_display(self) -> None:
        """DocConverterJobAdmin list_display"""
        admin_obj = DocConverterJobAdmin(DocConverterJob, AdminSite())
        assert "id" in admin_obj.list_display

    def test_doc_converter_tool_admin_list_display(self) -> None:
        """DocConverterToolAdmin list_display"""
        admin_obj = DocConverterToolAdmin(DocConverterTool, AdminSite())
        assert len(admin_obj.list_display) > 0


@pytest.mark.django_db
class TestDocumentRecognitionAdmins:
    """文档识别 Admin 测试"""

    def test_tool_admin_list_display(self) -> None:
        """DocumentRecognitionToolAdmin list_display"""
        admin_obj = DocumentRecognitionToolAdmin(DocumentRecognitionTool, AdminSite())
        assert len(admin_obj.list_display) > 0

    def test_task_admin_list_display(self) -> None:
        """DocumentRecognitionTaskAdmin list_display"""
        admin_obj = DocumentRecognitionTaskAdmin(DocumentRecognitionTask, AdminSite())
        assert "id" in admin_obj.list_display


@pytest.mark.django_db
class TestDocumentsAdmins:
    """文书 Admin 测试"""

    def test_document_template_admin_list_display(self) -> None:
        """DocumentTemplateAdmin list_display"""
        admin_obj = DocumentTemplateAdmin(DocumentTemplate, AdminSite())
        assert "id" in admin_obj.list_display

    def test_external_template_admin_list_display(self) -> None:
        """ExternalTemplateAdmin list_display"""
        admin_obj = ExternalTemplateAdmin(ExternalTemplate, AdminSite())
        assert "name" in admin_obj.list_display

    def test_folder_binding_admin_list_display(self) -> None:
        """DocumentTemplateFolderBindingAdmin list_display"""
        admin_obj = DocumentTemplateFolderBindingAdmin(DocumentTemplateFolderBinding, AdminSite())
        assert "document_template" in admin_obj.list_display

    def test_folder_template_admin_list_display(self) -> None:
        """FolderTemplateAdmin list_display"""
        admin_obj = FolderTemplateAdmin(FolderTemplate, AdminSite())
        assert "id" in admin_obj.list_display

    def test_proxy_matter_rule_admin_list_display(self) -> None:
        """ProxyMatterRuleAdmin list_display"""
        admin_obj = ProxyMatterRuleAdmin(ProxyMatterRule, AdminSite())
        assert "id" in admin_obj.list_display


@pytest.mark.django_db
class TestEnterpriseDataAdmins:
    """企业数据 Admin 测试"""

    def test_mcp_workbench_admin_list_display(self) -> None:
        """McpWorkbenchAdmin list_display"""
        admin_obj = McpWorkbenchAdmin(McpWorkbench, AdminSite())
        assert len(admin_obj.list_display) > 0


@pytest.mark.django_db
class TestEvidenceSortingAdmin:
    """证据排序 Admin 测试"""

    def test_list_display(self) -> None:
        """EvidenceSortingAdmin list_display"""
        admin_obj = EvidenceSortingAdmin(EvidenceSorting, AdminSite())
        assert len(admin_obj.list_display) > 0


@pytest.mark.django_db
class TestExpressQueryAdmins:
    """快递查询 Admin 测试"""

    def test_tool_admin_list_display(self) -> None:
        """ExpressQueryToolAdmin list_display"""
        admin_obj = ExpressQueryToolAdmin(ExpressQueryTool, AdminSite())
        assert len(admin_obj.list_display) > 0

    def test_task_admin_list_display(self) -> None:
        """ExpressQueryTaskAdmin list_display"""
        admin_obj = ExpressQueryTaskAdmin(ExpressQueryTask, AdminSite())
        assert "id" in admin_obj.list_display


@pytest.mark.django_db
class TestFeeNoticeAdmin:
    """收费通知 Admin 测试"""

    def test_list_display(self) -> None:
        """FeeNoticeAdmin list_display"""
        admin_obj = FeeNoticeAdmin(FeeNoticeTool, AdminSite())
        assert len(admin_obj.list_display) > 0


@pytest.mark.django_db
class TestImageRotationAdmin:
    """图片旋转 Admin 测试"""

    def test_list_display(self) -> None:
        """ImageRotationAdmin list_display"""
        admin_obj = ImageRotationAdmin(ImageRotationTool, AdminSite())
        assert len(admin_obj.list_display) > 0


@pytest.mark.django_db
class TestInvoiceRecognitionAdmin:
    """发票识别 Admin 测试"""

    def test_list_display(self) -> None:
        """InvoiceRecognitionTaskAdmin list_display"""
        admin_obj = InvoiceRecognitionTaskAdmin(InvoiceRecognitionTask, AdminSite())
        assert "name" in admin_obj.list_display


@pytest.mark.django_db
class TestLegalResearchAdmins:
    """法律检索 Admin 测试"""

    def test_task_admin_list_display(self) -> None:
        """LegalResearchTaskAdmin list_display"""
        admin_obj = LegalResearchTaskAdmin(LegalResearchTask, AdminSite())
        assert "id" in admin_obj.list_display

    def test_result_admin_list_display(self) -> None:
        """LegalResearchResultAdmin list_display"""
        admin_obj = LegalResearchResultAdmin(LegalResearchResult, AdminSite())
        assert "id" in admin_obj.list_display


@pytest.mark.django_db
class TestLegalSolutionAdmin:
    """法律解决方案 Admin 测试"""

    def test_list_display(self) -> None:
        """SolutionTaskAdmin list_display"""
        admin_obj = SolutionTaskAdmin(SolutionTask, AdminSite())
        assert "id" in admin_obj.list_display


@pytest.mark.django_db
class TestPreservationDateAdmin:
    """保全日期 Admin 测试"""

    def test_list_display(self) -> None:
        """PreservationDateAdmin list_display"""
        admin_obj = PreservationDateAdmin(PreservationDateTool, AdminSite())
        assert len(admin_obj.list_display) > 0


@pytest.mark.django_db
class TestContractReviewAdmins:
    """合同审查 Admin 测试"""

    def test_format_normalize_admin_list_display(self) -> None:
        """FormatNormalizeAdmin list_display"""
        admin_obj = FormatNormalizeAdmin(FormatNormalize, AdminSite())
        assert "contract_title" in admin_obj.list_display

    def test_review_task_admin_list_display(self) -> None:
        """ReviewTaskAdmin list_display"""
        admin_obj = ReviewTaskAdmin(ReviewTask, AdminSite())
        assert "contract_title" in admin_obj.list_display
