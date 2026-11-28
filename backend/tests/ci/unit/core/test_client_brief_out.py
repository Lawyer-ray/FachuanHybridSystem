"""嵌入快照 `client_detail` 的契约：不带 identity_docs / client_type_label。

背景：`identity_docs` 曾内嵌在三个当事人 schema（ContractPartyOut / CasePartyOut /
SupplementaryAgreementPartyOut）的 `client_detail` 里，于是「每个当事人的每份证件」
都要一条 SQL——实测占合同列表响应 9.8KB/139KB（7%），而前端生产代码 0 处消费。
三个嵌入点现在统一用 `ClientBriefOut`，证件只从客户自身端点
（GET /clients/{client_id} → ClientOut）出参。

反向验证：把任一嵌入点的 `client_detail` 改回 `ClientLiteOut`，
`test_*_party_serializes_brief_client` 立刻变红（多出一条 `clientidentitydoc` 查询）。
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.cases.models import CaseParty
from apps.cases.schemas.party_schemas import CasePartyOut
from apps.client.models import Client
from apps.client.schemas.client_schemas import ClientOut
from apps.contracts.models import ContractParty, SupplementaryAgreement, SupplementaryAgreementParty
from apps.contracts.schemas.party_schemas import ContractPartyOut
from apps.contracts.schemas.supplementary_schemas import SupplementaryAgreementPartyOut
from apps.core.api.schemas_shared import ClientBriefOut
from apps.testing.factories import CaseFactory, ClientFactory, ClientIdentityDocFactory, ContractFactory

PARTY_SCHEMAS = (ContractPartyOut, CasePartyOut, SupplementaryAgreementPartyOut)
EMBEDDED_FIELDS = {
    "id",
    "name",
    "is_our_client",
    "phone",
    "address",
    "id_number",
    "legal_representative",
}


class TestClientBriefOutShape:
    def test_carries_only_consumed_fields(self) -> None:
        assert set(ClientBriefOut.model_fields) == EMBEDDED_FIELDS

    def test_has_no_identity_docs(self) -> None:
        assert "identity_docs" not in ClientBriefOut.model_fields

    def test_has_no_derived_label(self) -> None:
        assert "client_type_label" not in ClientBriefOut.model_fields

    def test_all_party_schemas_embed_the_brief_snapshot(self) -> None:
        for schema in PARTY_SCHEMAS:
            assert schema.model_fields["client_detail"].annotation is ClientBriefOut, schema.__name__

    def test_client_own_endpoint_still_carries_identity_docs(self) -> None:
        """拆的只是嵌入快照：客户自身端点（证件管理 UI 的唯一入口）不受影响。"""
        assert "identity_docs" in ClientOut.model_fields
        assert "client_type_label" in ClientOut.model_fields


@pytest.mark.django_db
class TestEmbeddedSnapshotSerialization:
    @staticmethod
    def _client_with_docs() -> Client:
        client = ClientFactory(
            name="快照客户",
            is_our_client=True,
            phone="13800000000",  # privacy-allow 虚构号码
            address="某市某区",
            client_type="legal",
            legal_representative="李代表",
        )
        ClientIdentityDocFactory(client=client)
        return client

    @staticmethod
    def _identity_doc_sqls(ctx: CaptureQueriesContext) -> list[str]:
        return [q["sql"] for q in ctx.captured_queries if "clientidentitydoc" in q["sql"].lower()]

    def test_contract_party_serializes_brief_client(self) -> None:
        party = ContractParty.objects.create(contract=ContractFactory(), client=self._client_with_docs())

        with CaptureQueriesContext(connection) as ctx:
            data = ContractPartyOut.from_orm(party).model_dump(mode="json")

        assert data["client_detail"]["name"] == "快照客户"
        assert data["client_detail"]["is_our_client"] is True
        assert data["client_detail"]["legal_representative"] == "李代表"
        assert "identity_docs" not in data["client_detail"]
        assert not self._identity_doc_sqls(ctx), "当事人快照不该读证件表"

    def test_supplementary_party_serializes_brief_client(self) -> None:
        agreement = SupplementaryAgreement.objects.create(contract=ContractFactory(), name="补充协议")
        party = SupplementaryAgreementParty.objects.create(
            supplementary_agreement=agreement, client=self._client_with_docs(), role="PRINCIPAL"
        )
        fetched = agreement.parties.select_related("client").get(pk=party.pk)

        with CaptureQueriesContext(connection) as ctx:
            data = SupplementaryAgreementPartyOut.from_orm(fetched).model_dump(mode="json")

        assert data["client_detail"]["name"] == "快照客户"
        assert data["client_detail"]["phone"] == "13800000000"  # privacy-allow 虚构号码
        assert "identity_docs" not in data["client_detail"]
        assert not self._identity_doc_sqls(ctx), "补充协议当事人快照不该读证件表"

    def test_case_party_serializes_brief_client(self) -> None:
        party = CaseParty.objects.create(case=CaseFactory(), client=self._client_with_docs())
        fetched = CaseParty.objects.select_related("client").get(pk=party.pk)

        with CaptureQueriesContext(connection) as ctx:
            data = CasePartyOut.from_orm(fetched).model_dump(mode="json")

        assert data["client_detail"]["name"] == "快照客户"
        assert data["client_detail"]["address"] == "某市某区"
        assert "identity_docs" not in data["client_detail"]
        assert not self._identity_doc_sqls(ctx), "案件当事人快照不该读证件表"
