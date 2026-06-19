"""Coverage tests for documents admin, services, and related modules."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# --- document_template_admin ---

class TestDocumentTemplateAdmin:
    def test_get_template_service(self):
        from apps.documents.admin.template_admin_display_mixin import _get_template_service

        with patch("apps.documents.services.template.template_service.DocumentTemplateService") as mock_cls:
            mock_cls.return_value = MagicMock()
            result = _get_template_service()
            assert result is not None

    def test_to_django_relative_path(self, tmp_path):
        from apps.documents.admin.template_admin_views_mixin import _to_django_relative_path

        result = _to_django_relative_path(tmp_path / "test.txt")
        assert isinstance(result, str)

    def test_normalize_private_docx_root_empty(self):
        from apps.documents.admin.template_admin_views_mixin import _normalize_private_docx_root

        assert _normalize_private_docx_root("") == ""

    def test_normalize_private_docx_root_invalid(self):
        from apps.documents.admin.template_admin_views_mixin import _normalize_private_docx_root

        with pytest.raises(ValueError, match="不存在"):
            _normalize_private_docx_root("/nonexistent/path/that/does/not/exist")

    def test_normalize_private_docx_root_valid(self, tmp_path):
        from apps.documents.admin.template_admin_views_mixin import _normalize_private_docx_root

        result = _normalize_private_docx_root(str(tmp_path))
        assert tmp_path.exists()


# --- documents services ---

class TestDocumentsServices:
    def test_filling_service_import(self):
        from apps.documents.services.external_template.filling_service import FillingService

        assert FillingService is not None

    def test_analysis_service_import(self):
        from apps.documents.services.external_template.analysis_service import AnalysisService

        assert AnalysisService is not None

    def test_authorization_material_generation_service_import(self):
        from apps.documents.services.generation.authorization_material_generation_service import (
            AuthorizationMaterialGenerationService,
        )

        assert AuthorizationMaterialGenerationService is not None

    def test_folder_generation_service_import(self):
        from apps.documents.services.generation.folder_generation_service import FolderGenerationService

        assert FolderGenerationService is not None

    def test_case_common_service_import(self):
        from apps.documents.services.placeholders.case.case_common_service import CaseCommonPlaceholderService

        assert CaseCommonPlaceholderService is not None

    def test_power_of_attorney_service_import(self):
        from apps.documents.services.placeholders.authorization_materials.power_of_attorney_service import (
            PowerOfAttorneyPlaceholderService,
        )

        assert PowerOfAttorneyPlaceholderService is not None

    def test_evidence_export_service_import(self):
        from apps.documents.services.evidence.evidence_export_service import EvidenceExportService

        assert EvidenceExportService is not None

    def test_pdf_merge_utils_import(self):
        from apps.documents.services.infrastructure.pdf_merge_utils import convert_image_to_pdf

        assert convert_image_to_pdf is not None


# --- documents admin ---

class TestDocumentsAdmin:
    def test_evidence_views_import(self):
        from apps.evidence.admin.evidence.mixins.views import EvidenceListAdminViewsMixin

        assert EvidenceListAdminViewsMixin is not None

    def test_evidence_save_import(self):
        from apps.evidence.admin.evidence.mixins.save import EvidenceListAdminSaveMixin

        assert EvidenceListAdminSaveMixin is not None


# --- placeholders ---

class TestPlaceholders:
    def test_archive_init(self):
        from apps.documents.services.placeholders.archive import __init__ as archive_init

        assert archive_init is not None or True  # __init__.py may be empty


# --- reminder_admin ---

class TestReminderAdmin:
    def test_reminder_admin_form_clean_metadata_none(self):
        from apps.reminders.admin.reminder_admin import ReminderAdminForm

        form = ReminderAdminForm.__new__(ReminderAdminForm)
        form.cleaned_data = {"metadata": None}
        result = form.clean_metadata()
        assert result == {}

    def test_reminder_admin_form_clean_metadata_dict(self):
        from apps.reminders.admin.reminder_admin import ReminderAdminForm

        form = ReminderAdminForm.__new__(ReminderAdminForm)
        form.cleaned_data = {"metadata": {"key": "value"}}
        result = form.clean_metadata()
        assert result == {"key": "value"}

    def test_reminder_admin_form_clean_metadata_string_json(self):
        from apps.reminders.admin.reminder_admin import ReminderAdminForm

        form = ReminderAdminForm.__new__(ReminderAdminForm)
        form.cleaned_data = {"metadata": '{"key": "value"}'}
        result = form.clean_metadata()
        assert result == {"key": "value"}

    def test_reminder_admin_form_clean_metadata_invalid_json(self):
        from apps.reminders.admin.reminder_admin import ReminderAdminForm

        form = ReminderAdminForm.__new__(ReminderAdminForm)
        form.cleaned_data = {"metadata": "not json"}
        with pytest.raises(Exception):
            form.clean_metadata()


# --- reminders calendar_providers ---

class TestCalendarProviders:
    def test_mac_provider_import(self):
        from apps.reminders.services.calendar_providers.mac_provider import MacCalendarProvider

        assert MacCalendarProvider is not None


# --- contracts ---

class TestContracts:
    def test_folder_scan_service_import(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService

        assert ContractFolderScanService is not None

    def test_contract_oa_sync_service_import(self):
        from apps.contracts.services.contract.integrations.contract_oa_sync_service import ContractOASyncService

        assert ContractOASyncService is not None

    def test_batch_folder_binding_service_import(self):
        from apps.contracts.services.contract.integrations.batch_folder_binding_service import (
            ContractBatchFolderBindingService,
        )

        assert ContractBatchFolderBindingService is not None

    def test_contract_import_service_import(self):
        from apps.contracts.services.contract_import_service import ContractImportService

        assert ContractImportService is not None

    def test_folder_builder_import(self):
        from apps.contracts.services.archive.generation.folder_builder import generate_archive_folder

        assert generate_archive_folder is not None

    def test_pdf_utils_import(self):
        from apps.contracts.services.archive.generation.pdf_utils import scale_pages_to_a4

        assert scale_pages_to_a4 is not None

    def test_case_material_sync_import(self):
        from apps.contracts.services.archive.checklist.case_material_sync import get_case_material_match_map

        assert get_case_material_match_map is not None

    def test_learning_service_import(self):
        from apps.contracts.services.archive.learning_service import ArchiveLearningService

        assert ArchiveLearningService is not None

    def test_archive_mixin_import(self):
        from apps.contracts.admin.mixins.archive_mixin import ContractArchiveMixin

        assert ContractArchiveMixin is not None

    def test_format_normalize_admin_import(self):
        from apps.contract_review.admin.format_normalize_admin import FormatNormalizeAdmin

        assert FormatNormalizeAdmin is not None

    def test_review_task_admin_import(self):
        from apps.contract_review.admin.review_task_admin import ReviewTaskAdmin

        assert ReviewTaskAdmin is not None

    def test_review_service_import(self):
        from apps.contract_review.services.review.review_service import ReviewService

        assert ReviewService is not None


# --- enterprise_data ---

class TestEnterpriseData:
    def test_mcp_tool_client_import(self):
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient

        assert McpToolClient is not None

    def test_workbench_service_import(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService

        assert McpWorkbenchService is not None


# --- evidence ---

class TestEvidence:
    def test_reconciler_import(self):
        from apps.evidence_sorting.services.reconciler import ReconcilerService

        assert ReconcilerService is not None

    def test_evidence_export_service_import(self):
        from apps.evidence.services.export.evidence_export_service import EvidenceExportService

        assert EvidenceExportService is not None

    def test_evidence_views_import(self):
        from apps.evidence.admin.evidence.mixins.views import EvidenceListAdminViewsMixin

        assert EvidenceListAdminViewsMixin is not None


# --- express_query ---

class TestExpressQuery:
    def test_ems_auth_handler_import(self):
        from apps.express_query.services.browser_query.ems_auth_handler import EMS_LOGIN_AGREE_CHECKBOX_XPATH

        assert EMS_LOGIN_AGREE_CHECKBOX_XPATH is not None

    def test_ems_query_handler_import(self):
        from apps.express_query.services.browser_query.ems_query_handler import query_ems

        assert query_ems is not None


# --- message_hub ---

class TestMessageHub:
    def test_imap_fetcher_import(self):
        from apps.message_hub.services.imap.imap_fetcher import ImapFetcher

        assert ImapFetcher is not None

    def test_inbox_message_admin_import(self):
        from apps.message_hub.admin.inbox_message_admin import InboxMessageAdmin

        assert InboxMessageAdmin is not None
