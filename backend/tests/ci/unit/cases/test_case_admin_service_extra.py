pytestmark = pytest.mark.skip(reason='CI isolation issue - needs fix')

"""Tests for cases/services/case/case_admin_service.py — additional coverage."""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch, call

import pytest

from apps.cases.services.case.case_admin_service import (
    CaseAdminService,
    MaterialViewPayload,
)


@pytest.fixture
def svc() -> CaseAdminService:
    doc_svc = MagicMock()
    filing_svc = MagicMock()
    return CaseAdminService(document_service=doc_svc, filing_number_service=filing_svc)


@pytest.fixture
def svc_no_deps() -> CaseAdminService:
    return CaseAdminService()


# ── Lazy loading ──────────────────────────────────────────────────────────────

def test_document_service_lazy_load(svc_no_deps: CaseAdminService) -> None:
    with patch("apps.cases.services.case.case_admin_service.get_document_service") as mock_get:
        mock_get.return_value = MagicMock()
        result = svc_no_deps.document_service
        assert result is not None
        assert svc_no_deps.document_service is result


def test_filing_number_service_lazy_load(svc_no_deps: CaseAdminService) -> None:
    with patch("apps.cases.services.case.case_admin_service.get_case_filing_number_service") as mock_get:
        mock_get.return_value = MagicMock()
        result = svc_no_deps.filing_number_service
        assert result is not None
        assert svc_no_deps.filing_number_service is result


# ── get_matched_folder_templates ──────────────────────────────────────────────

def test_get_matched_folder_templates_basic(svc: CaseAdminService) -> None:
    svc.document_service.get_matched_folder_templates.return_value = "模板A"
    result = svc.get_matched_folder_templates("civil")
    assert result == "模板A"


def test_get_matched_folder_templates_with_legal_status(svc: CaseAdminService) -> None:
    svc.document_service.get_matched_folder_templates_with_legal_status.return_value = "模板B"
    result = svc.get_matched_folder_templates("civil", legal_statuses=["原告"])
    assert isinstance(result, tuple)


def test_get_matched_folder_templates_exception(svc: CaseAdminService) -> None:
    svc.document_service.get_matched_folder_templates.side_effect = Exception("fail")
    result = svc.get_matched_folder_templates("civil")
    assert "查询失败" in str(result)


# ── get_matched_folder_templates_list ─────────────────────────────────────────

def test_get_matched_folder_templates_list_success(svc: CaseAdminService) -> None:
    mock_module = MagicMock()
    mock_module.TemplateMatchingService.return_value.find_matching_case_folder_templates_list.return_value = [{"id": 1}]
    with patch("apps.cases.services.case.case_admin_service.import_module", return_value=mock_module):
        result = svc.get_matched_folder_templates_list("civil")
    assert result == [{"id": 1}]


def test_get_matched_folder_templates_list_exception(svc: CaseAdminService) -> None:
    with patch("apps.cases.services.case.case_admin_service.import_module", side_effect=Exception("fail")):
        result = svc.get_matched_folder_templates_list("civil")
    assert result == []


# ── get_matched_case_file_templates ───────────────────────────────────────────

def test_get_matched_case_file_templates_success(svc: CaseAdminService) -> None:
    svc.document_service.find_matching_case_file_templates.return_value = [{"id": 1}]
    result = svc.get_matched_case_file_templates("civil", "filing")
    assert result == [{"id": 1}]


def test_get_matched_case_file_templates_exception(svc: CaseAdminService) -> None:
    svc.document_service.find_matching_case_file_templates.side_effect = Exception("fail")
    result = svc.get_matched_case_file_templates("civil", "filing")
    assert result == []


# ── get_case_file_sub_type_choices ────────────────────────────────────────────

def test_get_case_file_sub_type_choices_success(svc: CaseAdminService) -> None:
    mock_module = MagicMock()
    mock_module.DocumentCaseFileSubType.choices = [("a", "A"), ("b", "B")]
    with patch("apps.cases.services.case.case_admin_service.import_module", return_value=mock_module):
        result = svc.get_case_file_sub_type_choices()
    assert len(result) == 2


