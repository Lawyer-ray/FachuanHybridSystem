"""业务域越权审计修复测试（client 域）。

覆盖：
- related-items：按查询用户过滤案件/合同关联（律师 A 拿不到 B 的案件/合同）
- ClientOut / ClientLiteOut 证件号出参打码（库里原文不变）
- delete_client 同步清理 historicalclient 快照（身份证号残留）
"""

from __future__ import annotations

import pytest

from apps.client.schemas import ClientOut
from apps.core.api.schemas_shared import ClientLiteOut
from apps.core.utils.id_card_utils import IdCardUtils
from apps.testing.factories import CaseFactory, ClientFactory, ContractFactory, LawyerFactory


def _bind_case(client, case, **kwargs):
    from apps.cases.models import CaseParty

    return CaseParty.objects.create(case=case, client=client, **kwargs)


def _bind_contract(client, contract, **kwargs):
    from apps.contracts.models import ContractParty

    return ContractParty.objects.create(contract=contract, client=client, **kwargs)


def _grant_view_client(user):
    """授予 client.view_client 权限（对齐线上普通律师的角色配置）。"""
    from django.contrib.auth.models import Permission

    user.user_permissions.add(Permission.objects.get(codename="view_client"))
    return user


# ── Item 1: related-items 按查询用户过滤 ─────────────────────────────────────


@pytest.mark.django_db
class TestRelatedItemsAccess:
    def _facade(self):
        from apps.client.services.client_query_facade import ClientQueryFacade

        return ClientQueryFacade()

    def test_lawyer_only_sees_own_case_and_contract(self):
        """律师 A 只看到自己被指派的案件/合同，看不到 B 的。"""
        lawyer_a = _grant_view_client(LawyerFactory())
        lawyer_b = LawyerFactory()
        client = ClientFactory()

        case_a = CaseFactory()
        case_b = CaseFactory()
        from apps.cases.models import CaseAssignment

        CaseAssignment.objects.create(case=case_a, lawyer=lawyer_a)
        CaseAssignment.objects.create(case=case_b, lawyer=lawyer_b)
        contract_a = ContractFactory()
        contract_b = ContractFactory()
        from apps.contracts.models import ContractAssignment

        ContractAssignment.objects.create(contract=contract_a, lawyer=lawyer_a)
        ContractAssignment.objects.create(contract=contract_b, lawyer=lawyer_b)

        _bind_case(client, case_a)
        _bind_case(client, case_b)
        _bind_contract(client, contract_a)
        _bind_contract(client, contract_b)

        result = self._facade().get_related_items(client_id=client.id, user=lawyer_a)

        assert [c["id"] for c in result["cases"]] == [case_a.id]
        assert [c["id"] for c in result["contracts"]] == [contract_a.id]

    def test_no_access_lawyer_sees_nothing(self):
        """无任何指派的律师看不到他人案件的关联条目。"""
        lawyer = _grant_view_client(LawyerFactory())
        owner = LawyerFactory()
        client = ClientFactory()
        case = CaseFactory()
        from apps.cases.models import CaseAssignment

        CaseAssignment.objects.create(case=case, lawyer=owner)
        _bind_case(client, case)

        result = self._facade().get_related_items(client_id=client.id, user=lawyer)

        assert result["cases"] == []
        assert result["contracts"] == []

    def test_admin_sees_unassigned_and_own_firm_items(self):
        """管理员可见无指派案件（兜底语义）与自己可见合同。"""
        admin = LawyerFactory(is_admin=True)
        client = ClientFactory()
        case_unassigned = CaseFactory()
        _bind_case(client, case_unassigned)

        result = self._facade().get_related_items(client_id=client.id, user=admin)

        assert [c["id"] for c in result["cases"]] == [case_unassigned.id]

    def test_user_none_keeps_legacy_full_view(self):
        """user=None（内部调用）不过滤，保持既有口径。"""
        lawyer = LawyerFactory()
        client = ClientFactory()
        case = CaseFactory()
        from apps.cases.models import CaseAssignment

        CaseAssignment.objects.create(case=case, lawyer=lawyer)
        _bind_case(client, case)

        result = self._facade().get_related_items(client_id=client.id)

        assert [c["id"] for c in result["cases"]] == [case.id]


# ── Item 3: 证件号出参打码 ───────────────────────────────────────────────────


class TestIdNumberMasking:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("110101199001011234", "110***********1234"),
            ("12345678", "123*5678"),
            ("1234567", "****"),
            ("", ""),
            (None, None),
        ],
    )
    def test_mask_id_number(self, raw, expected):
        assert IdCardUtils.mask_id_number(raw) == expected

    def test_mask_idempotent(self):
        once = IdCardUtils.mask_id_number("110101199001011234")
        assert IdCardUtils.mask_id_number(once) == once


@pytest.mark.django_db
class TestClientOutMasking:
    def test_client_out_masks_id_numbers(self):
        client = ClientFactory(
            client_type="natural",
            id_number="110101199001011234",
            legal_representative_id_number="110101198808088888",
        )
        data = ClientOut.from_orm(client).model_dump()

        assert data["id_number"] == "110***********1234"
        assert data["legal_representative_id_number"] == "110***********8888"
        # 库里原文不变（service 层仍读全文）
        client.refresh_from_db()
        assert client.id_number == "110101199001011234"

    def test_client_lite_out_masks_id_numbers(self):
        client = ClientFactory(id_number="110101199001011234")
        out = ClientLiteOut.from_model(client)

        assert out.id_number == "110***********1234"
        client.refresh_from_db()
        assert client.id_number == "110101199001011234"

    def test_short_id_number_fully_masked(self):
        client = ClientFactory(id_number="12345")
        assert ClientOut.from_orm(client).model_dump()["id_number"] == "****"


# ── Item 8c: 删除客户清理历史快照 ────────────────────────────────────────────


@pytest.mark.django_db
class TestDeleteClientPurgesHistory:
    def test_delete_client_removes_historical_snapshots(self):
        from apps.client.services.client_mutation_service import ClientMutationService

        admin = LawyerFactory(is_admin=True, is_superuser=True)
        client = ClientFactory(id_number="110101199001011234")
        # 更新一次以产生额外历史快照
        client.phone = "13800000000"
        client.save()

        historical_model = type(client).history.model
        assert historical_model.objects.filter(id=client.id).count() >= 2

        ClientMutationService().delete_client(client_id=client.id, user=admin)

        assert historical_model.objects.filter(id=client.id).count() == 0
