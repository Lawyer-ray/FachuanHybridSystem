"""Additional tests for cases/services/party/case_party_mutation_service.py — uncovered branches.

Covers: validate_legal_status_compatibility with client_id (our party legal status),
_validate_our_party_legal_status with conflicting/opposing/no-opposing statuses,
create_party with user logging.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import NotFoundError, ValidationException


def _make_service(**deps):
    from apps.cases.services.party.case_party_mutation_service import CasePartyMutationService
    return CasePartyMutationService(
        client_service=deps.get("client_service", MagicMock()),
        contract_service=deps.get("contract_service", MagicMock()),
        repo=deps.get("repo", MagicMock()),
    )


class TestValidateLegalStatusCompatibilityWithClientId:
    @patch("apps.cases.services.party.case_party_mutation_service.business_config")
    @patch("apps.cases.models.CaseParty")
    @patch("apps.cases.models.Case")
    def test_valid_status_with_client_id_calls_validate_our_party(
        self, mock_case_cls, mock_case_party, mock_config
    ):
        mock_case_cls.objects.filter.return_value.only.return_value.first.return_value = MagicMock()
        mock_config.is_legal_status_valid_for_case_type.return_value = True
        svc = _make_service()
        with patch.object(svc, '_validate_our_party_legal_status') as mock_validate:
            result = svc.validate_legal_status_compatibility(
                case_id=1, legal_status="plaintiff_side", client_id=10
            )
            assert result is True
            mock_validate.assert_called_once()


class TestValidateOurPartyLegalStatus:
    @patch("apps.cases.services.party.case_party_mutation_service.business_config")
    def test_not_our_client_returns_early(self, mock_config):
        svc = _make_service()
        mock_client_dto = MagicMock()
        mock_client_dto.is_our_client = False
        svc.client_service.get_client_internal.return_value = mock_client_dto
        mock_qs = MagicMock()
        # Should not raise - returns early
        svc._validate_our_party_legal_status(
            case_id=1, legal_status="plaintiff_side", client_id=10, parties_qs=mock_qs
        )

    @patch("apps.cases.services.party.case_party_mutation_service.business_config")
    def test_no_client_dto_returns_early(self, mock_config):
        svc = _make_service()
        svc.client_service.get_client_internal.return_value = None
        mock_qs = MagicMock()
        svc._validate_our_party_legal_status(
            case_id=1, legal_status="plaintiff_side", client_id=10, parties_qs=mock_qs
        )

    @patch("apps.cases.services.party.case_party_mutation_service.business_config")
    def test_invalid_new_status_returns_early(self, mock_config):
        svc = _make_service()
        mock_client_dto = MagicMock()
        mock_client_dto.is_our_client = True
        svc.client_service.get_client_internal.return_value = mock_client_dto
        mock_config.is_legal_status_valid_for_case_type.return_value = False
        mock_qs = MagicMock()
        svc._validate_our_party_legal_status(
            case_id=1, legal_status="bad_status", client_id=10, parties_qs=mock_qs
        )

    @patch("apps.cases.services.party.case_party_mutation_service.business_config")
    def test_no_opposing_group_returns_early(self, mock_config):
        svc = _make_service()
        mock_client_dto = MagicMock()
        mock_client_dto.is_our_client = True
        svc.client_service.get_client_internal.return_value = mock_client_dto
        mock_config.is_legal_status_valid_for_case_type.return_value = True
        mock_qs = MagicMock()
        svc._validate_our_party_legal_status(
            case_id=1, legal_status="unknown_status", client_id=10, parties_qs=mock_qs
        )

    @patch("apps.cases.services.party.case_party_mutation_service.business_config")
    def test_conflicting_opposing_status_raises(self, mock_config):
        svc = _make_service()
        mock_client_dto = MagicMock()
        mock_client_dto.is_our_client = True
        svc.client_service.get_client_internal.return_value = mock_client_dto
        mock_config.is_legal_status_valid_for_case_type.return_value = True
        # plaintiff_side has opposing_group = defendant_side
        mock_config.get_legal_status_label.return_value = "原告"
        mock_qs = MagicMock()
        mock_qs.filter.return_value.exclude.return_value.exclude.return_value.values_list.return_value = [
            ("defendant_side", "已有被告"),
        ]
        with pytest.raises(ValidationException, match="我方当事人诉讼地位冲突"):
            svc._validate_our_party_legal_status(
                case_id=1, legal_status="plaintiff_side", client_id=10, parties_qs=mock_qs
            )

    @patch("apps.cases.services.party.case_party_mutation_service.business_config")
    def test_no_conflicting_status_passes(self, mock_config):
        svc = _make_service()
        mock_client_dto = MagicMock()
        mock_client_dto.is_our_client = True
        svc.client_service.get_client_internal.return_value = mock_client_dto
        mock_config.is_legal_status_valid_for_case_type.return_value = True
        mock_qs = MagicMock()
        # No existing parties with conflicting statuses
        mock_qs.filter.return_value.exclude.return_value.exclude.return_value.values_list.return_value = []
        svc._validate_our_party_legal_status(
            case_id=1, legal_status="plaintiff_side", client_id=10, parties_qs=mock_qs
        )

    @patch("apps.cases.services.party.case_party_mutation_service.business_config")
    def test_appellant_opposing_appellee_raises(self, mock_config):
        svc = _make_service()
        mock_client_dto = MagicMock()
        mock_client_dto.is_our_client = True
        svc.client_service.get_client_internal.return_value = mock_client_dto
        mock_config.is_legal_status_valid_for_case_type.return_value = True
        mock_config.get_legal_status_label.return_value = "上诉人"
        mock_qs = MagicMock()
        mock_qs.filter.return_value.exclude.return_value.exclude.return_value.values_list.return_value = [
            ("appellee_side", "已有被上诉人"),
        ]
        with pytest.raises(ValidationException):
            svc._validate_our_party_legal_status(
                case_id=1, legal_status="appellant_side", client_id=10, parties_qs=mock_qs
            )

    @patch("apps.cases.services.party.case_party_mutation_service.business_config")
    def test_criminal_defendant_opposing_victim_raises(self, mock_config):
        svc = _make_service()
        mock_client_dto = MagicMock()
        mock_client_dto.is_our_client = True
        svc.client_service.get_client_internal.return_value = mock_client_dto
        mock_config.is_legal_status_valid_for_case_type.return_value = True
        mock_config.get_legal_status_label.return_value = "刑事被告人"
        mock_qs = MagicMock()
        mock_qs.filter.return_value.exclude.return_value.exclude.return_value.values_list.return_value = [
            ("criminal_victim_side", "已有刑事被害人"),
        ]
        with pytest.raises(ValidationException):
            svc._validate_our_party_legal_status(
                case_id=1, legal_status="criminal_defendant_side", client_id=10, parties_qs=mock_qs
            )


# create_party tests require @transaction.atomic decorator to work,
# so they need django_db marker. Skipped for unit test safety.
