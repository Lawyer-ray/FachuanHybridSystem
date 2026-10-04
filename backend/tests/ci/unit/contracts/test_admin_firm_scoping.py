"""管理员律所收敛测试（contracts 域，安全审计）。

与 cases 同口径：is_admin 不再跨律所全放行——可见 = 本所指派覆盖的合同
+ 无任何指派的无主合同；未挂律所的平台级管理员保持全量可见。
合同结构说明：Contract.assignments → ContractAssignment.lawyer（FK organization.Lawyer），
与 Case.assignments 同构，故采用同一过滤口径。
"""

from __future__ import annotations

import pytest

from apps.contracts.models import Contract, ContractAssignment
from apps.contracts.services.contract.domain.access_policy import ContractAccessPolicy
from apps.organization.models import LawFirm
from apps.testing.factories import ContractFactory, LawyerFactory


def _firm(name: str) -> LawFirm:
    return LawFirm.objects.create(name=name)


@pytest.mark.django_db
class TestAdminFirmScopingContracts:
    def test_same_firm_admin_sees_firm_assigned_contract(self):
        firm = _firm("合同同所")
        admin = LawyerFactory(is_admin=True, law_firm=firm)
        member = LawyerFactory(law_firm=firm)
        contract = ContractFactory()
        ContractAssignment.objects.create(contract=contract, lawyer=member)

        policy = ContractAccessPolicy()
        assert policy.has_access(contract.id, admin, None) is True
        assert contract.id in set(
            policy.filter_queryset(Contract.objects.all(), admin, None).values_list("id", flat=True)
        )

    def test_cross_firm_admin_blocked_on_assigned_contract(self):
        """A 所 admin 看不到仅有 B 所指派的合同。"""
        admin_a = LawyerFactory(is_admin=True, law_firm=_firm("合同甲所"))
        lawyer_b = LawyerFactory(law_firm=_firm("合同乙所"))
        contract = ContractFactory()
        ContractAssignment.objects.create(contract=contract, lawyer=lawyer_b)

        policy = ContractAccessPolicy()
        assert policy.has_access(contract.id, admin_a, None) is False
        assert contract.id not in set(
            policy.filter_queryset(Contract.objects.all(), admin_a, None).values_list("id", flat=True)
        )

    def test_admin_sees_contract_without_any_assignment(self):
        admin = LawyerFactory(is_admin=True, law_firm=_firm("合同丙所"))
        contract = ContractFactory()

        policy = ContractAccessPolicy()
        assert policy.has_access(contract.id, admin, None) is True
        assert contract.id in set(
            policy.filter_queryset(Contract.objects.all(), admin, None).values_list("id", flat=True)
        )

    def test_firmless_admin_keeps_full_visibility(self):
        admin = LawyerFactory(is_admin=True)
        lawyer_b = LawyerFactory(law_firm=_firm("合同丁所"))
        contract = ContractFactory()
        ContractAssignment.objects.create(contract=contract, lawyer=lawyer_b)

        policy = ContractAccessPolicy()
        assert policy.has_access(contract.id, admin, None) is True

    @pytest.mark.asyncio
    @pytest.mark.django_db(transaction=True)
    async def test_async_has_access_same_firm_scope(self):
        """ahas_access（异步版）与同步版同口径。

        transaction=True：sync_to_async 的 setup 跑在共享执行线程自己的连接上
        （autocommit），事务型用例的回滚管不到它，必须用 TransactionTestCase
        由 teardown flush 兜底，否则数据会漏进复用测试库。
        """
        from asgiref.sync import sync_to_async

        @sync_to_async
        def _setup() -> tuple:
            admin_a = LawyerFactory(is_admin=True, law_firm=_firm("异步甲所"))
            lawyer_b = LawyerFactory(law_firm=_firm("异步乙所"))
            contract = ContractFactory()
            ContractAssignment.objects.create(contract=contract, lawyer=lawyer_b)
            return contract, admin_a

        contract, admin_a = await _setup()
        assert await ContractAccessPolicy().ahas_access(contract.id, admin_a, None) is False
