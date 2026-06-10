"""Fee Notice API integration tests."""

from __future__ import annotations

import json

from unittest.mock import patch, MagicMock

import pytest

from apps.contracts.models import Contract
from apps.cases.models import Case


@pytest.mark.django_db
def test_extract_fee_notice_no_files(authenticated_client):
    resp = authenticated_client.post("/api/v1/fee-notice/extract")
    assert resp.status_code in (400, 422)


@pytest.mark.django_db
def test_search_cases(authenticated_client):
    contract = Contract.objects.create(name="费用比对合同", case_type="civil")
    Case.objects.create(name="费用比对案件", contract=contract)
    resp = authenticated_client.get("/api/v1/fee-notice/cases/search", {"keyword": "费用比对"})
    assert resp.status_code == 200
    data = resp.json()
    assert "cases" in data
    assert isinstance(data["cases"], list)


@pytest.mark.django_db
def test_compare_fee(authenticated_client):
    contract = Contract.objects.create(name="比对合同", case_type="civil")
    case = Case.objects.create(
        name="比对案件",
        contract=contract,
        target_amount=100000,
        preservation_amount=50000,
    )
    with patch("apps.fee_notice.services.FeeComparisonService.compare_fee") as mock_compare:
        mock_result = MagicMock()
        mock_result.case_info = MagicMock(
            case_id=case.id,
            case_name="比对案件",
            case_number="",
            cause_of_action_name="借款合同纠纷",
            target_amount=100000,
            preservation_amount=50000,
        )
        mock_result.extracted_acceptance_fee = 2300.0
        mock_result.extracted_preservation_fee = 520.0
        mock_result.calculated_acceptance_fee = 2300.0
        mock_result.calculated_acceptance_fee_half = 1150.0
        mock_result.calculated_preservation_fee = 520.0
        mock_result.acceptance_fee_match = True
        mock_result.acceptance_fee_close = False
        mock_result.acceptance_fee_diff = 0.0
        mock_result.preservation_fee_match = True
        mock_result.preservation_fee_close = False
        mock_result.preservation_fee_diff = 0.0
        mock_result.can_compare = True
        mock_result.message = "费用一致"
        mock_compare.return_value = mock_result

        resp = authenticated_client.post(
            "/api/v1/fee-notice/compare",
            data=json.dumps({
                "case_id": case.id,
                "extracted_acceptance_fee": "2300.00",
                "extracted_preservation_fee": "520.00",
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["case_id"] == case.id
        assert data["acceptance_fee_match"] is True
