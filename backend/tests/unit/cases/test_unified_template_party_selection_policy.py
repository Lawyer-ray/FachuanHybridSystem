from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from apps.cases.services.template.unified.party_selection import PartySelectionPolicy
from apps.core.exceptions import ValidationException


class _CaseStub:
    pass


def test_legal_rep_requires_client_id():
    policy = PartySelectionPolicy(repo=Mock(), client_service=Mock())
    with pytest.raises(ValidationException) as e:
        policy.select(
            case=_CaseStub(),
            function_code="legal_rep_certificate",
            client_id=None,
            client_ids=None,
            mode=None,
            legal_rep_cert_code="legal_rep_certificate",
            power_of_attorney_code="power_of_attorney",
        )
    assert e.value.code == "INVALID_CLIENT"


def test_client_must_exist_and_be_our_party():
    repo = Mock()
    repo.is_our_party.return_value = False
    client_service = Mock()
    client_service.get_client_internal.return_value = {"id": 1, "name": "张三"}

    policy = PartySelectionPolicy(repo=repo, client_service=client_service)

    with pytest.raises(ValidationException) as e:
        policy.select(
            case=_CaseStub(),
            function_code="power_of_attorney",
            client_id=1,
            client_ids=None,
            mode="individual",
            legal_rep_cert_code="legal_rep_certificate",
            power_of_attorney_code="power_of_attorney",
        )
    assert e.value.code == "INVALID_OUR_CLIENT"


def test_legal_rep_must_be_non_natural_person():
    repo = Mock()
    repo.is_our_party.return_value = True
    client_service = Mock()
    client_service.get_client_internal.return_value = SimpleNamespace(name="宝铭公司")
    client_service.is_natural_person_internal.return_value = True

    policy = PartySelectionPolicy(repo=repo, client_service=client_service)

    with pytest.raises(ValidationException) as e:
        policy.select(
            case=_CaseStub(),
            function_code="legal_rep_certificate",
            client_id=1,
            client_ids=None,
            mode=None,
            legal_rep_cert_code="legal_rep_certificate",
            power_of_attorney_code="power_of_attorney",
        )
    assert e.value.code == "INVALID_LEGAL_CLIENT"


def test_power_of_attorney_combined_selects_multiple_clients():
    repo = Mock()
    repo.is_our_party.return_value = True
    client_service = Mock()
    client_service.get_client_internal.side_effect = [SimpleNamespace(name="张三"), SimpleNamespace(name="李四")]

    policy = PartySelectionPolicy(repo=repo, client_service=client_service)
    selected = policy.select(
        case=_CaseStub(),
        function_code="power_of_attorney",
        client_id=None,
        client_ids=[1, 2],
        mode="combined",
        legal_rep_cert_code="legal_rep_certificate",
        power_of_attorney_code="power_of_attorney",
    )
    assert selected.client is None
    assert [c.name for c in selected.clients] == ["张三", "李四"]
