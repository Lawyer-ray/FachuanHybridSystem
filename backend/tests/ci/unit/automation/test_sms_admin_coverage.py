"""Court SMS Admin Actions 测试 - 覆盖 CourtSMSAdminActions"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.http import JsonResponse

from apps.automation.admin.sms.court_sms_admin_actions import CourtSMSAdminActions
from apps.automation.models import CourtSMS

User = get_user_model()


def _make_request(method="GET", path="/admin/", data=None):
    factory = RequestFactory()
    if method == "GET":
        request = factory.get(path, data or {})
    else:
        request = factory.post(path, data or {})
    request.user = User(is_superuser=True, is_staff=True)
    return request


@pytest.mark.django_db
class TestCourtSMSAdminActionsSubmitSmsView:
    """测试 submit_sms_view"""

    def test_submit_sms_view_get(self):
        mixin = CourtSMSAdminActions()
        mixin.model = MagicMock()
        mixin.model._meta = MagicMock()
        request = _make_request(method="GET")
        with patch("apps.automation.admin.sms.court_sms_admin_actions.render") as mock_render:
            mock_render.return_value = MagicMock(status_code=200)
            result = mixin.submit_sms_view(request)
            assert result.status_code == 200

    def test_submit_sms_view_post_empty_content(self):
        from django.test import Client

        mixin = CourtSMSAdminActions()
        mixin.model = MagicMock()
        mixin.model._meta = MagicMock()
        # Use a request that includes messages middleware
        with patch("apps.automation.admin.sms.court_sms_admin_actions.messages"):
            request = _make_request(method="POST", data={"content": ""})
            with patch("apps.automation.admin.sms.court_sms_admin_actions.render") as mock_render:
                mock_render.return_value = MagicMock(status_code=200)
                result = mixin.submit_sms_view(request)
                assert result.status_code == 200

    def test_submit_sms_view_post_success(self):
        mixin = CourtSMSAdminActions()
        mixin.model = MagicMock()
        mixin.model._meta = MagicMock()
        with patch("apps.automation.admin.sms.court_sms_admin_actions.messages"):
            request = _make_request(method="POST", data={"content": "法院短信内容"})
            with patch("apps.automation.admin.sms.court_sms_admin_actions._get_court_sms_service") as mock_svc:
                mock_sms = MagicMock()
                mock_sms.id = 1
                mock_svc.return_value.submit_sms.return_value = mock_sms
                with patch("apps.automation.admin.sms.court_sms_admin_actions.reverse", return_value="/admin/change/1/"):
                    result = mixin.submit_sms_view(request)
                    assert result.status_code == 302


@pytest.mark.django_db
class TestCourtSMSAdminActionsSearchCasesAjax:
    """测试 search_cases_ajax"""

    def test_search_cases_ajax_not_get(self):
        mixin = CourtSMSAdminActions()
        request = _make_request(method="POST")
        result = mixin.search_cases_ajax(request, sms_id=1)
        assert result.status_code == 405

    def test_search_cases_ajax_empty_query(self):
        import json as json_mod

        mixin = CourtSMSAdminActions()
        request = _make_request(method="GET", data={"q": ""})
        result = mixin.search_cases_ajax(request, sms_id=1)
        assert result.status_code == 200
        data = json_mod.loads(result.content)
        assert data["cases"] == []

    def test_search_cases_ajax_with_results(self):
        mixin = CourtSMSAdminActions()
        request = _make_request(method="GET", data={"q": "张三"})
        with patch("apps.automation.admin.sms.court_sms_admin_actions._get_case_service") as mock_svc:
            mock_case = MagicMock()
            mock_case.id = 1
            mock_svc.return_value.search_cases_by_party_internal.return_value = [mock_case]
            mock_svc.return_value.search_cases_by_case_number_internal.return_value = []

            mock_detail = MagicMock()
            mock_detail.id = 1
            mock_detail.name = "张三案"
            mock_detail.case_numbers = []
            mock_detail.parties = []
            mock_detail.created_at = None
            mock_svc.return_value.get_case_detail_internal.return_value = mock_detail

            result = mixin.search_cases_ajax(request, sms_id=1)
            assert result.status_code == 200

    def test_search_cases_ajax_exception(self):
        mixin = CourtSMSAdminActions()
        request = _make_request(method="GET", data={"q": "test"})
        with patch("apps.automation.admin.sms.court_sms_admin_actions._get_case_service") as mock_svc:
            mock_svc.return_value.search_cases_by_party_internal.side_effect = Exception("DB error")
            result = mixin.search_cases_ajax(request, sms_id=1)
            assert result.status_code == 500


@pytest.mark.django_db
class TestCourtSMSAdminActionsFormatCase:
    """测试 _format_case_for_template"""

    def test_format_case_orm_object(self):
        mixin = CourtSMSAdminActions()
        case_dto = MagicMock()
        case_dto.id = 1
        case_dto.name = "测试案件"
        case_dto.created_at = None
        case_dto.case_numbers = MagicMock()
        case_dto.parties = MagicMock()
        result = mixin._format_case_for_template(case_dto)
        assert result["id"] == 1
        assert result["name"] == "测试案件"

    def test_format_case_dto_fallback(self):
        mixin = CourtSMSAdminActions()
        case_dto = MagicMock(spec=["id", "name"])
        case_dto.id = 1
        case_dto.name = "测试案件"
        with patch("apps.automation.admin.sms.court_sms_admin_actions.CourtSMS") as MockSMS:
            pass
        result = mixin._format_case_for_template(case_dto)
        assert result["id"] == 1


@pytest.mark.django_db
class TestCourtSMSAdminActionsGetSuggestedCases:
    """测试 _get_suggested_cases"""

    def test_get_suggested_cases_empty(self):
        mixin = CourtSMSAdminActions()
        sms = MagicMock()
        sms.party_names = []
        sms.case_numbers = []
        case_service = MagicMock()
        result = mixin._get_suggested_cases(sms, case_service, sms_id=1)
        assert result == []

    def test_get_suggested_cases_with_party(self):
        mixin = CourtSMSAdminActions()
        sms = MagicMock()
        sms.party_names = ["张三"]
        sms.case_numbers = []
        case_service = MagicMock()
        mock_case = MagicMock()
        mock_case.id = 1
        case_service.search_cases_by_party_internal.return_value = [mock_case]
        result = mixin._get_suggested_cases(sms, case_service, sms_id=1)
        assert len(result) == 1

    def test_get_suggested_cases_dedup(self):
        mixin = CourtSMSAdminActions()
        sms = MagicMock()
        sms.party_names = ["张三"]
        sms.case_numbers = ["(2025)民初1号"]
        case_service = MagicMock()
        mock_case = MagicMock()
        mock_case.id = 1
        case_service.search_cases_by_party_internal.return_value = [mock_case]
        case_service.search_cases_by_case_number_internal.return_value = [mock_case]
        result = mixin._get_suggested_cases(sms, case_service, sms_id=1)
        assert len(result) == 1  # deduplicated

    def test_get_suggested_cases_exception(self):
        mixin = CourtSMSAdminActions()
        sms = MagicMock()
        sms.party_names = ["张三"]
        sms.case_numbers = []
        case_service = MagicMock()
        case_service.search_cases_by_party_internal.side_effect = Exception("Error")
        result = mixin._get_suggested_cases(sms, case_service, sms_id=1)
        assert result == []


@pytest.mark.django_db
class TestCourtSMSAdminActionsRecommendations:
    """测试 recommendations_ajax"""

    def test_recommendations_ajax_not_get(self):
        mixin = CourtSMSAdminActions()
        request = _make_request(method="POST")
        result = mixin.recommendations_ajax(request, sms_id=1)
        assert result.status_code == 405
