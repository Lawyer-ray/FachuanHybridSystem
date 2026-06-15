"""Unit tests for cases.services.party.case_party_mutation_service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.core.exceptions import ConflictError, NotFoundError, ValidationException




class TestCasePartyMutationServiceValidatePartyInContractScope:
    """validate_party_in_contract_scope tests."""

    def _make_service(self, **deps):
        from apps.cases.services.party.case_party_mutation_service import CasePartyMutationService

        client_service = deps.get("client_service", MagicMock())
        contract_service = deps.get("contract_service", MagicMock())
        repo = deps.get("repo", MagicMock())
        return CasePartyMutationService(
            client_service=client_service,
            contract_service=contract_service,
            repo=repo,
        )

    def test_case_not_found(self) -> None:
        repo = MagicMock()
        repo.get_case.return_value = None
        svc = self._make_service(repo=repo)
        with pytest.raises(NotFoundError, match="案件不存在"):
            svc.validate_party_in_contract_scope(case_id=1, client_id=10)

    def test_case_without_contract_returns_true(self) -> None:
        repo = MagicMock()
        case = MagicMock()
        case.contract_id = None
        repo.get_case.return_value = case
        svc = self._make_service(repo=repo)
        assert svc.validate_party_in_contract_scope(case_id=1, client_id=10) is True

    def test_contract_not_found_raises_validation(self) -> None:
        from apps.core.exceptions import NotFoundError

        repo = MagicMock()
        case = MagicMock()
        case.contract_id = 99
        repo.get_case.return_value = case
        contract_service = MagicMock()
        contract_service.get_all_parties.side_effect = NotFoundError("not found")
        svc = self._make_service(repo=repo, contract_service=contract_service)
        with pytest.raises(ValidationException, match="关联合同不存在"):
            svc.validate_party_in_contract_scope(case_id=1, client_id=10)

    def test_party_not_in_contract_scope(self) -> None:
        repo = MagicMock()
        case = MagicMock()
        case.contract_id = 99
        repo.get_case.return_value = case
        contract_service = MagicMock()
        contract_service.get_all_parties.return_value = [{"id": 1}, {"id": 2}]
        svc = self._make_service(repo=repo, contract_service=contract_service)
        with pytest.raises(ValidationException, match="当事人必须属于绑定合同"):
            svc.validate_party_in_contract_scope(case_id=1, client_id=999)

    def test_party_in_scope_returns_true(self) -> None:
        repo = MagicMock()
        case = MagicMock()
        case.contract_id = 99
        repo.get_case.return_value = case
        contract_service = MagicMock()
        contract_service.get_all_parties.return_value = [{"id": 10}, {"id": 20}]
        svc = self._make_service(repo=repo, contract_service=contract_service)
        assert svc.validate_party_in_contract_scope(case_id=1, client_id=10) is True


class TestCasePartyMutationServiceValidateLegalStatusCompatibility:
    """validate_legal_status_compatibility tests."""

    def _make_service(self, **deps):
        from apps.cases.services.party.case_party_mutation_service import CasePartyMutationService

        client_service = deps.get("client_service", MagicMock())
        contract_service = deps.get("contract_service", MagicMock())
        repo = deps.get("repo", MagicMock())
        return CasePartyMutationService(
            client_service=client_service,
            contract_service=contract_service,
            repo=repo,
        )

    @patch("apps.cases.services.party.case_party_mutation_service.business_config")
    @patch("apps.cases.models.Case")
    def test_case_not_found(self, mock_case_cls, mock_config) -> None:
        mock_case_cls.objects.filter.return_value.only.return_value.first.return_value = None
        svc = self._make_service()
        with pytest.raises(NotFoundError, match="案件不存在"):
            svc.validate_legal_status_compatibility(case_id=1, legal_status="plaintiff_side")

    @patch("apps.cases.services.party.case_party_mutation_service.business_config")
    @patch("apps.cases.models.Case")
    def test_incompatible_status_raises(self, mock_case_cls, mock_config) -> None:
        mock_case_cls.objects.filter.return_value.only.return_value.first.return_value = MagicMock()
        mock_config.is_legal_status_valid_for_case_type.return_value = False
        svc = self._make_service()
        with pytest.raises(ValidationException, match="不适用于当前案件"):
            svc.validate_legal_status_compatibility(case_id=1, legal_status="bad_status")

    @patch("apps.cases.services.party.case_party_mutation_service.business_config")
    @patch("apps.cases.services.party.case_party_mutation_service.CaseParty")
    @patch("apps.cases.models.Case")
    def test_compatible_status_returns_true(self, mock_case_cls, mock_case_party, mock_config) -> None:
        mock_case_cls.objects.filter.return_value.only.return_value.first.return_value = MagicMock()
        mock_config.is_legal_status_valid_for_case_type.return_value = True
        svc = self._make_service()
        assert svc.validate_legal_status_compatibility(case_id=1, legal_status="plaintiff_side") is True


@pytest.mark.django_db
class TestCasePartyMutationServiceCreateParty:
    """create_party tests."""

    def _make_service(self, **deps):
        from apps.cases.services.party.case_party_mutation_service import CasePartyMutationService

        client_service = deps.get("client_service", MagicMock())
        contract_service = deps.get("contract_service", MagicMock())
        repo = deps.get("repo", MagicMock())
        return CasePartyMutationService(
            client_service=client_service,
            contract_service=contract_service,
            repo=repo,
        )

    def test_case_not_found(self) -> None:
        repo = MagicMock()
        repo.get_case.return_value = None
        svc = self._make_service(repo=repo)
        with pytest.raises(NotFoundError, match="案件不存在"):
            svc.create_party(case_id=1, client_id=10)

    def test_client_not_found(self) -> None:
        repo = MagicMock()
        repo.get_case.return_value = MagicMock()
        client_service = MagicMock()
        client_service.validate_client_exists.return_value = False
        svc = self._make_service(repo=repo, client_service=client_service)
        with pytest.raises(NotFoundError, match="客户不存在"):
            svc.create_party(case_id=1, client_id=10)

    def test_party_already_exists(self) -> None:
        repo = MagicMock()
        repo.get_case.return_value = MagicMock()
        client_service = MagicMock()
        client_service.validate_client_exists.return_value = True
        repo.party_exists.return_value = True
        svc = self._make_service(repo=repo, client_service=client_service)
        with pytest.raises(ConflictError, match="当事人已存在"):
            svc.create_party(case_id=1, client_id=10)

    def test_successful_creation(self) -> None:
        repo = MagicMock()
        case = MagicMock()
        case.contract_id = None
        repo.get_case.return_value = case
        client_service = MagicMock()
        client_service.validate_client_exists.return_value = True
        repo.party_exists.return_value = False
        expected_party = MagicMock()
        expected_party.id = 1
        repo.create_party.return_value = expected_party
        svc = self._make_service(repo=repo, client_service=client_service)
        with (
            patch("apps.cases.models.Case") as mock_case_cls,
            patch("apps.cases.services.party.case_party_mutation_service.CaseParty"),
            patch("apps.cases.services.party.case_party_mutation_service.business_config") as mock_bc,
        ):
            mock_case_cls.objects.filter.return_value.only.return_value.first.return_value = MagicMock()
            mock_bc.is_legal_status_valid_for_case_type.return_value = True
            result = svc.create_party(case_id=1, client_id=10, legal_status="plaintiff_side")
        assert result is expected_party
        repo.create_party.assert_called_once()


@pytest.mark.django_db
class TestCasePartyMutationServiceCreatePartyInternal:
    """create_party_internal tests."""

    def _make_service(self, **deps):
        from apps.cases.services.party.case_party_mutation_service import CasePartyMutationService

        return CasePartyMutationService(
            client_service=deps.get("client_service", MagicMock()),
            contract_service=deps.get("contract_service", MagicMock()),
            repo=deps.get("repo", MagicMock()),
        )

    def test_case_not_found_returns_false(self) -> None:
        repo = MagicMock()
        repo.get_case.return_value = None
        svc = self._make_service(repo=repo)
        assert svc.create_party_internal(case_id=1, client_id=10) is False

    def test_existing_party_returns_true(self) -> None:
        repo = MagicMock()
        case = MagicMock()
        case.contract_id = None
        repo.get_case.return_value = case
        repo.party_exists.return_value = True
        svc = self._make_service(repo=repo)
        assert svc.create_party_internal(case_id=1, client_id=10) is True

    def test_creates_party_returns_true(self) -> None:
        repo = MagicMock()
        case = MagicMock()
        case.contract_id = None
        repo.get_case.return_value = case
        repo.party_exists.return_value = False
        svc = self._make_service(repo=repo)
        assert svc.create_party_internal(case_id=1, client_id=10, legal_status="plaintiff_side") is True
        repo.create_party.assert_called_once()


@pytest.mark.django_db
class TestCasePartyMutationServiceDeleteParty:
    """delete_party tests."""

    def test_party_not_found(self) -> None:
        from apps.cases.services.party.case_party_mutation_service import CasePartyMutationService

        with patch("apps.cases.services.party.case_party_mutation_service.CaseParty") as mock_cls:
            mock_cls.objects.filter.return_value.only.return_value.first.return_value = None
            svc = CasePartyMutationService(
                client_service=MagicMock(), contract_service=MagicMock(), repo=MagicMock()
            )
            with pytest.raises(NotFoundError, match="当事人不存在"):
                svc.delete_party(party_id=1)

    def test_successful_deletion(self) -> None:
        from apps.cases.services.party.case_party_mutation_service import CasePartyMutationService

        mock_party = MagicMock()
        mock_party.id = 1
        mock_party.case_id = 10
        mock_party.client_id = 20
        with patch("apps.cases.services.party.case_party_mutation_service.CaseParty") as mock_cls:
            mock_cls.objects.filter.return_value.only.return_value.first.return_value = mock_party
            svc = CasePartyMutationService(
                client_service=MagicMock(), contract_service=MagicMock(), repo=MagicMock()
            )
            result = svc.delete_party(party_id=1)
            assert result == {"success": True}
            mock_party.delete.assert_called_once()

    def test_delete_logs_user(self) -> None:
        from apps.cases.services.party.case_party_mutation_service import CasePartyMutationService

        mock_party = MagicMock()
        mock_party.id = 1
        mock_party.case_id = 10
        mock_party.client_id = 20
        user = MagicMock()
        user.id = 42
        with patch("apps.cases.services.party.case_party_mutation_service.CaseParty") as mock_cls:
            mock_cls.objects.filter.return_value.only.return_value.first.return_value = mock_party
            svc = CasePartyMutationService(
                client_service=MagicMock(), contract_service=MagicMock(), repo=MagicMock()
            )
            result = svc.delete_party(party_id=1, user=user)
            assert result == {"success": True}


class TestCasePartyMutationServiceValidateUpdateReferences:
    """_validate_update_references tests."""

    def test_invalid_case_id_raises(self) -> None:
        from apps.cases.services.party.case_party_mutation_service import CasePartyMutationService

        repo = MagicMock()
        repo.get_case.return_value = None
        svc = CasePartyMutationService(
            client_service=MagicMock(), contract_service=MagicMock(), repo=repo
        )
        party = MagicMock()
        party.case_id = 1
        with pytest.raises(NotFoundError, match="案件不存在"):
            svc._validate_update_references({"case_id": 999}, party)

    def test_invalid_client_id_raises(self) -> None:
        from apps.cases.services.party.case_party_mutation_service import CasePartyMutationService

        client_service = MagicMock()
        client_service.validate_client_exists.return_value = False
        svc = CasePartyMutationService(
            client_service=client_service, contract_service=MagicMock(), repo=MagicMock()
        )
        party = MagicMock()
        party.case_id = 1
        party.client_id = 10
        with pytest.raises(NotFoundError, match="客户不存在"):
            svc._validate_update_references({"client_id": 999}, party)

    def test_same_ids_skip_validation(self) -> None:
        from apps.cases.services.party.case_party_mutation_service import CasePartyMutationService

        svc = CasePartyMutationService(
            client_service=MagicMock(), contract_service=MagicMock(), repo=MagicMock()
        )
        party = MagicMock()
        party.case_id = 1
        party.client_id = 10
        # Should not raise
        svc._validate_update_references({"case_id": 1, "client_id": 10}, party)

    def test_same_case_new_client_checks_client(self) -> None:
        from apps.cases.services.party.case_party_mutation_service import CasePartyMutationService

        client_service = MagicMock()
        client_service.validate_client_exists.return_value = False
        svc = CasePartyMutationService(
            client_service=client_service, contract_service=MagicMock(), repo=MagicMock()
        )
        party = MagicMock()
        party.case_id = 1
        party.client_id = 10
        with pytest.raises(NotFoundError, match="客户不存在"):
            svc._validate_update_references({"client_id": 999}, party)

    def test_new_case_validated(self) -> None:
        from apps.cases.services.party.case_party_mutation_service import CasePartyMutationService

        repo = MagicMock()
        repo.get_case.return_value = MagicMock()
        svc = CasePartyMutationService(
            client_service=MagicMock(), contract_service=MagicMock(), repo=repo
        )
        party = MagicMock()
        party.case_id = 1
        party.client_id = 10
        # New case id different from current, but valid - should not raise
        svc._validate_update_references({"case_id": 2}, party)
        repo.get_case.assert_called_once_with(2)


class TestCasePartyMutationServiceValidateUpdateUniqueness:
    """_validate_update_uniqueness tests."""

    def test_same_ids_no_conflict(self) -> None:
        from apps.cases.services.party.case_party_mutation_service import CasePartyMutationService

        svc = CasePartyMutationService(
            client_service=MagicMock(), contract_service=MagicMock(), repo=MagicMock()
        )
        party = MagicMock()
        party.case_id = 1
        party.client_id = 10
        # Same case_id and client_id - should return early
        svc._validate_update_uniqueness(1, party, 1, 10)

    def test_duplicate_raises(self) -> None:
        from apps.cases.services.party.case_party_mutation_service import CasePartyMutationService

        with patch("apps.cases.services.party.case_party_mutation_service.CaseParty") as mock_cls:
            mock_cls.objects.filter.return_value.exclude.return_value.exists.return_value = True
            svc = CasePartyMutationService(
                client_service=MagicMock(), contract_service=MagicMock(), repo=MagicMock()
            )
            party = MagicMock()
            party.case_id = 1
            party.client_id = 10
            with pytest.raises(ConflictError, match="当事人已存在"):
                svc._validate_update_uniqueness(1, party, 2, 20)


class TestCasePartyMutationServiceInit:
    """Test constructor defaults."""

    def test_default_repo_created(self) -> None:
        from apps.cases.services.party.case_party_mutation_service import CasePartyMutationService

        with patch("apps.cases.services.party.case_party_mutation_service.CasePartyCommandRepo"):
            svc = CasePartyMutationService(
                client_service=MagicMock(), contract_service=MagicMock()
            )
            assert svc.client_service is not None
            assert svc.contract_service is not None

    def test_custom_repo_injected(self) -> None:
        from apps.cases.services.party.case_party_mutation_service import CasePartyMutationService

        repo = MagicMock()
        svc = CasePartyMutationService(
            client_service=MagicMock(), contract_service=MagicMock(), repo=repo
        )
        assert svc.repo is repo
