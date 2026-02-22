from __future__ import annotations

from apps.automation.services.sms.case_number_extractor_service import CaseNumberExtractorService


class _StubProvider:
    def __init__(self, text: str):
        self.text = text

    def extract(self, *, content: str) -> str:
        return self.text


class _StubCaseNumberService:
    def normalize_case_number(self, case_number: str) -> str:
        return case_number.replace("（", "(").replace("）", ")").replace(" ", "")


def test_extract_from_content_parses_json_and_deduplicates():
    provider = _StubProvider('{"case_numbers": ["(2024)粤0604民初12345号", "（2024）粤0604民初12345号"]}')
    svc = CaseNumberExtractorService(extraction_provider=provider, case_number_service=_StubCaseNumberService())  # type: ignore[arg-type]
    result = svc.extract_from_content("x")
    assert len(result) == 1
    assert result[0].endswith("号")


def test_extract_from_content_falls_back_when_non_json():
    provider = _StubProvider("案号：(2024)粤0604民初12345号")
    svc = CaseNumberExtractorService(extraction_provider=provider, case_number_service=_StubCaseNumberService())  # type: ignore[arg-type]
    result = svc.extract_from_content("x")
    assert result and result[0].endswith("号")