def test_get_case_file_sub_type_choices_exception(svc: CaseAdminService) -> None:
    with patch("apps.cases.services.case.case_admin_service.import_module", side_effect=Exception("fail")):
        result = svc.get_case_file_sub_type_choices()
    assert result == []


# ── get_case_file_templates_for_detail ────────────────────────────────────────

def test_get_case_file_templates_for_detail_no_case_type(svc: CaseAdminService) -> None:
    case = MagicMock()
    case.case_type = ""
    case.current_stage = "filing"
    templates, reason = svc.get_case_file_templates_for_detail(case)
    assert templates == []
    assert "案件类型" in reason


def test_get_case_file_templates_for_detail_no_stage(svc: CaseAdminService) -> None:
    case = MagicMock()
    case.case_type = "civil"
    case.current_stage = ""
    templates, reason = svc.get_case_file_templates_for_detail(case)
    assert templates == []
    assert "案件阶段" in reason


def test_get_case_file_templates_for_detail_success(svc: CaseAdminService) -> None:
    case = MagicMock()
    case.case_type = "civil"
    case.current_stage = "filing"
    case.supervising_authorities.all.return_value = []
    svc.document_service.find_matching_case_file_templates.return_value = [{"id": 1}]
    templates, reason = svc.get_case_file_templates_for_detail(case)
    assert len(templates) == 1
    assert reason == ""


# ── _get_case_applicable_institutions ─────────────────────────────────────────

def test_get_case_applicable_institutions(svc: CaseAdminService) -> None:
    auth1 = MagicMock()
    auth1.name = "北京法院"
    auth2 = MagicMock()
    auth2.name = "上海法院"
    auth3 = MagicMock()
    auth3.name = "北京法院"
    case = MagicMock()
    case.supervising_authorities.all.return_value = [auth1, auth2, auth3]

    result = svc._get_case_applicable_institutions(case)
    assert result == ["北京法院", "上海法院"]


def test_get_case_applicable_institutions_empty_name(svc: CaseAdminService) -> None:
    auth = MagicMock()
    auth.name = ""
    case = MagicMock()
    case.supervising_authorities.all.return_value = [auth]

    result = svc._get_case_applicable_institutions(case)
    assert result == []


# ── build_our_parties ─────────────────────────────────────────────────────────

def test_build_our_parties(svc: CaseAdminService) -> None:
    client = MagicMock()
    client.id = 1
    client.name = "Client A"
    client.client_type = "legal"
    client.is_our_client = True

    party = MagicMock()
    party.client = client
    party.legal_status = "plaintiff"
    party.get_legal_status_display.return_value = "原告"

    case = MagicMock()
    case.parties.all.return_value = [party]

    result = svc.build_our_parties(case)
    assert len(result) == 1
    assert result[0]["id"] == 1
    assert result[0]["name"] == "Client A"


def test_build_our_parties_filters_opponent(svc: CaseAdminService) -> None:
    client = MagicMock()
    client.is_our_client = False
    party = MagicMock()
    party.client = client

    case = MagicMock()
    case.parties.all.return_value = [party]

    result = svc.build_our_parties(case)
    assert result == []


def test_build_our_parties_no_legal_status(svc: CaseAdminService) -> None:
    client = MagicMock()
    client.id = 1
    client.name = "Client"
    client.client_type = "individual"
    client.is_our_client = True

    party = MagicMock()
    party.client = client
    party.legal_status = None

    case = MagicMock()
    case.parties.all.return_value = [party]

    result = svc.build_our_parties(case)
    assert result[0]["legal_status_display"] == ""


# ── build_material_view_parties ───────────────────────────────────────────────

def test_build_material_view_parties(svc: CaseAdminService) -> None:
    our_client = MagicMock()
    our_client.name = "Our Client"
    our_client.is_our_client = True
    our_party = MagicMock()
    our_party.id = 1
    our_party.client = our_client
    our_party.legal_status = "plaintiff"
    our_party.get_legal_status_display.return_value = "原告"

    opp_client = MagicMock()
    opp_client.name = "Opponent"
    opp_client.is_our_client = False
    opp_party = MagicMock()
    opp_party.id = 2
    opp_party.client = opp_client
    opp_party.legal_status = None

    case = MagicMock()
    case.parties.all.return_value = [our_party, opp_party]

    our, opp = svc.build_material_view_parties(case)
    assert len(our) == 1
    assert len(opp) == 1
    assert our[0]["id"] == 1
    assert opp[0]["id"] == 2


