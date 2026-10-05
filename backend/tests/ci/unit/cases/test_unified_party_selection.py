"""PartySelectionPolicy 单元测试。

覆盖法定代表人证明书/授权委托书的当事人选择分支，
以及我方当事人校验（不存在 / 非我方 / 非法人）。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.cases.services.template.unified.party_selection import PartySelectionPolicy, SelectedParties
from apps.core.exceptions import ValidationException

LEGAL_REP_CODE = "legal_rep_certificate"
POA_CODE = "power_of_attorney"

LEGAL_CLIENT_DTO = SimpleNamespace(id=101, name="甲公司", client_type="legal")
NATURAL_CLIENT_DTO = SimpleNamespace(id=102, name="张三", client_type="natural")


class _FakeRepo:
    def __init__(self, our_client_ids: set[int] | None = None) -> None:
        self.our_client_ids = our_client_ids if our_client_ids is not None else {101, 102}
        self.is_our_party_calls: list[tuple[int, int]] = []

    def is_our_party(self, case: object, *, client_id: int) -> bool:
        self.is_our_party_calls.append((id(case), client_id))
        return client_id in self.our_client_ids

    def count_our_parties(self, case: object) -> int:
        return len(self.our_client_ids)


class _FakeClientService:
    def __init__(self) -> None:
        self.clients = {101: LEGAL_CLIENT_DTO, 102: NATURAL_CLIENT_DTO}
        self.natural_ids = {102}

    def get_client_internal(self, client_id: int) -> object | None:
        return self.clients.get(client_id)

    def is_natural_person_internal(self, client_id: int) -> bool:
        return client_id in self.natural_ids


def _make_policy(
    our_client_ids: set[int] | None = None,
) -> tuple[PartySelectionPolicy, _FakeRepo, _FakeClientService]:
    repo = _FakeRepo(our_client_ids)
    client_service = _FakeClientService()
    policy = PartySelectionPolicy(repo=repo, client_service=client_service)  # type: ignore[arg-type]
    return policy, repo, client_service


class TestLazyInit:
    def test_default_repo_and_client_service(self) -> None:
        """未注入依赖时延迟构造默认实现并复用实例。"""
        policy = PartySelectionPolicy()
        assert policy.repo is not None
        assert policy.client_service is not None
        assert policy.client_service is policy.client_service

    def test_client_service_property_with_mock(self) -> None:
        svc = MagicMock()
        policy = PartySelectionPolicy(client_service=svc)
        assert policy.client_service is svc


class TestLegalRepCertificate:
    def test_missing_client_id_raises(self) -> None:
        policy, _, _ = _make_policy()
        with pytest.raises(ValidationException) as exc_info:
            policy.select(
                case=object(),
                function_code=LEGAL_REP_CODE,
                client_id=None,
                client_ids=None,
                mode=None,
                legal_rep_cert_code=LEGAL_REP_CODE,
                power_of_attorney_code=POA_CODE,
            )
        assert exc_info.value.code == "INVALID_CLIENT"

    def test_returns_legal_client(self) -> None:
        policy, repo, _ = _make_policy()
        case = SimpleNamespace(id=1)
        selected = policy.select(
            case=case,
            function_code=LEGAL_REP_CODE,
            client_id=101,
            client_ids=None,
            mode=None,
            legal_rep_cert_code=LEGAL_REP_CODE,
            power_of_attorney_code=POA_CODE,
        )
        assert isinstance(selected, SelectedParties)
        assert selected.client is LEGAL_CLIENT_DTO
        assert selected.clients is None
        assert repo.is_our_party_calls == [(id(case), 101)]

    def test_natural_person_rejected(self) -> None:
        policy, _, _ = _make_policy()
        with pytest.raises(ValidationException) as exc_info:
            policy.select(
                case=object(),
                function_code=LEGAL_REP_CODE,
                client_id=102,
                client_ids=None,
                mode=None,
                legal_rep_cert_code=LEGAL_REP_CODE,
                power_of_attorney_code=POA_CODE,
            )
        assert exc_info.value.code == "INVALID_LEGAL_CLIENT"


class TestPowerOfAttorney:
    def _select(self, policy: PartySelectionPolicy, **kwargs: object) -> SelectedParties:
        defaults: dict[str, object] = {
            "case": object(),
            "function_code": POA_CODE,
            "client_id": None,
            "client_ids": None,
            "mode": None,
            "legal_rep_cert_code": LEGAL_REP_CODE,
            "power_of_attorney_code": POA_CODE,
        }
        defaults.update(kwargs)
        return policy.select(**defaults)  # type: ignore[arg-type]

    def test_combined_mode_with_client_ids(self) -> None:
        policy, _, _ = _make_policy()
        selected = self._select(policy, mode="combined", client_ids=[101, 102])
        assert selected.client is None
        assert selected.clients == [LEGAL_CLIENT_DTO, NATURAL_CLIENT_DTO]

    def test_single_client_id(self) -> None:
        policy, _, _ = _make_policy()
        selected = self._select(policy, client_id=102)
        assert selected.client is NATURAL_CLIENT_DTO
        assert selected.clients is None

    def test_no_client_returns_empty(self) -> None:
        policy, _, _ = _make_policy()
        selected = self._select(policy)
        assert selected.client is None
        assert selected.clients is None

    def test_combined_mode_without_ids_returns_empty(self) -> None:
        policy, _, _ = _make_policy()
        selected = self._select(policy, mode="combined", client_ids=None)
        assert selected.client is None
        assert selected.clients is None


class TestOtherFunctionCodes:
    def test_unrelated_function_code_returns_empty(self) -> None:
        policy, _, _ = _make_policy()
        selected = policy.select(
            case=object(),
            function_code="authority_letter",
            client_id=101,
            client_ids=[102],
            mode="combined",
            legal_rep_cert_code=LEGAL_REP_CODE,
            power_of_attorney_code=POA_CODE,
        )
        assert selected.client is None
        assert selected.clients is None


class TestGetOurClientValidation:
    def test_client_not_found_raises(self) -> None:
        policy, _, _ = _make_policy()
        with pytest.raises(ValidationException) as exc_info:
            policy._get_our_client(case=object(), client_id=999)
        assert exc_info.value.code == "INVALID_CLIENT"

    def test_not_our_party_raises(self) -> None:
        policy, _, _ = _make_policy(our_client_ids=set())
        with pytest.raises(ValidationException) as exc_info:
            policy._get_our_client(case=object(), client_id=101)
        assert exc_info.value.code == "INVALID_OUR_CLIENT"
