"""Regression tests for enforcement party ordinal labels."""

from __future__ import annotations

from apps.core.models.enums import LegalStatus
from apps.documents.services.placeholders.litigation.enforcement_party_service import (
    EnforcementApplicantPartyService,
    EnforcementRespondentPartyService,
)


class _AccessorStub:
    def __init__(self, parties: list[dict[str, str]]) -> None:
        self._parties = parties

    def get_case_parties(self, case_id: int) -> list[dict[str, str]]:
        return self._parties


def _build_legal_party(name: str, status: str) -> dict[str, str]:
    return {
        "legal_status": status,
        "client_type": "legal",
        "client_name": name,
        "address": "广东省广州市天河区",
        "id_number": "91440101MA00000000",
        "legal_representative": "张三",
        "phone": "13800000000",
    }


def test_respondent_info_uses_chinese_numerals_for_multiple_parties() -> None:
    service = EnforcementRespondentPartyService()
    service.case_details_accessor = _AccessorStub(
        [
            _build_legal_party("第一公司", LegalStatus.DEFENDANT),
            _build_legal_party("第二公司", LegalStatus.RESPONDENT),
        ]
    )

    text = service.generate_respondent_info(case_id=12)

    assert "被申请人一：第一公司" in text
    assert "被申请人二：第二公司" in text
    assert "被申请人丁" not in text


def test_applicant_info_uses_chinese_numerals_for_multiple_parties() -> None:
    service = EnforcementApplicantPartyService()
    service.case_details_accessor = _AccessorStub(
        [
            _build_legal_party("甲公司", LegalStatus.PLAINTIFF),
            _build_legal_party("乙公司", LegalStatus.APPLICANT),
        ]
    )

    text = service.generate_applicant_info(case_id=12)

    assert "申请人一：甲公司" in text
    assert "申请人二：乙公司" in text
    assert "申请人丁" not in text