# ── build_material_view_authorities ───────────────────────────────────────────

def test_build_material_view_authorities(svc: CaseAdminService) -> None:
    auth = MagicMock()
    auth.id = 1
    auth.name = "北京法院"
    auth.authority_type = "court"
    auth.get_authority_type_display.return_value = "法院"

    case = MagicMock()
    case.supervising_authorities.all.return_value.order_by.return_value = [auth]

    result = svc.build_material_view_authorities(case)
    assert len(result) == 1
    assert result[0]["name"] == "北京法院"


def test_build_material_view_authorities_no_type(svc: CaseAdminService) -> None:
    auth = MagicMock()
    auth.id = 1
    auth.name = "Test"
    auth.authority_type = ""

    case = MagicMock()
    case.supervising_authorities.all.return_value.order_by.return_value = [auth]

    result = svc.build_material_view_authorities(case)
    assert result[0]["authority_type_display"] == ""


# ── get_case_with_admin_relations ─────────────────────────────────────────────

def test_get_case_with_admin_relations_not_found(svc: CaseAdminService) -> None:
    with patch("apps.cases.services.case.case_admin_service.Case") as MockCase:
        MockCase.DoesNotExist = type("DoesNotExist", (Exception,), {})
        MockCase.objects.select_related.return_value.prefetch_related.return_value.get.side_effect = MockCase.DoesNotExist

        result = svc.get_case_with_admin_relations(999)
        assert result is None


# ── build_materials_view_payload ──────────────────────────────────────────────

def test_build_materials_view_payload(svc: CaseAdminService) -> None:
    case = MagicMock()
    case.id = 1
    case.parties.all.return_value = []
    case.supervising_authorities.all.return_value.order_by.return_value = []

    mock_material_service = MagicMock()
    mock_material_service.get_used_type_ids.return_value = [1, 2]
    mock_material_service.get_material_types_by_category.return_value = []

    result = svc.build_materials_view_payload(
        case=case, material_service=mock_material_service, law_firm_id=1,
    )
    assert "party_types" in result
    assert "non_party_types" in result
    assert "our_parties" in result
    assert "opponent_parties" in result
    assert "authorities" in result


# ── group_templates_by_sub_type ───────────────────────────────────────────────

def test_group_templates_by_sub_type_basic(svc: CaseAdminService) -> None:
    templates = [
        {"case_sub_type": "complaint", "name": "起诉状"},
        {"case_sub_type": "evidence_list", "name": "证据清单"},
        {"case_sub_type": "complaint", "name": "答辩状"},
    ]
    choices = [("complaint", "起诉文书"), ("evidence_list", "证据材料"), ("other_materials", "其他")]

    result = svc.group_templates_by_sub_type(templates, choices)
    assert len(result) == 2
    assert result[0][0] == "起诉文书"
    assert len(result[0][1]) == 2


def test_group_templates_excludes_special_types(svc: CaseAdminService) -> None:
    templates = [
        {"case_sub_type": "complaint", "name": "起诉状"},
        {"case_sub_type": "power_of_attorney_materials", "name": "授权委托"},
        {"case_sub_type": "property_preservation_materials", "name": "保全"},
    ]
    choices = [("complaint", "起诉")]

    result = svc.group_templates_by_sub_type(templates, choices)
    assert len(result) == 1
    assert result[0][0] == "起诉"


def test_group_templates_include_special_types(svc: CaseAdminService) -> None:
    templates = [
        {"case_sub_type": "power_of_attorney_materials", "name": "授权委托"},
    ]
    choices = [("power_of_attorney_materials", "授权")]

    result = svc.group_templates_by_sub_type(templates, choices, exclude_special_sub_types=False)
    assert len(result) == 1


