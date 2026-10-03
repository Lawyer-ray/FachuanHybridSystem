"""列表端点限额语义回归测试（v27.2.11 限额清偿的行为锚点）。

覆盖四个端点：
- GET /api/v1/client/clients（limit 默认 1000）
- GET /api/v1/cases/cases（显式 limit 生效；无过滤无 limit 时默认上限——单测分支见下）
- GET /api/v1/organization/lawyers（page_size=500 放开历史截断）
- GET /api/v1/contacts/contacts（limit 默认 1000，需 admin）

回归锚点语义：律师超过 20 人时 /lawyers 必须全量返回（旧实现被 service
page_size=20 硬截断）；limit 参数必须被尊重而非静默忽略。
"""

from __future__ import annotations

import pytest

from apps.testing.factories import CaseFactory, ClientFactory, ContractFactory, LawyerFactory


@pytest.mark.django_db
class TestClientsLimit:
    def test_explicit_limit_respected(self, authenticated_client):
        for _ in range(3):
            ClientFactory(client_type="natural")
        resp = authenticated_client.get("/api/v1/client/clients?limit=2")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


@pytest.mark.django_db
class TestCasesLimit:
    def _make_cases(self, n: int = 3):
        contract = ContractFactory()
        for _ in range(n):
            CaseFactory(contract=contract)
        return contract

    def test_explicit_limit_respected(self, authenticated_client):
        self._make_cases(3)
        resp = authenticated_client.get("/api/v1/cases/cases?limit=2")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_filtered_query_unaffected_by_default_cap(self, authenticated_client):
        """带过滤参数（contract_id）的查询不受默认上限影响——消费方契约。"""
        contract = self._make_cases(3)
        resp = authenticated_client.get(f"/api/v1/cases/cases?contract_id={contract.pk}")
        assert resp.status_code == 200
        assert len(resp.json()) == 3

    @pytest.mark.asyncio
    async def test_no_filter_uses_default_cap(self):
        """无过滤、无显式 limit 时应用默认上限 1000（handler 决策分支）。"""
        from unittest.mock import MagicMock, patch

        from apps.cases.api import case_api

        class _RecordingQS:
            def __init__(self) -> None:
                self.slices: list = []

            def __getitem__(self, key):
                self.slices.append(key)
                return iter([])

        qs = _RecordingQS()
        request = MagicMock()
        ctx = MagicMock(user=None, org_access=None, perm_open_access=True)
        with (
            patch.object(case_api, "_get_case_query_facade") as facade,
            patch.object(case_api, "extract_request_context", return_value=ctx),
        ):
            facade.return_value.list_cases.return_value = qs
            result = await case_api.list_cases(request)
        assert qs.slices == [slice(1000)]
        assert result == []


@pytest.mark.django_db
class TestLawyersNoTruncation:
    def test_more_than_20_lawyers_all_returned(self, authenticated_client):
        """回归锚点：律师 >20 人必须全量返回（旧实现截断在前 20 条，
        办案页执业证号/律所字段静默缺失）。"""
        from apps.organization.models import Lawyer

        for _ in range(25):
            LawyerFactory()
        total = Lawyer.objects.count()  # 含 authenticated_client 自建的超管
        assert total >= 26  # 自检：确已超过旧的 20 条截断线
        resp = authenticated_client.get("/api/v1/organization/lawyers")
        assert resp.status_code == 200
        assert len(resp.json()) == total


@pytest.mark.django_db
class TestContactsLimit:
    def test_explicit_limit_respected(self, authenticated_client):
        from apps.cases.models import Case
        from apps.contacts.models import CaseContact

        contract = ContractFactory()
        case = CaseFactory(contract=contract)
        for _ in range(3):
            CaseContact.objects.create(case=case, name=f"联系人-{case.pk}")
        resp = authenticated_client.get("/api/v1/contacts/contacts?limit=2")
        assert resp.status_code == 200
        assert len(resp.json()) == 2
