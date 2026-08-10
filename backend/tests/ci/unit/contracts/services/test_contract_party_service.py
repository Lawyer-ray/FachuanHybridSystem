"""Unit tests for ContractPartyService (role 支持 / 增删改)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestContractPartyService:
    """测试 ContractPartyService 的 add_party role 逻辑"""

    def test_add_party_creates_with_default_role(self) -> None:
        from apps.contracts.models import PartyRole
        from apps.contracts.services.party.contract_party_service import ContractPartyService

        svc = ContractPartyService()
        with patch("apps.contracts.services.party.contract_party_service.Contract") as mock_contract, patch(
            "apps.contracts.services.party.contract_party_service.ContractParty"
        ) as mock_cp:
            mock_contract.objects.filter.return_value.exists.return_value = True
            party = MagicMock(id=1, role=PartyRole.PRINCIPAL)
            mock_cp.objects.get_or_create.return_value = (party, True)

            result = svc.add_party(contract_id=1, client_id=10)

            mock_cp.objects.get_or_create.assert_called_once_with(
                contract_id=1, client_id=10, defaults={"role": PartyRole.PRINCIPAL}
            )
            assert result is party
            party.save.assert_not_called()

    def test_add_party_with_custom_role(self) -> None:
        from apps.contracts.models import PartyRole
        from apps.contracts.services.party.contract_party_service import ContractPartyService

        svc = ContractPartyService()
        with patch("apps.contracts.services.party.contract_party_service.Contract") as mock_contract, patch(
            "apps.contracts.services.party.contract_party_service.ContractParty"
        ) as mock_cp:
            mock_contract.objects.filter.return_value.exists.return_value = True
            party = MagicMock(id=1, role=PartyRole.OPPOSING)
            mock_cp.objects.get_or_create.return_value = (party, True)

            svc.add_party(contract_id=1, client_id=10, role=PartyRole.OPPOSING)

            mock_cp.objects.get_or_create.assert_called_once_with(
                contract_id=1, client_id=10, defaults={"role": PartyRole.OPPOSING}
            )

    def test_add_party_updates_role_when_existing(self) -> None:
        from apps.contracts.models import PartyRole
        from apps.contracts.services.party.contract_party_service import ContractPartyService

        svc = ContractPartyService()
        with patch("apps.contracts.services.party.contract_party_service.Contract") as mock_contract, patch(
            "apps.contracts.services.party.contract_party_service.ContractParty"
        ) as mock_cp:
            mock_contract.objects.filter.return_value.exists.return_value = True
            existing_party = MagicMock(id=1, role=PartyRole.PRINCIPAL)
            mock_cp.objects.get_or_create.return_value = (existing_party, False)

            svc.add_party(contract_id=1, client_id=10, role=PartyRole.OPPOSING)

            assert existing_party.role == PartyRole.OPPOSING
            existing_party.save.assert_called_once()

    def test_add_party_does_not_save_when_role_unchanged(self) -> None:
        from apps.contracts.models import PartyRole
        from apps.contracts.services.party.contract_party_service import ContractPartyService

        svc = ContractPartyService()
        with patch("apps.contracts.services.party.contract_party_service.Contract") as mock_contract, patch(
            "apps.contracts.services.party.contract_party_service.ContractParty"
        ) as mock_cp:
            mock_contract.objects.filter.return_value.exists.return_value = True
            existing_party = MagicMock(id=1, role=PartyRole.PRINCIPAL)
            mock_cp.objects.get_or_create.return_value = (existing_party, False)

            svc.add_party(contract_id=1, client_id=10, role=PartyRole.PRINCIPAL)

            existing_party.save.assert_not_called()

    def test_add_party_raises_when_contract_missing(self) -> None:
        from apps.contracts.services.party.contract_party_service import ContractPartyService
        from apps.core.exceptions import NotFoundError

        svc = ContractPartyService()
        with patch("apps.contracts.services.party.contract_party_service.Contract") as mock_contract:
            mock_contract.objects.filter.return_value.exists.return_value = False
            with pytest.raises(NotFoundError):
                svc.add_party(contract_id=999, client_id=10)

    def test_remove_party_raises_when_not_found(self) -> None:
        from apps.contracts.services.party.contract_party_service import ContractPartyService
        from apps.core.exceptions import NotFoundError

        svc = ContractPartyService()
        with patch("apps.contracts.services.party.contract_party_service.ContractParty") as mock_cp:
            mock_cp.objects.filter.return_value.delete.return_value = (0, {})
            with pytest.raises(NotFoundError):
                svc.remove_party(contract_id=1, client_id=99)