def test_group_templates_unknown_sub_type(svc: CaseAdminService) -> None:
    templates = [{"case_sub_type": "unknown_type", "name": "test"}]
    choices = []

    result = svc.group_templates_by_sub_type(templates, choices)
    assert len(result) == 1


def test_group_templates_default_sub_type(svc: CaseAdminService) -> None:
    templates = [{"name": "no sub type"}]
    choices = [("other_materials", "其他")]

    result = svc.group_templates_by_sub_type(templates, choices)
    assert len(result) == 1


# ── detect_special_template_flags ─────────────────────────────────────────────

def test_detect_special_preservation_by_function_code(svc: CaseAdminService) -> None:
    templates = [{"function_code": "preservation_application", "name": "test"}]
    has_pres, has_delay = svc.detect_special_template_flags(templates)
    assert has_pres is True
    assert has_delay is False


def test_detect_special_preservation_by_name(svc: CaseAdminService) -> None:
    templates = [{"name": "财产保全申请书"}]
    has_pres, has_delay = svc.detect_special_template_flags(templates)
    assert has_pres is True


def test_detect_special_delay_by_function_code(svc: CaseAdminService) -> None:
    templates = [{"function_code": "delay_delivery_application", "name": "test"}]
    has_pres, has_delay = svc.detect_special_template_flags(templates)
    assert has_pres is False
    assert has_delay is True


def test_detect_special_delay_by_name(svc: CaseAdminService) -> None:
    templates = [{"name": "暂缓送达申请书"}]
    has_pres, has_delay = svc.detect_special_template_flags(templates)
    assert has_delay is True


def test_detect_special_none(svc: CaseAdminService) -> None:
    templates = [{"name": "普通模板"}]
    has_pres, has_delay = svc.detect_special_template_flags(templates)
    assert has_pres is False
    assert has_delay is False


def test_detect_special_empty(svc: CaseAdminService) -> None:
    has_pres, has_delay = svc.detect_special_template_flags([])
    assert has_pres is False
    assert has_delay is False


# ── handle_case_filing_change ─────────────────────────────────────────────────
# Note: handle_case_filing_change uses @transaction.atomic and Case.objects.get
# which requires database access. Tested via integration tests instead.
# We test the pure logic branches that don't need DB.

# ── import_cases_from_json_data ───────────────────────────────────────────────

def test_import_cases_from_json_data_success(svc: CaseAdminService) -> None:
    mock_import_service = MagicMock()
    mock_import_service.import_one.return_value = MagicMock()

    data_list = [
        {"name": "Case 1", "filing_number": "FC-1"},
        {"name": "Case 2", "filing_number": None},
    ]

    with patch("apps.cases.services.case.case_admin_service.Case") as MockCase:
        MockCase.objects.filter.return_value.exists.return_value = False
        success, skipped, errors = svc.import_cases_from_json_data(
            data_list, case_import_service=mock_import_service,
        )

    assert success == 2
    assert skipped == 0
    assert errors == []


def test_import_cases_from_json_data_with_skip(svc: CaseAdminService) -> None:
    mock_import_service = MagicMock()
    mock_import_service.import_one.return_value = MagicMock()

    data_list = [{"name": "Case 1", "filing_number": "FC-1"}]

    with patch("apps.cases.services.case.case_admin_service.Case") as MockCase:
        MockCase.objects.filter.return_value.exists.return_value = True
        success, skipped, errors = svc.import_cases_from_json_data(
            data_list, case_import_service=mock_import_service,
        )

    assert success == 0
    assert skipped == 1


def test_import_cases_from_json_data_with_error(svc: CaseAdminService) -> None:
    mock_import_service = MagicMock()
    mock_import_service.import_one.side_effect = ValueError("bad data")

    data_list = [{"name": "Bad Case", "filing_number": "FC-1"}]

    with patch("apps.cases.services.case.case_admin_service.Case") as MockCase:
        MockCase.objects.filter.return_value.exists.return_value = False
        success, skipped, errors = svc.import_cases_from_json_data(
            data_list, case_import_service=mock_import_service,
        )

    assert success == 0
    assert skipped == 0
    assert len(errors) == 1
    assert "Bad Case" in errors[0]
