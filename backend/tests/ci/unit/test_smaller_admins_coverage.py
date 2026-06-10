"""Smaller Admin Apps 测试 - workbench, oa_filing, message_hub, contracts, enterprise_data,
fee_notice, pdf_splitting, chat_records, express_query, finance, image_rotation,
invoice_recognition, doc_converter, organization"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory

User = get_user_model()


def _make_request(method="GET", path="/admin/"):
    factory = RequestFactory()
    if method == "GET":
        request = factory.get(path)
    else:
        request = factory.post(path)
    request.user = User(is_superuser=True, is_staff=True)
    return request


# ==============================================================================
# workbench
# ==============================================================================

@pytest.mark.django_db
class TestWorkbenchAdmin:
    def test_session_admin_list_display(self):
        from apps.workbench.admin import WorkbenchSessionAdmin
        from apps.workbench.models import WorkbenchSession

        admin_obj = WorkbenchSessionAdmin(WorkbenchSession, AdminSite())
        assert "session_id" in admin_obj.list_display
        assert "title" in admin_obj.list_display
        assert "status" in admin_obj.list_display
        assert "created_at" in admin_obj.list_display

    def test_session_admin_list_filter(self):
        from apps.workbench.admin import WorkbenchSessionAdmin
        from apps.workbench.models import WorkbenchSession

        admin_obj = WorkbenchSessionAdmin(WorkbenchSession, AdminSite())
        assert "status" in admin_obj.list_filter

    def test_session_admin_search_fields(self):
        from apps.workbench.admin import WorkbenchSessionAdmin
        from apps.workbench.models import WorkbenchSession

        admin_obj = WorkbenchSessionAdmin(WorkbenchSession, AdminSite())
        assert "title" in admin_obj.search_fields
        assert "session_id" in admin_obj.search_fields

    def test_message_admin_list_display(self):
        from apps.workbench.admin import WorkbenchMessageAdmin
        from apps.workbench.models import WorkbenchMessage

        admin_obj = WorkbenchMessageAdmin(WorkbenchMessage, AdminSite())
        assert "id" in admin_obj.list_display
        assert "session" in admin_obj.list_display
        assert "role" in admin_obj.list_display

    def test_batch_job_admin_list_display(self):
        from apps.workbench.admin import BatchJobAdmin
        from apps.workbench.models import BatchJob

        admin_obj = BatchJobAdmin(BatchJob, AdminSite())
        assert "id" in admin_obj.list_display
        assert "job_type" in admin_obj.list_display
        assert "status" in admin_obj.list_display
        assert "progress" in admin_obj.list_display

    def test_batch_job_item_admin_list_display(self):
        from apps.workbench.admin import BatchJobItemAdmin
        from apps.workbench.models import BatchJobItem

        admin_obj = BatchJobItemAdmin(BatchJobItem, AdminSite())
        assert "id" in admin_obj.list_display
        assert "file_name" in admin_obj.list_display
        assert "status" in admin_obj.list_display


# ==============================================================================
# oa_filing
# ==============================================================================

@pytest.mark.django_db
class TestOaFilingAdmin:
    def test_filing_session_admin_attributes(self):
        from apps.oa_filing.admin.filing_session_admin import FilingSessionAdmin
        from apps.oa_filing.models import FilingSession

        admin_obj = FilingSessionAdmin(FilingSession, AdminSite())
        assert "id" in admin_obj.list_display
        assert "case" in admin_obj.list_display
        assert "status" in admin_obj.list_display
        assert "created_at" in admin_obj.list_display


# ==============================================================================
# message_hub
# ==============================================================================

@pytest.mark.django_db
class TestMessageHubAdmin:
    def test_inbox_message_admin_list_display(self):
        from apps.message_hub.admin import InboxMessageAdmin
        from apps.message_hub.models import InboxMessage

        admin_obj = InboxMessageAdmin(InboxMessage, AdminSite())
        assert len(admin_obj.list_display) > 0

    def test_message_source_admin_list_display(self):
        from apps.message_hub.admin import MessageSourceAdmin
        from apps.message_hub.models import MessageSource

        admin_obj = MessageSourceAdmin(MessageSource, AdminSite())
        assert "id" in admin_obj.list_display


# ==============================================================================
# contracts
# ==============================================================================

@pytest.mark.django_db
class TestContractsAdmin:
    def test_contract_admin_attributes(self):
        from apps.contracts.admin import ContractAdmin
        from apps.contracts.models import Contract

        admin_obj = ContractAdmin(Contract, AdminSite())
        assert "id" in admin_obj.list_display
        assert len(admin_obj.list_display) > 3

    def test_contract_admin_search_fields(self):
        from apps.contracts.admin import ContractAdmin
        from apps.contracts.models import Contract

        admin_obj = ContractAdmin(Contract, AdminSite())
        assert len(admin_obj.search_fields) > 0

    def test_supplementary_agreement_admin(self):
        from apps.contracts.admin import SupplementaryAgreementAdmin
        from apps.contracts.models import SupplementaryAgreement

        admin_obj = SupplementaryAgreementAdmin(SupplementaryAgreement, AdminSite())
        assert admin_obj.list_display is not None

    def test_archive_classification_rule_admin(self):
        from apps.contracts.admin import ArchiveClassificationRuleAdmin
        from apps.contracts.models import ArchiveClassificationRule

        admin_obj = ArchiveClassificationRuleAdmin(ArchiveClassificationRule, AdminSite())
        assert admin_obj.list_display is not None


# ==============================================================================
# enterprise_data
# ==============================================================================

@pytest.mark.django_db
class TestEnterpriseDataAdmin:
    def test_mcp_workbench_admin_list_display(self):
        from apps.enterprise_data.admin import McpWorkbenchAdmin
        from apps.enterprise_data.models import McpWorkbench

        admin_obj = McpWorkbenchAdmin(McpWorkbench, AdminSite())
        assert admin_obj.list_display is not None


# ==============================================================================
# fee_notice
# ==============================================================================

@pytest.mark.django_db
class TestFeeNoticeAdmin:
    def test_fee_notice_admin_list_display(self):
        from apps.fee_notice.admin import FeeNoticeAdmin
        from apps.fee_notice.models import FeeNoticeTool

        admin_obj = FeeNoticeAdmin(FeeNoticeTool, AdminSite())
        assert admin_obj.list_display is not None


# ==============================================================================
# pdf_splitting
# ==============================================================================

@pytest.mark.django_db
class TestPdfSplittingAdmin:
    def test_pdf_splitting_tool_admin(self):
        from apps.pdf_splitting.admin import PdfSplittingToolAdmin
        from apps.pdf_splitting.models import PdfSplittingTool

        admin_obj = PdfSplittingToolAdmin(PdfSplittingTool, AdminSite())
        assert admin_obj.list_display is not None

    def test_pdf_split_job_admin(self):
        from apps.pdf_splitting.admin import PdfSplitJobAdmin
        from apps.pdf_splitting.models import PdfSplitJob

        admin_obj = PdfSplitJobAdmin(PdfSplitJob, AdminSite())
        assert admin_obj.list_display is not None


# ==============================================================================
# chat_records
# ==============================================================================

@pytest.mark.django_db
class TestChatRecordsAdmin:
    def test_project_admin(self):
        from apps.chat_records.admin import ChatRecordProjectAdmin
        from apps.chat_records.models import ChatRecordProject

        admin_obj = ChatRecordProjectAdmin(ChatRecordProject, AdminSite())
        assert "id" in admin_obj.list_display
        assert "name" in admin_obj.list_display

    def test_screenshot_admin(self):
        from apps.chat_records.admin import ChatRecordScreenshotAdmin
        from apps.chat_records.models import ChatRecordScreenshot

        admin_obj = ChatRecordScreenshotAdmin(ChatRecordScreenshot, AdminSite())
        assert "id" in admin_obj.list_display

    def test_export_task_admin(self):
        from apps.chat_records.admin import ChatRecordExportTaskAdmin
        from apps.chat_records.models import ChatRecordExportTask

        admin_obj = ChatRecordExportTaskAdmin(ChatRecordExportTask, AdminSite())
        assert "id" in admin_obj.list_display

    def test_recording_admin(self):
        from apps.chat_records.admin import ChatRecordRecordingAdmin
        from apps.chat_records.models import ChatRecordRecording

        admin_obj = ChatRecordRecordingAdmin(ChatRecordRecording, AdminSite())
        assert "id" in admin_obj.list_display


# ==============================================================================
# express_query
# ==============================================================================

@pytest.mark.django_db
class TestExpressQueryAdmin:
    def test_tool_admin(self):
        from apps.express_query.admin import ExpressQueryToolAdmin
        from apps.express_query.models import ExpressQueryTool

        admin_obj = ExpressQueryToolAdmin(ExpressQueryTool, AdminSite())
        assert admin_obj.list_display is not None

    def test_task_admin(self):
        from apps.express_query.admin import ExpressQueryTaskAdmin
        from apps.express_query.models import ExpressQueryTask

        admin_obj = ExpressQueryTaskAdmin(ExpressQueryTask, AdminSite())
        assert admin_obj.list_display is not None


# ==============================================================================
# finance
# ==============================================================================

@pytest.mark.django_db
class TestFinanceAdmin:
    def test_lpr_rate_admin(self):
        from apps.finance.admin import LPRRateAdmin
        from apps.finance.models import LPRRate

        admin_obj = LPRRateAdmin(LPRRate, AdminSite())
        assert admin_obj.list_display is not None


# ==============================================================================
# image_rotation
# ==============================================================================

@pytest.mark.django_db
class TestImageRotationAdmin:
    def test_image_rotation_admin(self):
        from apps.image_rotation.admin import ImageRotationAdmin
        from apps.image_rotation.models import ImageRotationTool

        admin_obj = ImageRotationAdmin(ImageRotationTool, AdminSite())
        assert admin_obj.list_display is not None


# ==============================================================================
# invoice_recognition
# ==============================================================================

@pytest.mark.django_db
class TestInvoiceRecognitionAdmin:
    def test_invoice_recognition_task_admin(self):
        from apps.invoice_recognition.admin import InvoiceRecognitionTaskAdmin
        from apps.invoice_recognition.models import InvoiceRecognitionTask

        admin_obj = InvoiceRecognitionTaskAdmin(InvoiceRecognitionTask, AdminSite())
        assert admin_obj.list_display is not None


# ==============================================================================
# doc_converter
# ==============================================================================

@pytest.mark.django_db
class TestDocConverterAdmin:
    def test_job_admin(self):
        from apps.doc_converter.admin import DocConverterJobAdmin
        from apps.doc_converter.models import DocConverterJob

        admin_obj = DocConverterJobAdmin(DocConverterJob, AdminSite())
        assert admin_obj.list_display is not None

    def test_tool_admin(self):
        from apps.doc_converter.admin import DocConverterToolAdmin
        from apps.doc_converter.models import DocConverterTool

        admin_obj = DocConverterToolAdmin(DocConverterTool, AdminSite())
        assert admin_obj.list_display is not None


# ==============================================================================
# organization
# ==============================================================================

@pytest.mark.django_db
class TestOrganizationAdmin:
    def test_lawfirm_admin(self):
        from apps.organization.admin import LawFirmAdmin
        from apps.organization.models import LawFirm

        admin_obj = LawFirmAdmin(LawFirm, AdminSite())
        assert admin_obj.list_display is not None

    def test_lawyer_admin(self):
        from apps.organization.admin import LawyerAdmin
        from apps.organization.models import Lawyer

        admin_obj = LawyerAdmin(Lawyer, AdminSite())
        assert admin_obj.list_display is not None

    def test_lawyer_admin_search_fields(self):
        from apps.organization.admin import LawyerAdmin
        from apps.organization.models import Lawyer

        admin_obj = LawyerAdmin(Lawyer, AdminSite())
        assert len(admin_obj.search_fields) > 0

    def test_team_admin(self):
        from apps.organization.admin import TeamAdmin
        from apps.organization.models import Team

        admin_obj = TeamAdmin(Team, AdminSite())
        assert admin_obj.list_display is not None

    def test_account_credential_admin(self):
        from apps.organization.admin import AccountCredentialAdmin
        from apps.organization.models import AccountCredential

        admin_obj = AccountCredentialAdmin(AccountCredential, AdminSite())
        assert admin_obj.list_display is not None
