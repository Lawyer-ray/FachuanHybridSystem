"""Tests for apps.automation.dtos and various schema files."""

from __future__ import annotations

from datetime import datetime

import pytest

from apps.automation.dtos import CaptchaRecognizeResultDTO, CourtTokenDTO


class TestCaptchaRecognizeResultDTO:
    def test_success(self):
        dto = CaptchaRecognizeResultDTO(success=True, text="abc", processing_time=1.5, error=None)
        assert dto.success is True
        assert dto.text == "abc"

    def test_failure(self):
        dto = CaptchaRecognizeResultDTO(success=False, text=None, processing_time=0.0, error="timeout")
        assert dto.error == "timeout"

    def test_frozen(self):
        dto = CaptchaRecognizeResultDTO(success=True, text="x", processing_time=0.1, error=None)
        with pytest.raises(AttributeError):
            dto.success = False  # type: ignore[misc]


class TestCourtTokenDTO:
    def test_creation(self):
        dt = datetime(2024, 1, 1)
        dto = CourtTokenDTO(
            site_name="court",
            account="user",
            token="tok123",
            token_type="jwt",
            expires_at=dt,
            created_at=dt,
            updated_at=dt,
        )
        assert dto.token == "tok123"
        assert dto.site_name == "court"

    def test_frozen(self):
        dto = CourtTokenDTO("s", "a", "t", "jwt", None, None, None)
        with pytest.raises(AttributeError):
            dto.token = "new"  # type: ignore[misc]


class TestCourtSMSSchemas:
    def test_sms_parse_result(self):
        from apps.automation.schemas.court_sms import SMSParseResult
        result = SMSParseResult(
            sms_type="document",
            download_links=["http://example.com"],
            case_numbers=["(2024)001"],
            party_names=["Alice"],
            has_valid_download_link=True,
        )
        assert result.sms_type == "document"
        assert result.has_valid_download_link is True

    def test_court_sms_submit_in_validation(self):
        from apps.automation.schemas.court_sms import CourtSMSSubmitIn
        # Valid
        sms = CourtSMSSubmitIn(content="  hello  ")
        assert sms.content == "hello"

    def test_court_sms_submit_in_empty_content(self):
        from apps.automation.schemas.court_sms import CourtSMSSubmitIn
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            CourtSMSSubmitIn(content="")

    def test_court_sms_submit_in_whitespace_content(self):
        from apps.automation.schemas.court_sms import CourtSMSSubmitIn
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            CourtSMSSubmitIn(content="   ")

    def test_batch_delete_in(self):
        from apps.automation.schemas.court_sms import CourtSMSBatchDeleteIn
        batch = CourtSMSBatchDeleteIn(ids=[1, 2, 3])
        assert len(batch.ids) == 3

    def test_batch_delete_in_empty(self):
        from apps.automation.schemas.court_sms import CourtSMSBatchDeleteIn
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            CourtSMSBatchDeleteIn(ids=[])

    def test_assign_case_in(self):
        from apps.automation.schemas.court_sms import CourtSMSAssignCaseIn
        assign = CourtSMSAssignCaseIn(case_id=42)
        assert assign.case_id == 42
