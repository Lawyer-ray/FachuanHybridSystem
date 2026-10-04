"""补充覆盖测试: contracts/schemas/supplementary_schemas.py

覆盖: SupplementaryAgreementPartyOut / SupplementaryAgreementOut 的
resolve_* 静态方法（dict 与 model 两分支、prefetch 分支）及输入 Schema 默认值。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from apps.contracts.schemas.supplementary_schemas import (
    SupplementaryAgreementIn,
    SupplementaryAgreementInput,
    SupplementaryAgreementOut,
    SupplementaryAgreementPartyIn,
    SupplementaryAgreementPartyInput,
    SupplementaryAgreementPartyOut,
    SupplementaryAgreementUpdate,
)
from apps.core.api.schemas import SchemaMixin

SCHEMA_MOD = "apps.contracts.schemas.supplementary_schemas"


# ── SupplementaryAgreementPartyOut.resolve_* ──────────────────────


class TestPartyOutResolveClientDetail:
    def test_dict_with_nested_dict_builds_client_out(self):
        detail = {
            "id": 1,
            "name": "A公司",
            "is_our_client": True,
            "client_type": "company",
            "client_type_label": "公司",
            "identity_docs": [],
        }
        result = SupplementaryAgreementPartyOut.resolve_client_detail({"client_detail": detail})
        assert result is not None
        assert result.id == 1
        assert result.name == "A公司"

    def test_dict_with_non_dict_detail_returned_as_is(self):
        result = SupplementaryAgreementPartyOut.resolve_client_detail({"client_detail": None})
        assert result is None

    def test_model_without_client_returns_none(self):
        obj = MagicMock()
        obj.client = None
        assert SupplementaryAgreementPartyOut.resolve_client_detail(obj) is None

    def test_model_with_client_calls_from_model(self):
        obj = MagicMock()
        obj.client = MagicMock(name="client")
        expected = MagicMock(name="client_out")
        with pytest.MonkeyPatch.context() as mp:
            mock_client_out = MagicMock()
            mock_client_out.from_model.return_value = expected
            mp.setattr(f"{SCHEMA_MOD}.ClientOut", mock_client_out)
            result = SupplementaryAgreementPartyOut.resolve_client_detail(obj)
        mock_client_out.from_model.assert_called_once_with(obj.client)
        assert result is expected


class TestPartyOutResolveClientName:
    def test_dict_branch(self):
        assert SupplementaryAgreementPartyOut.resolve_client_name({"client_name": "B公司"}) == "B公司"

    def test_dict_missing_key_returns_empty(self):
        assert SupplementaryAgreementPartyOut.resolve_client_name({}) == ""

    def test_model_without_client_returns_empty(self):
        obj = MagicMock()
        obj.client = None
        assert SupplementaryAgreementPartyOut.resolve_client_name(obj) == ""

    def test_model_with_client_returns_name(self):
        obj = MagicMock()
        obj.client = MagicMock()
        obj.client.name = "C公司"
        assert SupplementaryAgreementPartyOut.resolve_client_name(obj) == "C公司"


class TestPartyOutResolveIsOurClient:
    def test_dict_truthy(self):
        assert SupplementaryAgreementPartyOut.resolve_is_our_client({"is_our_client": True}) is True

    def test_dict_falsy(self):
        assert SupplementaryAgreementPartyOut.resolve_is_our_client({"is_our_client": 0}) is False

    def test_model_without_client(self):
        obj = MagicMock()
        obj.client = None
        assert SupplementaryAgreementPartyOut.resolve_is_our_client(obj) is False

    def test_model_with_client(self):
        obj = MagicMock()
        obj.client = MagicMock()
        obj.client.is_our_client = True
        assert SupplementaryAgreementPartyOut.resolve_is_our_client(obj) is True


class TestPartyOutResolveRoleLabel:
    def test_dict_branch(self):
        assert SupplementaryAgreementPartyOut.resolve_role_label({"role_label": "委托人"}) == "委托人"

    def test_dict_missing_key_returns_empty(self):
        assert SupplementaryAgreementPartyOut.resolve_role_label({}) == ""

    def test_model_empty_role_returns_empty(self):
        obj = MagicMock()
        obj.role = ""
        assert SupplementaryAgreementPartyOut.resolve_role_label(obj) == ""

    def test_model_role_uses_display(self):
        obj = MagicMock()
        obj.role = "PRINCIPAL"
        obj.get_role_display.return_value = "委托人"
        assert SupplementaryAgreementPartyOut.resolve_role_label(obj) == "委托人"
        obj.get_role_display.assert_called_once_with()


# ── SupplementaryAgreementOut.resolve_* ───────────────────────────


class TestAgreementOutResolveParties:
    def test_dict_branch_returns_prefetched_list(self):
        parties = [{"id": 1}, {"id": 2}]
        result = SupplementaryAgreementOut.resolve_parties({"parties": parties})
        assert result == parties

    def test_dict_branch_missing_key_returns_empty(self):
        assert SupplementaryAgreementOut.resolve_parties({}) == []

    def test_model_with_prefetch_cache_avoids_query(self):
        obj = MagicMock()
        prefetched = [MagicMock(id=1)]
        obj._prefetched_objects_cache = {"parties": prefetched}
        assert SupplementaryAgreementOut.resolve_parties(obj) == prefetched
        obj.parties.select_related.assert_not_called()

    def test_model_without_prefetch_queries_db_shape(self):
        obj = MagicMock()
        obj._prefetched_objects_cache = {}
        parties = [MagicMock(id=1), MagicMock(id=2)]
        obj.parties.select_related.return_value.all.return_value = parties
        result = SupplementaryAgreementOut.resolve_parties(obj)
        obj.parties.select_related.assert_called_once_with("client")
        assert result == parties


class TestAgreementOutResolveTimestamps:
    def test_dict_branch_created_at(self):
        assert (
            SupplementaryAgreementOut.resolve_created_at({"created_at": "2026-01-02T03:04:05"}) == "2026-01-02T03:04:05"
        )

    def test_dict_branch_missing_created_at(self):
        assert SupplementaryAgreementOut.resolve_created_at({}) == ""

    def test_dict_branch_updated_at(self):
        assert (
            SupplementaryAgreementOut.resolve_updated_at({"updated_at": "2026-02-03T04:05:06"}) == "2026-02-03T04:05:06"
        )

    def test_dict_branch_missing_updated_at(self):
        assert SupplementaryAgreementOut.resolve_updated_at({}) == ""

    def test_model_datetime_serialized_iso(self):
        dt = datetime(2026, 3, 4, 5, 6, 7)
        obj = MagicMock()
        obj.created_at = dt
        obj.updated_at = None
        assert SupplementaryAgreementOut.resolve_created_at(obj) == SchemaMixin._resolve_datetime_iso(dt)
        assert SupplementaryAgreementOut.resolve_updated_at(obj) is None


# ── 输入 Schema 默认值 ────────────────────────────────────────────


class TestInputSchemaDefaults:
    def test_party_input_role_default(self):
        party = SupplementaryAgreementPartyInput(client_id=1)
        assert party.role == "PRINCIPAL"

    def test_party_in_role_default_uses_party_role(self):
        from apps.contracts.models import PartyRole

        party = SupplementaryAgreementPartyIn(client_id=2)
        assert party.role == PartyRole.PRINCIPAL

    def test_agreement_in_defaults(self):
        payload = SupplementaryAgreementIn(contract_id=3)
        assert payload.name is None
        assert payload.party_ids is None
        assert payload.parties is None

    def test_agreement_input_defaults(self):
        payload = SupplementaryAgreementInput()
        assert payload.name is None
        assert payload.party_ids is None
        assert payload.parties is None

    def test_agreement_update_defaults(self):
        payload = SupplementaryAgreementUpdate()
        assert payload.name is None
        assert payload.party_ids is None
        assert payload.parties is None

    def test_agreement_in_with_parties(self):
        payload = SupplementaryAgreementIn(
            contract_id=4,
            parties=[SupplementaryAgreementPartyInput(client_id=5, role="AGENT")],
        )
        assert payload.parties[0].client_id == 5
        assert payload.parties[0].role == "AGENT"
