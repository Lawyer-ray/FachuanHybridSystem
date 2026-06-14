"""case_party_mutation_service.py — round3 tests for uncovered branches.

Covers:
- create_party: success path with legal_status, case not found, client not found,
  party already exists, contract validation failure
- create_party_internal: success, case not found, party already exists
- delete_party: success, not found
- _validate_update_references: case not found, client not found
- _validate_update_uniqueness: no change returns, conflict
- validate_legal_status_compatibility: incompatible status, case not found
- validate_party_in_contract_scope: no contract, contract not found, party not in scope
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import ConflictError, NotFoundError, ValidationException


def _make_service(**deps):
    from apps.cases.services.party.case_party_mutation_service import CasePartyMutationService
    return CasePartyMutationService(
        client_service=deps.get("client_service", MagicMock()),
        contract_service=deps.get("contract_service", MagicMock()),
        repo=deps.get("repo", MagicMock()),
    )


# ── validate_party_in_contract_scope ──────────────────────────────────────────


class TestValidatePartyInContractScope:
    def test_no_contract_id(self):
        from types import SimpleNamespace
        svc = _make_service()
        svc.repo.get_case.return_value = SimpleNamespace(contract_id=None)
        assert svc.validate_party_in_contract_scope(1, 10) is True

    def test_contract_not_found(self):
        from types import SimpleNamespace
        svc = _make_service()
        svc.repo.get_case.return_value = SimpleNamespace(contract_id=1)
        svc.contract_service.get_all_parties.side_effect = NotFoundError("nf")
        with pytest.raises(ValidationException, match="关联合同不存在"):
            svc.validate_party_in_contract_scope(1, 10)

    def test_party_not_in_scope(self):
        from types import SimpleNamespace
        svc = _make_service()
        svc.repo.get_case.return_value = SimpleNamespace(contract_id=1)
        svc.contract_service.get_all_parties.return_value = [{"id": 99}]
        with pytest.raises(ValidationException, match="当事人必须属于"):
            svc.validate_party_in_contract_scope(1, 10)

    def test_case_not_found(self):
        svc = _make_service()
        svc.repo.get_case.return_value = None
        with pytest.raises(NotFoundError, match="案件不存在"):
            svc.validate_party_in_contract_scope(999, 10)


# ── validate_legal_status_compatibility ───────────────────────────────────────


class TestValidateLegalStatusCompat:
    @patch("apps.cases.services.party.case_party_mutation_service.business_config")
    @patch("apps.cases.models.Case")
    def test_case_not_found(self, MockCase, mock_config):
        MockCase.objects.filter.return_value.only.return_value.first.return_value = None
        svc = _make_service()
        with pytest.raises(NotFoundError, match="案件不存在"):
            svc.validate_legal_status_compatibility(case_id=999, legal_status="plaintiff")

    @patch("apps.cases.services.party.case_party_mutation_service.business_config")
    @patch("apps.cases.models.Case")
    def test_incompatible_status(self, MockCase, mock_config):
        MockCase.objects.filter.return_value.only.return_value.first.return_value = MagicMock()
        mock_config.is_legal_status_valid_for_case_type.return_value = False
        svc = _make_service()
        with pytest.raises(ValidationException, match="不适用于当前案件"):
            svc.validate_legal_status_compatibility(case_id=1, legal_status="bad_status")

    @patch("apps.cases.services.party.case_party_mutation_service.business_config")
    @patch("apps.cases.services.party.case_party_mutation_service.CaseParty")
    @patch("apps.cases.models.Case")
    def test_valid_status_without_client_id(self, MockCase, MockCP, mock_config):
        MockCase.objects.filter.return_value.only.return_value.first.return_value = MagicMock()
        mock_config.is_legal_status_valid_for_case_type.return_value = True
        svc = _make_service()
        result = svc.validate_legal_status_compatibility(case_id=1, legal_status="plaintiff_side")
        assert result is True


# ── create_party ──────────────────────────────────────────────────────────────


class TestCreateParty:
    @pytest.mark.django_db
    def test_case_not_found(self):
        svc = _make_service()
        svc.repo.get_case.return_value = None
        with pytest.raises(NotFoundError, match="案件不存在"):
            svc.create_party(case_id=999, client_id=1)

    @pytest.mark.django_db
    def test_client_not_found(self):
        svc = _make_service()
        svc.repo.get_case.return_value = MagicMock()
        svc.client_service.validate_client_exists.return_value = False
        with pytest.raises(NotFoundError, match="客户不存在"):
            svc.create_party(case_id=1, client_id=999)

    @pytest.mark.django_db
    def test_party_already_exists(self):
        svc = _make_service()
        svc.repo.get_case.return_value = MagicMock()
        svc.client_service.validate_client_exists.return_value = True
        svc.repo.party_exists.return_value = True
        with pytest.raises(ConflictError, match="当事人已存在"):
            svc.create_party(case_id=1, client_id=10)

    @pytest.mark.django_db
    def test_success_without_legal_status(self):
        svc = _make_service()
        case = MagicMock()
        case.contract_id = None
        svc.repo.get_case.return_value = case
        svc.client_service.validate_client_exists.return_value = True
        svc.repo.party_exists.return_value = False
        mock_party = MagicMock()
        mock_party.id = 1
        svc.repo.create_party.return_value = mock_party
        result = svc.create_party(case_id=1, client_id=10)
        assert result == mock_party

    @pytest.mark.django_db
    def test_success_with_legal_status(self):
        svc = _make_service()
        svc.repo.get_case.return_value = MagicMock()
        svc.client_service.validate_client_exists.return_value = True
        svc.repo.party_exists.return_value = False
        mock_party = MagicMock()
        mock_party.id = 1
        svc.repo.create_party.return_value = mock_party
        with patch.object(svc, "validate_legal_status_compatibility"):
            with patch.object(svc, "validate_party_in_contract_scope"):
                result = svc.create_party(case_id=1, client_id=10, legal_status="plaintiff")
                assert result == mock_party


# ── create_party_internal ─────────────────────────────────────────────────────


class TestCreatePartyInternal:
    @pytest.mark.django_db
    def test_case_not_found(self):
        svc = _make_service()
        svc.repo.get_case.return_value = None
        assert svc.create_party_internal(case_id=999, client_id=1) is False

    @pytest.mark.django_db
    def test_party_already_exists(self):
        svc = _make_service()
        svc.repo.get_case.return_value = MagicMock()
        svc.repo.party_exists.return_value = True
        assert svc.create_party_internal(case_id=1, client_id=10) is True

    @pytest.mark.django_db
    def test_success(self):
        svc = _make_service()
        svc.repo.get_case.return_value = MagicMock()
        svc.repo.party_exists.return_value = False
        assert svc.create_party_internal(case_id=1, client_id=10) is True
        svc.repo.create_party.assert_called_once()


# ── delete_party ──────────────────────────────────────────────────────────────


class TestDeleteParty:
    @pytest.mark.django_db
    def test_success(self):
        with patch("apps.cases.services.party.case_party_mutation_service.CaseParty") as MockCP:
            mock_party = MagicMock()
            mock_party.case_id = 1
            mock_party.client_id = 10
            MockCP.objects.filter.return_value.only.return_value.first.return_value = mock_party
            svc = _make_service()
            result = svc.delete_party(party_id=1)
            assert result == {"success": True}
            mock_party.delete.assert_called_once()

    @pytest.mark.django_db
    def test_not_found(self):
        with patch("apps.cases.services.party.case_party_mutation_service.CaseParty") as MockCP:
            MockCP.objects.filter.return_value.only.return_value.first.return_value = None
            svc = _make_service()
            with pytest.raises(NotFoundError, match="当事人不存在"):
                svc.delete_party(party_id=999)


# ── _validate_update_references ───────────────────────────────────────────────


class TestValidateUpdateReferences:
    def test_case_not_found(self):
        svc = _make_service()
        party = MagicMock()
        party.case_id = 1
        party.client_id = 10
        svc.repo.get_case.return_value = None
        with pytest.raises(NotFoundError, match="案件不存在"):
            svc._validate_update_references({"case_id": 2}, party)

    def test_client_not_found(self):
        svc = _make_service()
        party = MagicMock()
        party.case_id = 1
        party.client_id = 10
        svc.repo.get_case.return_value = MagicMock()
        svc.client_service.validate_client_exists.return_value = False
        with pytest.raises(NotFoundError, match="客户不存在"):
            svc._validate_update_references({"client_id": 20}, party)

    def test_no_change(self):
        svc = _make_service()
        party = MagicMock()
        party.case_id = 1
        party.client_id = 10
        # No case_id or client_id in data, or same values
        svc._validate_update_references({}, party)


# ── _validate_update_uniqueness ───────────────────────────────────────────────


class TestValidateUpdateUniqueness:
    def test_no_change_returns(self):
        svc = _make_service()
        party = MagicMock()
        party.case_id = 1
        party.client_id = 10
        # Same values, should return without querying
        svc._validate_update_uniqueness(1, party, 1, 10)

    def test_conflict_raises(self):
        svc = _make_service()
        party = MagicMock()
        party.case_id = 1
        party.client_id = 10
        with patch("apps.cases.services.party.case_party_mutation_service.CaseParty") as MockCP:
            MockCP.objects.filter.return_value.exclude.return_value.exists.return_value = True
            with pytest.raises(ConflictError, match="当事人已存在"):
                svc._validate_update_uniqueness(1, party, 1, 20)
