"""
合同 CRUD API 集成测试

通过直接调用 API 函数测试完整的 CRUD 流程。
使用 factories 创建测试数据。

Requirements: 5.2
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import Mock

import pytest

from apps.contracts.api.contract_api import (
    create_contract,
    delete_contract,
    get_contract,
    list_contracts,
    update_contract,
    update_contract_lawyers,
)
from apps.contracts.models import Contract
from apps.contracts.schemas import ContractIn, ContractUpdate, UpdateLawyersIn
from apps.core.exceptions import NotFoundError, PermissionDenied
from tests.factories.contract_factories import ContractFactory
from tests.factories.organization_factories import LawyerFactory


def _make_request(
    user: Any = None,
    *,
    perm_open_access: bool = True,
    org_access: Any = None,
) -> Mock:
    """构造模拟 request 对象。"""
    request = Mock()
    request.user = user
    request.perm_open_access = perm_open_access
    request.org_access = org_access
    return request


@pytest.mark.django_db
@pytest.mark.integration
class TestContractCreateAPI:
    """合同创建 API 测试"""

    def test_create_contract_minimal(self) -> None:
        """最小字段创建合同"""
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        payload = ContractIn(
            name="测试合同",
            case_type="civil",
            status="active",
            fee_mode="fixed",
            fixed_amount=10000.00,
            lawyer_ids=[lawyer.id],
        )
        result = create_contract(request, payload)

        assert result.id is not None
        assert result.name == "测试合同"
        assert result.case_type == "civil"
        assert result.fee_mode == "fixed"

    def test_create_contract_with_risk_fee(self) -> None:
        """风险收费模式创建合同"""
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        payload = ContractIn(
            name="风险合同",
            case_type="civil",
            status="active",
            fee_mode="full_risk",
            risk_rate=15.0,
            lawyer_ids=[lawyer.id],
        )
        result = create_contract(request, payload)

        assert result.name == "风险合同"
        assert result.fee_mode == "full_risk"


@pytest.mark.django_db
@pytest.mark.integration
class TestContractListAPI:
    """合同列表查询 API 测试"""

    def test_list_contracts_empty(self) -> None:
        """空列表查询"""
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        result = list_contracts(request)
        assert len(result) == 0

    def test_list_contracts_returns_all(self) -> None:
        """查询所有合同"""
        ContractFactory.create_batch(3)
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        result = list_contracts(request)
        assert len(result) == 3

    def test_list_contracts_filter_by_case_type(self) -> None:
        """按案件类型过滤"""
        ContractFactory.create_batch(2, case_type="civil")
        ContractFactory(case_type="criminal")
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        result = list_contracts(request, case_type="civil")
        assert len(result) == 2

    def test_list_contracts_filter_by_status(self) -> None:
        """按状态过滤"""
        ContractFactory.create_batch(2, status="active")
        ContractFactory(status="closed")
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        result = list_contracts(request, status="active")
        assert len(result) == 2


@pytest.mark.django_db
@pytest.mark.integration
class TestContractGetAPI:
    """合同详情查询 API 测试"""

    def test_get_contract_success(self) -> None:
        """获取合同详情"""
        contract = ContractFactory(name="详情测试合同")
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        result = get_contract(request, contract.id)

        assert result.id == contract.id
        assert result.name == "详情测试合同"

    def test_get_contract_not_found(self) -> None:
        """获取不存在的合同"""
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        with pytest.raises(NotFoundError):
            get_contract(request, 999999)

    def test_get_contract_permission_denied(self) -> None:
        """无权限访问合同"""
        contract = ContractFactory()
        lawyer = LawyerFactory(is_admin=False)
        request = _make_request(
            user=lawyer,
            perm_open_access=False,
            org_access={"lawyers": set(), "extra_cases": set()},
        )

        with pytest.raises(PermissionDenied):
            get_contract(request, contract.id)


@pytest.mark.django_db
@pytest.mark.integration
class TestContractUpdateAPI:
    """合同更新 API 测试"""

    def test_update_contract_name(self) -> None:
        """更新合同名称"""
        contract = ContractFactory(name="旧名称")
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        payload = ContractUpdate(name="新名称")
        result = update_contract(request, contract.id, payload)

        assert result.name == "新名称"
        contract.refresh_from_db()
        assert contract.name == "新名称"

    def test_update_contract_partial(self) -> None:
        """部分更新（只更新指定字段）"""
        contract = ContractFactory(name="原名称", status="active")
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        payload = ContractUpdate(status="closed")
        result = update_contract(request, contract.id, payload)

        assert result.name == "原名称"
        assert result.status == "closed"

    def test_update_contract_not_found(self) -> None:
        """更新不存在的合同"""
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        payload = ContractUpdate(name="新名称")
        with pytest.raises(NotFoundError):
            update_contract(request, 999999, payload)

    def test_update_contract_finance_requires_admin(self) -> None:
        """更新财务数据需要管理员权限"""
        contract = ContractFactory(
            fee_mode="fixed",
            fixed_amount=Decimal("10000.00"),
        )
        lawyer = LawyerFactory(is_admin=False)
        request = _make_request(user=lawyer)

        payload = ContractUpdate(fixed_amount=20000.00)
        with pytest.raises(PermissionDenied):
            update_contract(request, contract.id, payload, confirm_finance=True)


@pytest.mark.django_db
@pytest.mark.integration
class TestContractDeleteAPI:
    """合同删除 API 测试"""

    def test_delete_contract_success(self) -> None:
        """删除合同"""
        contract = ContractFactory()
        contract_id = contract.id
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        result = delete_contract(request, contract_id)

        assert result["success"] is True
        assert not Contract.objects.filter(id=contract_id).exists()

    def test_delete_contract_not_found(self) -> None:
        """删除不存在的合同"""
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        with pytest.raises(NotFoundError):
            delete_contract(request, 999999)


@pytest.mark.django_db
@pytest.mark.integration
class TestContractLawyersAPI:
    """合同律师指派 API 测试"""

    def test_update_contract_lawyers(self) -> None:
        """更新合同律师指派"""
        contract = ContractFactory()
        lawyer1 = LawyerFactory()
        lawyer2 = LawyerFactory()
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        payload = UpdateLawyersIn(lawyer_ids=[lawyer1.id, lawyer2.id])
        # API 直接调用返回 List[ContractAssignment]
        assignments = update_contract_lawyers(request, contract.id, payload)

        assigned_ids = {a.lawyer_id for a in assignments}
        assert lawyer1.id in assigned_ids
        assert lawyer2.id in assigned_ids
