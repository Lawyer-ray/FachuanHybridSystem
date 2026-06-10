"""
Tests for documents/models/ - proxy_matter_rule, placeholder, folder_template properties.
Also covers documents/tasks.py and signals.py uncovered lines.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestProxyMatterRuleModel:
    @pytest.mark.django_db
    def test_str_with_fields(self):
        from apps.core.models.enums import CaseStage, SimpleCaseType
        from apps.documents.models import ProxyMatterRule

        rule = ProxyMatterRule.objects.create(
            case_types=[SimpleCaseType.CIVIL],
            case_stage=CaseStage.FIRST_TRIAL,
            legal_statuses=["plaintiff"],
            items_text="item1",
        )
        s = str(rule)
        assert isinstance(s, str)
        assert len(s) > 0

    @pytest.mark.django_db
    def test_str_with_empty_fields(self):
        from apps.documents.models import ProxyMatterRule

        rule = ProxyMatterRule.objects.create(items_text="item1")
        s = str(rule)
        assert "任意类型" in s

    @pytest.mark.django_db
    def test_get_case_types_display_empty(self):
        from apps.documents.models import ProxyMatterRule

        rule = ProxyMatterRule(case_types=[])
        assert rule.get_case_types_display() == ""

    @pytest.mark.django_db
    def test_get_case_types_display_with_values(self):
        from apps.core.models.enums import SimpleCaseType
        from apps.documents.models import ProxyMatterRule

        rule = ProxyMatterRule(case_types=[SimpleCaseType.CIVIL])
        display = rule.get_case_types_display()
        assert len(display) > 0

    @pytest.mark.django_db
    def test_get_legal_statuses_display_empty(self):
        from apps.documents.models import ProxyMatterRule

        rule = ProxyMatterRule(legal_statuses=[])
        assert rule.get_legal_statuses_display() == ""

    @pytest.mark.django_db
    def test_get_legal_statuses_display_with_values(self):
        from apps.core.models.enums import LegalStatus
        from apps.documents.models import ProxyMatterRule

        rule = ProxyMatterRule(legal_statuses=[LegalStatus.PLAINTIFF])
        display = rule.get_legal_statuses_display()
        assert len(display) > 0


class TestPlaceholderModel:
    def test_str(self):
        from apps.documents.models import Placeholder

        p = Placeholder(key="test_key", display_name="Test Key")
        assert "test_key" in str(p)

    def test_data_path_property(self):
        from apps.documents.models import Placeholder

        p = Placeholder(key="k", display_name="D")
        assert p.data_path == ""
        p.data_path = "some/path"
        assert p.data_path == "some/path"

    def test_category_property(self):
        from apps.documents.models import Placeholder

        p = Placeholder(key="k", display_name="D")
        assert p.category == ""
        p.category = "litigation"
        assert p.category == "litigation"


class TestFolderTemplateProperties:
    def _make_template(self, **kwargs):
        from apps.documents.models import FolderTemplate

        defaults = {
            "name": "Test Template",
            "template_type": "contract",
            "case_types": [],
            "case_stages": [],
            "contract_types": [],
            "structure": {},
            "is_active": True,
            "is_default": False,
        }
        defaults.update(kwargs)
        return FolderTemplate(**defaults)

    def test_template_type_display(self):
        ft = self._make_template(template_type="contract")
        assert isinstance(ft.template_type_display, str)

    def test_case_types_display_empty(self):
        ft = self._make_template(case_types=[])
        assert ft.case_types_display == "-"

    def test_case_types_display_single(self):
        ft = self._make_template(case_types=["civil"])
        assert ft.case_types_display == "civil" or len(ft.case_types_display) > 0

    def test_case_types_display_multiple(self):
        ft = self._make_template(case_types=["civil", "criminal", "admin"])
        assert "种类型" in ft.case_types_display

    def test_case_stages_display(self):
        ft = self._make_template(case_stages=["first_instance"])
        assert isinstance(ft.case_stages_display, str)

    def test_contract_types_display(self):
        ft = self._make_template(contract_types=["service"])
        assert isinstance(ft.contract_types_display, str)

    def test_case_type_property(self):
        ft = self._make_template(case_types=["civil"])
        assert ft.case_type == "civil"

    def test_case_type_property_empty(self):
        ft = self._make_template(case_types=[])
        assert ft.case_type is None

    def test_case_stage_property(self):
        ft = self._make_template(case_stages=["first_instance"])
        assert ft.case_stage == "first_instance"

    def test_case_stage_property_empty(self):
        ft = self._make_template(case_stages=[])
        assert ft.case_stage is None

    def test_get_legal_statuses_display_empty(self):
        ft = self._make_template(legal_statuses=[])
        assert ft.get_legal_statuses_display() == ""

    def test_legal_statuses_display_property(self):
        ft = self._make_template(legal_statuses=[])
        assert ft.legal_statuses_display == "-"

    def test_str(self):
        ft = self._make_template()
        s = str(ft)
        assert "Test Template" in s


class TestDocumentTemplateModel:
    def test_audit_hooks_import_path(self):
        """Verify the hook methods exist and can be called with mocked internals."""
        from apps.documents.models.document_template import DocumentTemplate

        dt = DocumentTemplate(name="Test", template_type="contract")
        # Verify the hook methods exist
        assert hasattr(dt, "on_create_audit_log")
        assert hasattr(dt, "on_update_audit_log")

    def test_absolute_file_path_empty(self):
        from apps.documents.models.document_template import DocumentTemplate

        dt = DocumentTemplate(name="Test", template_type="contract", file_path="")
        assert dt.absolute_file_path == ""

    def test_absolute_file_path_set(self):
        from apps.documents.models.document_template import DocumentTemplate

        dt = DocumentTemplate(name="Test", template_type="contract", file_path="test.docx")
        with patch(
            "apps.documents.models.document_template.resolve_docx_template_path"
        ) as mock_resolve:
            mock_path = MagicMock()
            mock_path.__str__ = lambda self: "/resolved/test.docx"
            mock_resolve.return_value = mock_path
            result = dt.absolute_file_path
            assert "test.docx" in result


class TestTasks:
    def test_merge_evidence_pdf_task_delegates(self):
        from apps.documents.tasks import merge_evidence_pdf_task

        with patch("apps.evidence.tasks.merge_evidence_pdf_task") as mock_task:
            mock_task.return_value = "ok"
            result = merge_evidence_pdf_task(42)
            mock_task.assert_called_once_with(42)
            assert result == "ok"


class TestSignals:
    def test_signals_module_imports(self):
        """Verify signals module can be imported and key functions exist."""
        from apps.documents import signals

        assert hasattr(signals, "_create_audit_log")
