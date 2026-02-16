"""
ContractService 单元测试
"""

from decimal import Decimal
from unittest.mock import MagicMock, Mock

import pytest

from apps.contracts.models import Contract, ContractAssignment, ContractParty, FeeMode
from apps.contracts.services import ContractService
from apps.core.exceptions import NotFoundError, PermissionDenied, ValidationException
from apps.core.interfaces import ContractDTO, LawyerDTO
from tests.factories.client_factories import ClientFactory
from tests.factories.contract_factories import ContractAssignmentFactory, ContractFactory, ContractPaymentFactory
from tests.factories.organization_factories import LawFirmFactory, LawyerFactory


@pytest.mark.django_db
class TestContractService:
    """合同服务测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        # 创建 Mock 案件服务
        self.mock_case_service = Mock()

        # 创建 Service 实例（注入 Mock）
        self.service = ContractService(case_service=self.mock_case_service)

    def test_create_contract_success(self):
        """测试创建合同成功"""
        # 准备测试数据
        data = {
            "name": "测试合同",
            "case_type": "civil",
            "status": "active",
            "fee_mode": FeeMode.FIXED,
            "fixed_amount": Decimal("10000.00"),
            "representation_stages": ["first_trial"],
        }

        # 执行测试
        contract = self.service.create_contract(data)

        # 断言结果
        assert contract.id is not None
        assert contract.name == "测试合同"
        assert contract.case_type == "civil"
        assert contract.status == "active"
        assert contract.fee_mode == FeeMode.FIXED
        assert contract.fixed_amount == Decimal("10000.00")

    def test_create_contract_with_lawyers(self):
        """测试创建合同并指派律师"""
        # 创建律师
        lawyer1 = LawyerFactory()
        lawyer2 = LawyerFactory()

        # 准备测试数据
        data = {
            "name": "测试合同",
            "case_type": "civil",
            "status": "active",
            "fee_mode": FeeMode.FIXED,
            "fixed_amount": Decimal("10000.00"),
            "lawyer_ids": [lawyer1.id, lawyer2.id],
        }

        # 执行测试
        contract = self.service.create_contract(data)

        # 断言结果
        assert contract.id is not None
        assert contract.assignments.count() == 2

    def test_create_contract_invalid_fee_mode(self):
        """测试创建合同时收费模式验证失败"""
        # 准备测试数据（固定收费但没有金额）
        data = {
            "name": "测试合同",
            "case_type": "civil",
            "status": "active",
            "fee_mode": FeeMode.FIXED,
            "fixed_amount": None,
        }

        # 断言抛出异常
        with pytest.raises(ValidationException) as exc_info:
            self.service.create_contract(data)

        assert "固定收费模式必须指定金额" in str(exc_info.value.message)

    def test_update_contract_success(self):
        """测试更新合同成功"""
        # 创建测试合同
        contract = ContractFactory(name="原合同名称")

        # 准备更新数据
        data = {
            "name": "新合同名称",
            "status": "completed",
        }

        # 执行测试
        updated_contract = self.service.update_contract(contract.id, data)

        # 断言结果
        assert updated_contract.name == "新合同名称"
        assert updated_contract.status == "completed"

        # 验证数据库
        contract.refresh_from_db()
        assert contract.name == "新合同名称"

    def test_update_contract_not_found(self):
        """测试更新不存在的合同"""
        data = {"name": "新名称"}

        # 断言抛出异常
        with pytest.raises(NotFoundError):
            self.service.update_contract(999, data)

    def test_delete_contract_success(self):
        """测试删除合同成功"""
        # 创建测试合同
        contract = ContractFactory()

        # 执行测试
        result = self.service.delete_contract(contract.id)

        # 断言结果
        assert result is True

        # 验证合同已删除
        assert not Contract.objects.filter(id=contract.id).exists()

    def test_delete_contract_not_found(self):
        """测试删除不存在的合同"""
        # 断言抛出异常
        with pytest.raises(NotFoundError):
            self.service.delete_contract(999)

    def test_get_contract_success(self):
        """测试成功获取合同"""
        # 创建测试合同
        contract = ContractFactory()

        # 执行查询
        result = self.service.get_contract(contract_id=contract.id, perm_open_access=True)

        # 断言结果
        assert result.id == contract.id
        assert result.name == contract.name

    def test_get_contract_not_found(self):
        """测试获取不存在的合同"""
        # 断言抛出异常
        with pytest.raises(NotFoundError):
            self.service.get_contract(contract_id=999, perm_open_access=True)

    def test_get_contract_permission_denied(self):
        """测试无权限访问合同"""
        # 创建测试合同
        contract = ContractFactory()

        # 创建 Mock 用户
        user = Mock()
        user.is_authenticated = True
        user.is_admin = False
        user.id = 1

        # 配置无权限
        org_access = {
            "lawyers": set(),
        }

        # 断言抛出异常
        with pytest.raises(PermissionDenied):
            self.service.get_contract(contract_id=contract.id, user=user, org_access=org_access, perm_open_access=False)

    def test_get_contract_with_admin(self):
        """测试管理员可以访问任何合同"""
        # 创建测试合同
        contract = ContractFactory()

        # 配置管理员用户
        admin_user = Mock()
        admin_user.is_authenticated = True
        admin_user.is_admin = True

        # 执行查询
        result = self.service.get_contract(contract_id=contract.id, user=admin_user, perm_open_access=False)

        # 断言结果
        assert result.id == contract.id

    def test_get_contract_with_assigned_lawyer(self):
        """测试分配的律师有权限访问合同"""
        # 创建律师和合同
        lawyer = LawyerFactory()
        contract = ContractFactory()
        ContractAssignmentFactory(contract=contract, lawyer=lawyer)

        # 配置用户
        user = Mock()
        user.is_authenticated = True
        user.is_admin = False
        user.id = lawyer.id

        # 配置权限
        org_access = {
            "lawyers": {lawyer.id},
        }

        # 执行查询
        result = self.service.get_contract(
            contract_id=contract.id, user=user, org_access=org_access, perm_open_access=False
        )

        # 断言结果
        assert result.id == contract.id

    def test_list_contracts_all(self):
        """测试获取所有合同"""
        # 创建测试合同
        contract1 = ContractFactory(name="合同1")
        contract2 = ContractFactory(name="合同2")

        # 执行查询
        result = self.service.list_contracts(perm_open_access=True)

        # 断言结果
        assert result.count() == 2

    def test_list_contracts_filter_by_case_type(self):
        """测试按案件类型过滤合同"""
        # 创建不同类型的合同
        ContractFactory(case_type="civil")
        ContractFactory(case_type="criminal")

        # 执行查询
        result = self.service.list_contracts(case_type="civil", perm_open_access=True)

        # 断言结果
        assert result.count() == 1
        assert result.first().case_type == "civil"

    def test_list_contracts_filter_by_status(self):
        """测试按状态过滤合同"""
        # 创建不同状态的合同
        ContractFactory(status="active")
        ContractFactory(status="completed")

        # 执行查询
        result = self.service.list_contracts(status="active", perm_open_access=True)

        # 断言结果
        assert result.count() == 1
        assert result.first().status == "active"

    def test_list_contracts_with_admin_permission(self):
        """测试管理员权限获取所有合同"""
        # 创建测试合同
        ContractFactory()
        ContractFactory()

        # 配置管理员用户
        admin_user = Mock()
        admin_user.is_authenticated = True
        admin_user.is_admin = True

        # 执行查询
        result = self.service.list_contracts(user=admin_user, perm_open_access=False)

        # 断言结果
        assert result.count() == 2

    def test_list_contracts_with_lawyer_permission(self):
        """测试律师权限只能看到自己的合同"""
        # 创建律师
        lawyer = LawyerFactory()

        # 创建合同
        contract1 = ContractFactory(name="我的合同")
        contract2 = ContractFactory(name="其他合同")

        # 只给第一个合同分配律师
        ContractAssignmentFactory(contract=contract1, lawyer=lawyer)

        # 配置用户
        user = Mock()
        user.is_authenticated = True
        user.is_admin = False
        user.id = lawyer.id

        # 配置权限
        org_access = {
            "lawyers": {lawyer.id},
        }

        # 执行查询
        result = self.service.list_contracts(user=user, org_access=org_access, perm_open_access=False)

        # 断言结果（只能看到分配给自己的合同）
        assert result.count() == 1
        assert result.first().id == contract1.id

    def test_get_finance_summary(self):
        """测试获取合同财务汇总"""
        # 创建合同和收款记录
        contract = ContractFactory(fee_mode=FeeMode.FIXED, fixed_amount=Decimal("10000.00"))
        ContractPaymentFactory(contract=contract, amount=Decimal("3000.00"), invoiced_amount=Decimal("3000.00"))
        ContractPaymentFactory(contract=contract, amount=Decimal("2000.00"), invoiced_amount=Decimal("1000.00"))

        # 执行测试
        summary = self.service.get_finance_summary(contract.id)

        # 断言结果
        assert summary["contract_id"] == contract.id
        assert summary["total_received"] == 5000.00
        assert summary["total_invoiced"] == 4000.00
        assert summary["unpaid_amount"] == 5000.00  # 10000 - 5000

    def test_get_finance_summary_hourly_fee(self):
        """测试按小时收费的合同财务汇总"""
        # 创建按小时收费的合同
        contract = ContractFactory(fee_mode=FeeMode.HOURLY, fixed_amount=None)
        ContractPaymentFactory(contract=contract, amount=Decimal("1000.00"))

        # 执行测试
        summary = self.service.get_finance_summary(contract.id)

        # 断言结果
        assert summary["total_received"] == 1000.00
        assert summary["unpaid_amount"] is None  # 按小时收费没有未收金额

    def test_add_party_success(self):
        """测试添加当事人成功"""
        # 创建合同和客户
        contract = ContractFactory()
        client = ClientFactory()

        # 执行测试
        party = self.service.add_party(contract.id, client.id)

        # 断言结果
        assert party.id is not None
        assert party.contract_id == contract.id
        assert party.client_id == client.id

    def test_add_party_contract_not_found(self):
        """测试添加当事人时合同不存在"""
        client = ClientFactory()

        # 断言抛出异常
        with pytest.raises(NotFoundError):
            self.service.add_party(999, client.id)

    def test_remove_party_success(self):
        """测试移除当事人成功"""
        # 创建合同、客户和当事人关系
        contract = ContractFactory()
        client = ClientFactory()
        ContractParty.objects.create(contract=contract, client=client)

        # 执行测试
        result = self.service.remove_party(contract.id, client.id)

        # 断言结果
        assert result is True

        # 验证当事人已删除
        assert not ContractParty.objects.filter(contract_id=contract.id, client_id=client.id).exists()

    def test_remove_party_not_found(self):
        """测试移除不存在的当事人"""
        contract = ContractFactory()

        # 执行测试（不存在的当事人）
        result = self.service.remove_party(contract.id, 999)

        # 断言结果（返回 False）
        assert result is False

    def test_update_contract_lawyers(self):
        """测试更新合同律师"""
        # 创建合同和律师
        contract = ContractFactory()
        lawyer1 = LawyerFactory()
        lawyer2 = LawyerFactory()

        # 执行测试
        assignments = self.service.update_contract_lawyers(contract.id, [lawyer1.id, lawyer2.id])

        # 断言结果
        assert len(assignments) == 2
        assert contract.assignments.count() == 2

    def test_validate_fee_mode_fixed_without_amount(self):
        """测试固定收费模式验证：缺少金额"""
        data = {
            "fee_mode": FeeMode.FIXED,
            "fixed_amount": None,
        }

        # 断言抛出异常
        with pytest.raises(ValidationException) as exc_info:
            self.service._validate_fee_mode(data)

        assert "固定收费模式必须指定金额" in str(exc_info.value.message)

    def test_validate_fee_mode_hourly_with_amount(self):
        """测试按小时收费模式验证：不应有固定金额"""
        data = {
            "fee_mode": FeeMode.HOURLY,
            "fixed_amount": Decimal("10000.00"),
        }

        # 断言抛出异常
        with pytest.raises(ValidationException) as exc_info:
            self.service._validate_fee_mode(data)

        assert "按小时收费模式不应指定固定金额" in str(exc_info.value.message)

    def test_validate_stages_success(self):
        """测试验证代理阶段成功"""
        stages = ["first_trial", "second_trial"]

        # 执行测试
        result = self.service._validate_stages(stages, "civil")

        # 断言结果
        assert result == stages

    def test_get_all_parties(self):
        """测试获取合同所有当事人"""
        # 创建合同和当事人
        contract = ContractFactory()
        client1 = ClientFactory(name="客户1")
        client2 = ClientFactory(name="客户2")
        ContractParty.objects.create(contract=contract, client=client1)
        ContractParty.objects.create(contract=contract, client=client2)

        # 执行测试
        parties = self.service.get_all_parties(contract.id)

        # 断言结果
        assert len(parties) == 2


@pytest.mark.django_db
class TestContractServiceQueryOptimization:
    """合同服务查询优化测试"""

    def test_get_contract_queryset_optimization(self):
        """测试 get_contract_queryset 预加载优化"""
        # 创建测试数据
        contract = ContractFactory()
        lawyer = LawyerFactory()
        ContractAssignmentFactory(contract=contract, lawyer=lawyer)

        # 创建 Service 实例
        service = ContractService()

        # 使用优化的查询集
        from django.db import connection, reset_queries
        from django.test.utils import override_settings

        with override_settings(DEBUG=True):
            reset_queries()

            # 获取合同
            qs = service.get_contract_queryset().filter(id=contract.id)
            contract_obj = qs.first()

            # 访问关联对象不应该产生额外查询
            initial_query_count = len(connection.queries)

            # 访问预加载的关系
            _ = list(contract_obj.cases.all())
            _ = list(contract_obj.payments.all())
            _ = list(contract_obj.assignments.all())

            # 查询次数不应该增加（因为已经预加载）
            final_query_count = len(connection.queries)

            # 由于使用了 prefetch_related，访问关联对象不会产生额外查询
            assert final_query_count == initial_query_count


@pytest.mark.django_db
class TestContractServiceAdapter:
    """合同服务适配器测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        from apps.contracts.services.contract_service import ContractServiceAdapter

        self.adapter = ContractServiceAdapter()

    def test_get_contract_returns_dto(self):
        """测试获取合同返回 DTO"""
        # 创建测试合同
        contract = ContractFactory()

        # 执行测试
        dto = self.adapter.get_contract(contract.id)

        # 断言结果
        assert dto is not None
        assert dto.id == contract.id
        assert dto.name == contract.name

    def test_get_contract_not_found_returns_none(self):
        """测试获取不存在的合同返回 None"""
        # 执行测试
        dto = self.adapter.get_contract(999)

        # 断言结果
        assert dto is None

    def test_get_contract_stages(self):
        """测试获取合同代理阶段"""
        # 创建测试合同
        contract = ContractFactory(representation_stages=["first_trial", "second_trial"])

        # 执行测试
        stages = self.adapter.get_contract_stages(contract.id)

        # 断言结果
        assert stages == ["first_trial", "second_trial"]

    def test_validate_contract_active(self):
        """测试验证合同是否激活"""
        # 创建激活的合同
        active_contract = ContractFactory(status="active")

        # 执行测试
        result = self.adapter.validate_contract_active(active_contract.id)

        # 断言结果
        assert result is True

    def test_validate_contract_inactive(self):
        """测试验证合同未激活"""
        # 创建未激活的合同
        inactive_contract = ContractFactory(status="draft")

        # 执行测试
        result = self.adapter.validate_contract_active(inactive_contract.id)

        # 断言结果
        assert result is False

    def test_get_contracts_by_ids(self):
        """测试批量获取合同"""
        # 创建测试合同
        contract1 = ContractFactory()
        contract2 = ContractFactory()

        # 执行测试
        dtos = self.adapter.get_contracts_by_ids([contract1.id, contract2.id])

        # 断言结果
        assert len(dtos) == 2
        assert dtos[0].id == contract1.id
        assert dtos[1].id == contract2.id

    def test_get_contract_assigned_lawyer_id(self):
        """测试获取合同主要负责律师 ID"""
        # 创建合同和律师
        contract = ContractFactory()
        lawyer = LawyerFactory()
        ContractAssignmentFactory(contract=contract, lawyer=lawyer, is_primary=True)

        # 执行测试
        lawyer_id = self.adapter.get_contract_assigned_lawyer_id(contract.id)

        # 断言结果
        assert lawyer_id == lawyer.id

    def test_get_contract_assigned_lawyer_id_no_primary(self):
        """测试获取合同主要负责律师 ID（无主要律师）"""
        # 创建合同
        contract = ContractFactory()

        # 执行测试
        lawyer_id = self.adapter.get_contract_assigned_lawyer_id(contract.id)

        # 断言结果
        assert lawyer_id is None

    def test_get_contract_lawyers(self):
        """测试获取合同所有律师"""
        # 创建合同和律师
        contract = ContractFactory()
        lawyer1 = LawyerFactory()
        lawyer2 = LawyerFactory()
        ContractAssignmentFactory(contract=contract, lawyer=lawyer1)
        ContractAssignmentFactory(contract=contract, lawyer=lawyer2)

        # 执行测试
        lawyers = self.adapter.get_contract_lawyers(contract.id)

        # 断言结果
        assert len(lawyers) == 2
