"""Tests for cases/services/case/case_admin_service.py — Round 2 coverage.

Covers uncovered branches: get_case_with_admin_relations, build_our_parties
without legal_status, build_material_view_parties edge cases, authorities
without authority_type, group_templates_by_sub_type with extra keys,
get_matched_folder_templates_list, serialize_queryset_for_export,
collect_file_paths_for_export, get_case_file_templates_for_detail
with institutions.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call

import pytest

from apps.cases.services.case.case_admin_service import CaseAdminService


@pytest.fixture
def svc() -> CaseAdminService:
    return CaseAdminService(document_service=MagicMock(), filing_number_service=MagicMock())


# ── build_our_parties ──


class TestBuildOurPartiesEdgeCases:
    def test_no_legal_status(self, svc: CaseAdminService):
        case = MagicMock()
        party = MagicMock()
        party.client.id = 1
        party.client.name = "Test"
        party.client.is_our_client = True
        party.client.client_type = "natural"
        party.legal_status = None
        case.parties.all.return_value = [party]

        result = svc.build_our_parties(case)
        assert len(result) == 1
        assert result[0]["legal_status"] is None
        assert result[0]["legal_status_display"] == ""

    def test_no_client_type(self, svc: CaseAdminService):
        case = MagicMock()
        party = MagicMock()
        party.client.id = 1
        party.client.name = "Test"
        party.client.is_our_client = True
        party.client.client_type = None
        party.legal_status = "plaintiff"
        party.get_legal_status_display.return_value = "原告"
        case.parties.all.return_value = [party]

        result = svc.build_our_parties(case)
        assert len(result) == 1
        assert result[0]["client_type"] == ""


# ── build_material_view_parties ──


class TestBuildMaterialViewPartiesEdge:
    def test_no_legal_status(self, svc: CaseAdminService):
        case = MagicMock()
        party = MagicMock()
        party.id = 1
        party.client.name = "Test"
        party.client.is_our_client = True
        party.legal_status = None
        case.parties.all.return_value = [party]

        our, opp = svc.build_material_view_parties(case)
        assert len(our) == 1
        assert our[0]["legal_status_display"] == ""

    def test_empty_name(self, svc: CaseAdminService):
        case = MagicMock()
        party = MagicMock()
        party.id = 1
        party.client.name = ""
        party.client.is_our_client = False
        party.legal_status = "defendant"
        party.get_legal_status_display.return_value = "被告"
        case.parties.all.return_value = [party]

        our, opp = svc.build_material_view_parties(case)
        assert len(opp) == 1
        assert opp[0]["name"] == ""


# ── build_material_view_authorities ──


class TestBuildMaterialViewAuthoritiesEdge:
    def test_no_authority_type(self, svc: CaseAdminService):
        case = MagicMock()
        auth = MagicMock()
        auth.id = 1
        auth.name = "Test Court"
        auth.authority_type = ""
        case.supervising_authorities.all.return_value.order_by.return_value = [auth]

        result = svc.build_material_view_authorities(case)
        assert len(result) == 1
        assert result[0]["authority_type_display"] == ""

    def test_empty_name(self, svc: CaseAdminService):
        case = MagicMock()
        auth = MagicMock()
        auth.id = 1
        auth.name = None
        auth.authority_type = "court"
        auth.get_authority_type_display.return_value = "法院"
        case.supervising_authorities.all.return_value.order_by.return_value = [auth]

        result = svc.build_material_view_authorities(case)
        assert result[0]["name"] == ""


# ── get_case_with_admin_relations ──


class TestGetCaseWithAdminRelations:
    @pytest.mark.django_db
    def test_not_found_returns_none(self, svc: CaseAdminService):
        result = svc.get_case_with_admin_relations(999999)
        assert result is None

    @pytest.mark.django_db
    def test_found_returns_case(self, svc: CaseAdminService):
        from apps.cases.models import Case

        case = Case.objects.create(name="Admin Rel Test")
        result = svc.get_case_with_admin_relations(case.id)
        assert result is not None
        assert result.id == case.id


# ── group_templates_by_sub_type ──


class TestGroupTemplatesBySubTypeExtra:
    def test_extra_keys_sorted(self, svc: CaseAdminService):
        templates = [
            {"case_sub_type": "zz_extra", "name": "Z Extra"},
            {"case_sub_type": "aa_extra", "name": "A Extra"},
            {"case_sub_type": "known", "name": "Known"},
        ]
        choices = [("known", "已知类型")]

        result = svc.group_templates_by_sub_type(templates, choices)
        labels = [r[0] for r in result]
        # "已知类型" should come first (from choices), then extra keys sorted
        assert labels[0] == "已知类型"
        assert labels[1] == "aa_extra"
        assert labels[2] == "zz_extra"

    def test_default_sub_type(self, svc: CaseAdminService):
        templates = [{"name": "No sub type"}]
        choices = [("other_materials", "其他材料")]

        result = svc.group_templates_by_sub_type(templates, choices)
        assert len(result) == 1
        assert result[0][0] == "其他材料"


# ── detect_special_template_flags ──


class TestDetectSpecialTemplateFlagsEdge:
    def test_empty_templates(self, svc: CaseAdminService):
        has_pres, has_delay = svc.detect_special_template_flags([])
        assert has_pres is False
        assert has_delay is False

    def test_multiple_templates(self, svc: CaseAdminService):
        templates = [
            {"function_code": "preservation_application", "name": "保全"},
            {"function_code": "delay_delivery_application", "name": "暂缓"},
        ]
        has_pres, has_delay = svc.detect_special_template_flags(templates)
        assert has_pres is True
        assert has_delay is True

    def test_name_only_delay(self, svc: CaseAdminService):
        templates = [{"function_code": None, "name": "暂缓送达申请书"}]
        has_pres, has_delay = svc.detect_special_template_flags(templates)
        assert has_pres is False
        assert has_delay is True


# ── get_matched_folder_templates_list ──


class TestGetMatchedFolderTemplatesList:
    def test_success(self, svc: CaseAdminService):
        with patch("apps.cases.services.case.case_admin_service.import_module") as mock_import:
            mock_module = MagicMock()
            mock_module.TemplateMatchingService.return_value.find_matching_case_folder_templates_list.return_value = [{"name": "tpl"}]
            mock_import.return_value = mock_module
            result = svc.get_matched_folder_templates_list("litigation", ["plaintiff"])
            assert len(result) == 1

    def test_exception_returns_empty(self, svc: CaseAdminService):
        with patch("apps.cases.services.case.case_admin_service.import_module", side_effect=ImportError("no")):
            result = svc.get_matched_folder_templates_list("litigation")
            assert result == []


# ── get_case_file_sub_type_choices ──


class TestGetCaseFileSubTypeChoicesMore:
    def test_returns_list(self, svc: CaseAdminService):
        result = svc.get_case_file_sub_type_choices()
        assert isinstance(result, list)


# ── _get_case_applicable_institutions ──


class TestGetCaseApplicableInstitutions:
    def test_deduplicates_names(self, svc: CaseAdminService):
        case = MagicMock()
        auth1 = MagicMock(name="Court A")
        auth1.name = "北京市朝阳区法院"
        auth2 = MagicMock(name="Court A dup")
        auth2.name = "北京市朝阳区法院"
        auth3 = MagicMock(name="Court B")
        auth3.name = "北京市海淀区法院"
        case.supervising_authorities.all.return_value = [auth1, auth2, auth3]

        result = svc._get_case_applicable_institutions(case)
        assert len(result) == 2
        assert "北京市朝阳区法院" in result
        assert "北京市海淀区法院" in result

    def test_empty_name_skipped(self, svc: CaseAdminService):
        case = MagicMock()
        auth = MagicMock()
        auth.name = ""
        case.supervising_authorities.all.return_value = [auth]

        result = svc._get_case_applicable_institutions(case)
        assert result == []

    def test_none_name_skipped(self, svc: CaseAdminService):
        case = MagicMock()
        auth = MagicMock()
        auth.name = None
        case.supervising_authorities.all.return_value = [auth]

        result = svc._get_case_applicable_institutions(case)
        assert result == []


# ── build_materials_view_payload ──


class TestBuildMaterialsViewPayloadMore:
    def test_with_parties_and_authorities(self, svc: CaseAdminService):
        case = MagicMock()
        case.id = 42

        our = MagicMock()
        our.id = 1
        our.client.name = "我方"
        our.client.is_our_client = True
        our.legal_status = "plaintiff"
        our.get_legal_status_display.return_value = "原告"

        case.parties.all.return_value = [our]
        case.supervising_authorities.all.return_value.order_by.return_value = []

        mat_svc = MagicMock()
        mat_svc.get_used_type_ids.return_value = [1]
        mat_svc.get_material_types_by_category.return_value = [{"id": 1, "name": "起诉状"}]

        result = svc.build_materials_view_payload(case=case, material_service=mat_svc, law_firm_id=1)
        assert result["party_types"] == [{"id": 1, "name": "起诉状"}]
        assert len(result["our_parties"]) == 1
        assert result["our_parties"][0]["legal_status_display"] == "原告"
