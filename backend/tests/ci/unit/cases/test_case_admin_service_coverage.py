"""cases.services.case.case_admin_service 补充覆盖测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock

import pytest


class TestCaseAdminServiceInit:
    def test_default_init(self):
        from apps.cases.services.case.case_admin_service import CaseAdminService

        svc = CaseAdminService()
        assert svc._document_service is None
        assert svc._filing_number_service is None

    def test_init_with_injection(self):
        from apps.cases.services.case.case_admin_service import CaseAdminService

        doc_svc = MagicMock()
        filing_svc = MagicMock()
        svc = CaseAdminService(document_service=doc_svc, filing_number_service=filing_svc)
        assert svc.document_service is doc_svc
        assert svc.filing_number_service is filing_svc


class TestGetMatchedFolderTemplates:
    def test_with_legal_statuses(self):
        from apps.cases.services.case.case_admin_service import CaseAdminService

        doc_svc = MagicMock()
        doc_svc.get_matched_folder_templates_with_legal_status.return_value = "模板A、模板B"
        svc = CaseAdminService(document_service=doc_svc)

        result = svc.get_matched_folder_templates("litigation", ["原告", "被告"])
        assert "模板A" in str(result)

    def test_without_legal_statuses(self):
        from apps.cases.services.case.case_admin_service import CaseAdminService

        doc_svc = MagicMock()
        doc_svc.get_matched_folder_templates.return_value = "模板C"
        svc = CaseAdminService(document_service=doc_svc)

        result = svc.get_matched_folder_templates("litigation")
        assert result == "模板C"

    def test_exception_returns_failure_string(self):
        from apps.cases.services.case.case_admin_service import CaseAdminService

        doc_svc = MagicMock()
        doc_svc.get_matched_folder_templates.side_effect = RuntimeError("DB error")
        svc = CaseAdminService(document_service=doc_svc)

        result = svc.get_matched_folder_templates("litigation")
        assert "查询失败" in str(result)


class TestGetMatchedCaseFileTemplates:
    def test_success(self):
        from apps.cases.services.case.case_admin_service import CaseAdminService

        doc_svc = MagicMock()
        doc_svc.find_matching_case_file_templates.return_value = [{"name": "模板1"}]
        svc = CaseAdminService(document_service=doc_svc)

        result = svc.get_matched_case_file_templates("litigation", "一审", ["法院A"])
        assert len(result) == 1

    def test_exception_returns_empty(self):
        from apps.cases.services.case.case_admin_service import CaseAdminService

        doc_svc = MagicMock()
        doc_svc.find_matching_case_file_templates.side_effect = RuntimeError("error")
        svc = CaseAdminService(document_service=doc_svc)

        result = svc.get_matched_case_file_templates("litigation", "一审")
        assert result == []


class TestGetCaseFileSubTypeChoices:
    def test_success(self):
        from apps.cases.services.case.case_admin_service import CaseAdminService

        svc = CaseAdminService()
        result = svc.get_case_file_sub_type_choices()
        # Should return a list of tuples
        assert isinstance(result, list)

    @patch("apps.cases.services.case.case_admin_service.import_module")
    def test_exception_returns_empty(self, mock_import):
        from apps.cases.services.case.case_admin_service import CaseAdminService

        mock_import.side_effect = ImportError("not found")
        svc = CaseAdminService()
        result = svc.get_case_file_sub_type_choices()
        assert result == []


class TestGetCaseFileTemplatesForDetail:
    def test_no_case_type(self):
        from apps.cases.services.case.case_admin_service import CaseAdminService

        case = MagicMock()
        case.case_type = ""
        svc = CaseAdminService()
        result = svc.get_case_file_templates_for_detail(case)
        assert result == ([], "未设置案件类型")

    def test_no_current_stage(self):
        from apps.cases.services.case.case_admin_service import CaseAdminService

        case = MagicMock()
        case.case_type = "litigation"
        case.current_stage = ""
        svc = CaseAdminService()
        result = svc.get_case_file_templates_for_detail(case)
        assert result == ([], "未设置案件阶段")

    def test_success_with_authorities(self):
        from apps.cases.services.case.case_admin_service import CaseAdminService

        doc_svc = MagicMock()
        doc_svc.find_matching_case_file_templates.return_value = [{"name": "模板"}]
        svc = CaseAdminService(document_service=doc_svc)

        case = MagicMock()
        case.case_type = "litigation"
        case.current_stage = "一审"
        auth = MagicMock()
        auth.name = "北京市朝阳区法院"
        case.supervising_authorities.all.return_value = [auth]

        templates, missing = svc.get_case_file_templates_for_detail(case)
        assert templates == [{"name": "模板"}]
        assert missing == ""


class TestBuildOurLegalEntities:
    def test_returns_legal_entities(self):
        from apps.cases.services.case.case_admin_service import CaseAdminService

        svc = CaseAdminService()
        case = MagicMock()
        party = MagicMock()
        party.client.id = 1
        party.client.name = "某公司"
        party.client.is_our_client = True
        party.client.client_type = "legal"
        case.parties.all.return_value = [party]

        result = svc.build_our_legal_entities(case)
        assert len(result) == 1
        assert result[0]["name"] == "某公司"

    def test_excludes_non_our_clients(self):
        from apps.cases.services.case.case_admin_service import CaseAdminService

        svc = CaseAdminService()
        case = MagicMock()
        party = MagicMock()
        party.client.is_our_client = False
        case.parties.all.return_value = [party]

        result = svc.build_our_legal_entities(case)
        assert len(result) == 0


class TestBuildOurParties:
    def test_includes_our_clients(self):
        from apps.cases.services.case.case_admin_service import CaseAdminService

        svc = CaseAdminService()
        case = MagicMock()
        party = MagicMock()
        party.client.id = 1
        party.client.name = "原告公司"
        party.client.is_our_client = True
        party.client.client_type = "legal"
        party.legal_status = "plaintiff"
        party.get_legal_status_display.return_value = "原告"
        case.parties.all.return_value = [party]

        result = svc.build_our_parties(case)
        assert len(result) == 1
        assert result[0]["legal_status"] == "plaintiff"

    def test_excludes_opponents(self):
        from apps.cases.services.case.case_admin_service import CaseAdminService

        svc = CaseAdminService()
        case = MagicMock()
        party = MagicMock()
        party.client.is_our_client = False
        case.parties.all.return_value = [party]

        result = svc.build_our_parties(case)
        assert len(result) == 0


class TestBuildRespondents:
    def test_returns_opponents(self):
        from apps.cases.services.case.case_admin_service import CaseAdminService

        svc = CaseAdminService()
        case = MagicMock()
        party = MagicMock()
        party.client.id = 2
        party.client.name = "被告公司"
        party.client.is_our_client = False
        case.parties.all.return_value = [party]

        result = svc.build_respondents(case)
        assert len(result) == 1
        assert result[0]["name"] == "被告公司"


class TestBuildMaterialViewParties:
    def test_separates_our_and_opponent(self):
        from apps.cases.services.case.case_admin_service import CaseAdminService

        svc = CaseAdminService()
        case = MagicMock()

        our = MagicMock()
        our.client.name = "我方"
        our.client.is_our_client = True
        our.legal_status = "plaintiff"
        our.get_legal_status_display.return_value = "原告"
        our.id = 1

        opp = MagicMock()
        opp.client.name = "对方"
        opp.client.is_our_client = False
        opp.legal_status = "defendant"
        opp.get_legal_status_display.return_value = "被告"
        opp.id = 2

        case.parties.all.return_value = [our, opp]

        our_list, opp_list = svc.build_material_view_parties(case)
        assert len(our_list) == 1
        assert len(opp_list) == 1


class TestBuildMaterialViewAuthorities:
    def test_returns_authorities(self):
        from apps.cases.services.case.case_admin_service import CaseAdminService

        svc = CaseAdminService()
        case = MagicMock()
        auth = MagicMock()
        auth.id = 1
        auth.name = "北京市朝阳区法院"
        auth.authority_type = "court"
        auth.get_authority_type_display.return_value = "法院"
        case.supervising_authorities.all.return_value.order_by.return_value = [auth]

        result = svc.build_material_view_authorities(case)
        assert len(result) == 1
        assert result[0]["name"] == "北京市朝阳区法院"


class TestGroupTemplatesBySubType:
    def test_groups_and_orders(self):
        from apps.cases.services.case.case_admin_service import CaseAdminService

        svc = CaseAdminService()
        templates = [
            {"case_sub_type": "B", "name": "模板B"},
            {"case_sub_type": "A", "name": "模板A"},
            {"case_sub_type": "B", "name": "模板B2"},
        ]
        choices = [("A", "类型A"), ("B", "类型B")]

        result = svc.group_templates_by_sub_type(templates, choices)
        assert len(result) == 2
        # A should come before B based on choices order
        assert result[0][0] == "类型A"
        assert result[1][0] == "类型B"
        assert len(result[1][1]) == 2

    def test_excludes_special_sub_types(self):
        from apps.cases.services.case.case_admin_service import CaseAdminService

        svc = CaseAdminService()
        templates = [
            {"case_sub_type": "A", "name": "模板A"},
            {"case_sub_type": "power_of_attorney_materials", "name": "授权"},
        ]
        choices = [("A", "类型A"), ("power_of_attorney_materials", "授权材料")]

        result = svc.group_templates_by_sub_type(templates, choices, exclude_special_sub_types=True)
        assert len(result) == 1

    def test_includes_special_sub_types_when_disabled(self):
        from apps.cases.services.case.case_admin_service import CaseAdminService

        svc = CaseAdminService()
        templates = [
            {"case_sub_type": "A", "name": "模板A"},
            {"case_sub_type": "power_of_attorney_materials", "name": "授权"},
        ]
        choices = [("A", "类型A"), ("power_of_attorney_materials", "授权材料")]

        result = svc.group_templates_by_sub_type(templates, choices, exclude_special_sub_types=False)
        assert len(result) == 2


class TestDetectSpecialTemplateFlags:
    def test_detects_preservation(self):
        from apps.cases.services.case.case_admin_service import CaseAdminService

        svc = CaseAdminService()
        templates = [{"function_code": "preservation_application", "name": "财产保全申请书"}]
        has_pres, has_delay = svc.detect_special_template_flags(templates)
        assert has_pres is True
        assert has_delay is False

    def test_detects_delay_delivery(self):
        from apps.cases.services.case.case_admin_service import CaseAdminService

        svc = CaseAdminService()
        templates = [{"function_code": "delay_delivery_application", "name": "暂缓送达申请书"}]
        has_pres, has_delay = svc.detect_special_template_flags(templates)
        assert has_pres is False
        assert has_delay is True

    def test_no_special_templates(self):
        from apps.cases.services.case.case_admin_service import CaseAdminService

        svc = CaseAdminService()
        templates = [{"function_code": "other", "name": "其他模板"}]
        has_pres, has_delay = svc.detect_special_template_flags(templates)
        assert has_pres is False
        assert has_delay is False

    def test_detects_by_name(self):
        from apps.cases.services.case.case_admin_service import CaseAdminService

        svc = CaseAdminService()
        templates = [{"function_code": None, "name": "财产保全申请书"}]
        has_pres, _ = svc.detect_special_template_flags(templates)
        assert has_pres is True


class TestBuildMaterialsViewPayload:
    def test_builds_payload(self):
        from apps.cases.services.case.case_admin_service import CaseAdminService

        doc_svc = MagicMock()
        svc = CaseAdminService(document_service=doc_svc)

        case = MagicMock()
        case.id = 1
        case.parties.all.return_value = []
        case.supervising_authorities.all.return_value.order_by.return_value = []

        mat_svc = MagicMock()
        mat_svc.get_used_type_ids.return_value = [1, 2]
        mat_svc.get_material_types_by_category.return_value = []

        result = svc.build_materials_view_payload(case=case, material_service=mat_svc, law_firm_id=1)
        assert "party_types" in result
        assert "non_party_types" in result
        assert "our_parties" in result
        assert "opponent_parties" in result
        assert "authorities" in result


class TestHandleCaseFilingChange:
    @pytest.mark.django_db
    def test_case_not_found(self):
        from apps.cases.services.case.case_admin_service import CaseAdminService
        from apps.core.exceptions import NotFoundError

        svc = CaseAdminService()
        with pytest.raises(NotFoundError):
            svc.handle_case_filing_change(999999, is_filed=True)

    @pytest.mark.django_db
    def test_unfile_returns_none(self):
        from apps.cases.models import Case
        from apps.cases.services.case.case_admin_service import CaseAdminService

        case = Case.objects.create(name="Test Filing", filing_number="FC-001")
        svc = CaseAdminService()
        result = svc.handle_case_filing_change(case.id, is_filed=False)
        assert result is None

    @pytest.mark.django_db
    def test_filed_with_existing_number(self):
        from apps.cases.models import Case
        from apps.cases.services.case.case_admin_service import CaseAdminService

        case = Case.objects.create(name="Test Filing2", filing_number="FC-002")
        svc = CaseAdminService()
        result = svc.handle_case_filing_change(case.id, is_filed=True)
        assert result == "FC-002"

    @pytest.mark.django_db
    def test_filed_generates_new_number(self):
        from apps.cases.models import Case
        from apps.cases.services.case.case_admin_service import CaseAdminService

        case = Case.objects.create(name="Test Filing3", filing_number=None)
        filing_svc = MagicMock()
        filing_svc.generate_case_filing_number_internal.return_value = "FC-NEW-001"
        svc = CaseAdminService(filing_number_service=filing_svc)

        result = svc.handle_case_filing_change(case.id, is_filed=True)
        assert result == "FC-NEW-001"


class TestImportCasesFromJsonData:
    @pytest.mark.django_db
    def test_success_and_skip(self):
        from apps.cases.services.case.case_admin_service import CaseAdminService

        svc = CaseAdminService()
        import_svc = MagicMock()

        # First call: no existing case => success
        # Second call: existing case => skip
        import_one_calls = [MagicMock()]
        import_svc.import_one.side_effect = lambda data: None

        data = [
            {"filing_number": "FC-001", "name": "case1"},
            {"filing_number": "FC-002", "name": "case2"},
        ]

        # Create a case with FC-002 to test skip
        from apps.cases.models import Case
        Case.objects.create(name="existing", filing_number="FC-002")

        success, skipped, errors = svc.import_cases_from_json_data(data, case_import_service=import_svc)
        assert success + skipped == 2
        assert errors == []

    @pytest.mark.django_db
    def test_import_error(self):
        from apps.cases.services.case.case_admin_service import CaseAdminService

        svc = CaseAdminService()
        import_svc = MagicMock()
        import_svc.import_one.side_effect = RuntimeError("DB error")

        data = [{"filing_number": "FC-ERR-001", "name": "bad_case"}]
        success, skipped, errors = svc.import_cases_from_json_data(data, case_import_service=import_svc)
        assert success == 0
        assert len(errors) == 1
        assert "bad_case" in errors[0]
