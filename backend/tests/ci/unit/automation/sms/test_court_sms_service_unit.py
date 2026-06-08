"""court_sms_service.py 单元测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


class TestCourtSMSService:

    def _make_service(self):
        from apps.automation.services.sms.court_sms_service import CourtSMSService
        parser = MagicMock()
        matcher = MagicMock()
        return CourtSMSService(parser=parser, matcher=matcher), parser, matcher

    def test_init_stores_dependencies(self):
        from apps.automation.services.sms.court_sms_service import CourtSMSService
        parser = MagicMock()
        matcher = MagicMock()
        svc = CourtSMSService(parser=parser, matcher=matcher)
        assert svc.parser is parser
        assert svc._matcher is matcher

    def test_submit_sms_rejects_empty_content(self):
        from apps.automation.services.sms.court_sms_service import CourtSMSService
        from apps.core.exceptions import ValidationException
        svc, _, _ = self._make_service()
        with pytest.raises(ValidationException, match="不能为空"):
            svc.submit_sms("")

    @pytest.mark.django_db
    def test_assign_case_raises_when_sms_not_found(self):
        from apps.automation.services.sms.court_sms_service import CourtSMSService
        from apps.core.exceptions import NotFoundError
        svc, _, _ = self._make_service()
        with patch("apps.automation.services.sms.court_sms_service.CourtSMS") as MockSMS:
            MockSMS.DoesNotExist = type("DoesNotExist", (Exception,), {})
            MockSMS.objects.get.side_effect = MockSMS.DoesNotExist()
            with pytest.raises(NotFoundError):
                svc.assign_case(999, 1)

    @pytest.mark.django_db
    def test_retry_processing_raises_when_sms_not_found(self):
        from apps.automation.services.sms.court_sms_service import CourtSMSService
        from apps.core.exceptions import NotFoundError
        svc, _, _ = self._make_service()
        with patch("apps.automation.services.sms.court_sms_service.CourtSMS") as MockSMS:
            MockSMS.DoesNotExist = type("DoesNotExist", (Exception,), {})
            MockSMS.objects.get.side_effect = MockSMS.DoesNotExist()
            with pytest.raises(NotFoundError):
                svc.retry_processing(999)

    @pytest.mark.django_db
    def test_delete_sms_raises_when_not_found(self):
        from apps.automation.services.sms.court_sms_service import CourtSMSService
        from apps.core.exceptions import NotFoundError
        svc, _, _ = self._make_service()
        with patch("apps.automation.services.sms.court_sms_service.CourtSMS") as MockSMS:
            MockSMS.DoesNotExist = type("DoesNotExist", (Exception,), {})
            MockSMS.objects.get.side_effect = MockSMS.DoesNotExist()
            with pytest.raises(NotFoundError):
                svc.delete_sms(999)

    def test_get_sms_detail_raises_when_not_found(self):
        from apps.automation.services.sms.court_sms_service import CourtSMSService
        from apps.core.exceptions import NotFoundError
        svc, _, _ = self._make_service()
        with patch("apps.automation.services.sms.court_sms_service.CourtSMS") as MockSMS:
            MockSMS.DoesNotExist = type("DoesNotExist", (Exception,), {})
            MockSMS.objects.select_related.return_value.prefetch_related.return_value.get.side_effect = MockSMS.DoesNotExist
            with pytest.raises(NotFoundError):
                svc.get_sms_detail(999)

    def test_has_renamed_documents_returns_false_when_no_task(self):
        from apps.automation.services.sms.court_sms_service import CourtSMSService
        svc, _, _ = self._make_service()
        sms = SimpleNamespace(scraper_task=None)
        assert svc._has_renamed_documents(sms) is False

    def test_has_renamed_documents_returns_false_when_no_result(self):
        from apps.automation.services.sms.court_sms_service import CourtSMSService
        svc, _, _ = self._make_service()
        sms = SimpleNamespace(scraper_task=SimpleNamespace(result=None))
        assert svc._has_renamed_documents(sms) is False

    def test_has_renamed_documents_returns_false_when_empty_files(self):
        from apps.automation.services.sms.court_sms_service import CourtSMSService
        svc, _, _ = self._make_service()
        sms = SimpleNamespace(scraper_task=SimpleNamespace(result={"renamed_files": []}))
        assert svc._has_renamed_documents(sms) is False
