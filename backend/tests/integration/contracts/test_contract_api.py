"""
合同 API 集成测试

测试合同 API 的端到端流程
"""

from decimal import Decimal

import pytest
from django.test import Client

from apps.contracts.models import Contract, ContractPayment, InvoiceStatus
from tests.factories.client_factories import ClientFactory
from tests.factories.contract_factories import ContractFactory
from tests.factories.organization_factories import LawFirmFactory, LawyerFactory


@pytest.mark.django_db
class TestContractAPI:
    """合同 API 集成测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.client = Client()

        # 创建测试用户（管理员）
        self.admin_user = LawyerFactory(is_admin=True)
        self.normal_user = LawyerFactory(is_admin=False)

        # 创建律所
        self.law_firm = LawFirmFactory()

    def test_create_contract_success(self):
        """测试创建合同成功"""
        # 准备数据
        lawyer = LawyerFactory(law_firm=self.law_firm)

        data = {
            "name": "测试合同",
            "case_type": "civil",
            "status": "active",
            "fee_mode": "fixed",
            "fixed_amount": 10000.00,
            "lawyer_ids": [lawyer.id],  # 使用新的 lawyer_ids 字段  # type: ignore[attr-defined]
        }

        # 模拟请求
        from unittest.mock import Mock

        request = Mock()
        request.user = self.admin_user

        # 调用 API
        from apps.contracts.api.contract_api import create_contract
        from apps.contracts.schemas import ContractIn

        payload = ContractIn(**data)
        contract = create_contract(request, payload)

        # 验证结果
        assert contract.id is not None
        assert contract.name == "测试合同"
        assert contract.case_type == "civil"
        assert contract.status == "active"
        assert contract.fee_mode == "fixed"
        assert float(contract.fixed_amount) == 10000.00

        # 验证律师指派
        assert contract.primary_lawyer.id == lawyer.id  # type: ignore[attr-defined]
        assignments = contract.assignments.all()
        assert len(assignments) == 1
        assert assignments[0].lawyer_id == lawyer.id  # type: ignore[attr-defined]
        assert assignments[0].is_primary is True

    def test_create_contract_with_cases_success(self):
        """测试创建合同并关联案件成功"""
        # 准备数据
        lawyer = LawyerFactory(law_firm=self.law_firm)
        client = ClientFactory()

        data = {
            "name": "测试合同",
            "case_type": "civil",
            "status": "active",
            "fee_mode": "fixed",
            "fixed_amount": 10000.00,
            "lawyer_ids": [lawyer.id],  # 使用新的 lawyer_ids 字段  # type: ignore[attr-defined]
            "cases": [
                {
                    "name": "测试案件1",
                    "case_type": "civil",
                    "target_amount": 50000.00,
                    "parties": [{"client_id": client.id, "legal_status": "plaintiff"}],  # type: ignore[attr-defined]
                }
            ],
        }

        # 模拟请求
        from unittest.mock import Mock

        request = Mock()
        request.user = self.admin_user

        # 调用 API
        from apps.contracts.api.contract_api import ContractWithCasesIn, create_contract_with_cases

        payload = ContractWithCasesIn(**data)
        contract = create_contract_with_cases(request, payload)

        # 验证结果
        assert contract.id is not None
        assert contract.name == "测试合同"

        # 验证律师指派
        assert contract.primary_lawyer.id == lawyer.id  # type: ignore[attr-defined]

        # 验证案件创建
        cases = contract.cases.all()
        assert len(cases) == 1
        assert cases[0].name == "测试案件1"

        # 验证当事人创建
        parties = cases[0].parties.all()
        assert len(parties) == 1
        assert parties[0].client_id == client.id  # type: ignore[attr-defined]
        assert parties[0].legal_status == "plaintiff"

    def test_update_contract_success(self):
        """测试更新合同成功"""
        # 创建合同
        contract = ContractFactory(name="旧名称", status="draft", fee_mode="fixed", fixed_amount=Decimal("10000.00"))

        # 准备更新数据
        update_data = {"name": "新名称", "status": "active"}

        # 模拟请求
        from unittest.mock import Mock

        request = Mock()
        request.user = self.admin_user

        # 调用 API
        from apps.contracts.api.contract_api import update_contract
        from apps.contracts.schemas import ContractUpdate

        payload = ContractUpdate(**update_data)
        updated_contract = update_contract(request, contract.id, payload, confirm_finance=False)  # type: ignore[attr-defined]

        # 验证结果
        assert updated_contract.name == "新名称"
        assert updated_contract.status == "active"

        # 验证数据库
        contract.refresh_from_db()  # type: ignore[attr-defined]
        assert contract.name == "新名称"
        assert contract.status == "active"

    def test_update_contract_finance_requires_admin(self):
        """测试更新财务数据需要管理员权限"""
        # 创建合同
        contract = ContractFactory(fee_mode="fixed", fixed_amount=Decimal("10000.00"))

        # 准备更新数据（包含财务字段）
        update_data = {"fixed_amount": 20000.00}

        # 模拟请求（普通用户）
        from unittest.mock import Mock

        request = Mock()
        request.user = self.normal_user

        # 调用 API
        from apps.contracts.api.contract_api import update_contract
        from apps.contracts.schemas import ContractUpdate
        from apps.core.exceptions import PermissionDenied

        payload = ContractUpdate(**update_data)

        # 验证抛出权限异常（Service 层抛出 PermissionDenied，全局处理器转为 403）
        with pytest.raises(PermissionDenied) as exc_info:
            update_contract(request, contract.id, payload, confirm_finance=True)  # type: ignore[attr-defined]

        assert "管理员权限" in str(exc_info.value)

    def test_update_contract_finance_requires_confirmation(self):
        """测试更新财务数据需要二次确认"""
        # 创建合同
        contract = ContractFactory(fee_mode="fixed", fixed_amount=Decimal("10000.00"))

        # 准备更新数据（包含财务字段）
        update_data = {"fixed_amount": 20000.00}

        # 模拟请求（管理员）
        from unittest.mock import Mock

        request = Mock()
        request.user = self.admin_user

        # 调用 API（不确认）
        from ninja.errors import HttpError

        from apps.contracts.api.contract_api import update_contract
        from apps.contracts.schemas import ContractUpdate

        payload = ContractUpdate(**update_data)

        # 验证抛出异常
        with pytest.raises(HttpError) as exc_info:
            update_contract(request, contract.id, payload, confirm_finance=False)  # type: ignore[attr-defined]

        assert exc_info.value.status_code == 400
        assert "二次确认" in str(exc_info.value)

    def test_add_payments_success(self):
        """测试添加收款记录成功"""
        # 创建合同
        contract = ContractFactory(fee_mode="fixed", fixed_amount=Decimal("10000.00"))

        # 准备收款数据
        payments_data = [
            {
                "contract_id": contract.id,  # type: ignore[attr-defined]
                "amount": 5000.00,
                "received_at": "2024-01-01",
                "invoiced_amount": 5000.00,
                "note": "首期款",
            }
        ]

        # 模拟请求（管理员）
        from unittest.mock import Mock

        request = Mock()
        request.user = self.admin_user

        # 调用 API
        from apps.contracts.api.contract_api import update_contract
        from apps.contracts.schemas import ContractPaymentIn, ContractUpdate

        payload = ContractUpdate()
        payments = [ContractPaymentIn(**p) for p in payments_data]

        updated_contract = update_contract(request, contract.id, payload, confirm_finance=True, new_payments=payments)  # type: ignore[attr-defined]

        # 验证收款记录
        payments = ContractPayment.objects.filter(contract=contract)  # type: ignore[misc]
        assert payments.count() == 1
        assert float(payments[0].amount) == 5000.00
        assert payments[0].invoice_status == InvoiceStatus.INVOICED_FULL

    def test_add_payments_exceeds_fixed_amount(self):
        """测试添加收款超过固定金额"""
        # 创建合同
        contract = ContractFactory(fee_mode="fixed", fixed_amount=Decimal("10000.00"))

        # 准备收款数据（超过固定金额）
        payments_data = [
            {
                "contract_id": contract.id,  # type: ignore[attr-defined]
                "amount": 15000.00,
                "received_at": "2024-01-01",
                "invoiced_amount": 0,
                "note": "超额款",
            }
        ]

        # 模拟请求（管理员）
        from unittest.mock import Mock

        request = Mock()
        request.user = self.admin_user

        # 调用 API
        from apps.contracts.api.contract_api import update_contract
        from apps.contracts.schemas import ContractPaymentIn, ContractUpdate
        from apps.core.exceptions import ValidationException

        payload = ContractUpdate()
        payments = [ContractPaymentIn(**p) for p in payments_data]

        # 验证抛出异常（Service 层抛出 ValidationException，全局处理器转为 400）
        with pytest.raises(ValidationException) as exc_info:
            update_contract(request, contract.id, payload, confirm_finance=True, new_payments=payments)  # type: ignore[attr-defined]

        assert "超过" in str(exc_info.value)

    def test_delete_contract_success(self):
        """测试删除合同成功"""
        # 创建合同
        contract = ContractFactory()
        contract_id = contract.id  # type: ignore[attr-defined]

        # 模拟请求
        from unittest.mock import Mock

        request = Mock()
        request.user = self.admin_user

        # 调用 API
        from apps.contracts.api.contract_api import delete_contract

        result = delete_contract(request, contract_id)

        # 验证结果
        assert result["success"] is True

        # 验证合同已删除
        assert not Contract.objects.filter(id=contract_id).exists()

    def test_get_contract_success(self):
        """测试获取合同成功"""
        # 创建合同
        contract = ContractFactory(name="测试合同")

        # 模拟请求
        from unittest.mock import Mock

        request = Mock()
        request.user = self.admin_user
        request.perm_open_access = True

        # 调用 API
        from apps.contracts.api.contract_api import get_contract

        result = get_contract(request, contract.id)  # type: ignore[attr-defined]

        # 验证结果
        assert result.id == contract.id  # type: ignore[attr-defined]
        assert result.name == "测试合同"

    def test_list_contracts_success(self):
        """测试列表查询成功"""
        # 创建多个合同
        ContractFactory.create_batch(5, case_type="civil")
        ContractFactory.create_batch(3, case_type="criminal")

        # 模拟请求
        from unittest.mock import Mock

        request = Mock()
        request.user = self.admin_user
        request.perm_open_access = True

        # 调用 API
        from apps.contracts.api.contract_api import list_contracts

        # 测试不过滤
        result = list_contracts(request)
        assert len(result) == 8

        # 测试按案件类型过滤
        result = list_contracts(request, case_type="civil")
        assert len(result) == 5

        result = list_contracts(request, case_type="criminal")
        assert len(result) == 3
