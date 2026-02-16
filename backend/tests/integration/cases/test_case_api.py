"""
案件 API 集成测试

测试 API 端到端流程，包括：
- 创建案件的完整流程
- 列表查询和搜索
- 权限控制
- 异常场景
"""
import pytest
from django.test import Client
from apps.cases.models import Case
from apps.contracts.models import Contract
from apps.contracts.services.contract.contract_service import ContractService
from apps.organization.models import Lawyer, LawFirm
from apps.client.models import Client as ClientModel


@pytest.mark.django_db
class TestCaseAPI:
    """案件 API 集成测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        from apps.contracts.models import ContractAssignment
        
        # 创建测试数据
        self.law_firm = LawFirm.objects.create(name="测试律所")
        self.lawyer = Lawyer.objects.create(
            username="testlawyer",
            real_name="测试律师",
            law_firm=self.law_firm
        )

        self.contract = Contract.objects.create(
            name="测试合同",
            case_type="civil",
            status="active",
            representation_stages=["first_trial", "second_trial"]
        )
        # 使用 ContractAssignment 关联律师
        ContractAssignment.objects.create(
            contract=self.contract,
            lawyer=self.lawyer,
            is_primary=True
        )

        # 创建测试客户端
        self.client = Client()

    def test_create_case_success(self):
        """测试创建案件成功"""
        # 准备请求数据
        data = {
            "name": "测试案件",
            "contract_id": self.contract.id,
            "current_stage": "first_trial",
            "is_archived": False
        }

        # 发送请求（注意：这里需要认证，实际测试中需要设置认证）
        # response = self.client.post("/api/cases", json=data)

        # 由于没有完整的认证设置，我们直接测试 Service 层
        # 这里只是示例，实际应该测试完整的 HTTP 请求流程
        from apps.cases.services import CaseService
        from apps.contracts.services import ContractServiceAdapter
        from unittest.mock import Mock

        service = CaseService(contract_service=ContractServiceAdapter(contract_service=ContractService()))
        user = Mock()
        user.is_authenticated = True
        user.id = self.lawyer.id

        case = service.create_case(data, user=user)

        # 断言结果
        assert case.id is not None
        assert case.name == "测试案件"
        assert case.contract_id == self.contract.id

    def test_list_cases(self):
        """测试列表查询"""
        # 创建测试案件
        Case.objects.create(
            name="案件1",
            contract=self.contract,
            is_archived=False
        )
        Case.objects.create(
            name="案件2",
            contract=self.contract,
            is_archived=False
        )

        # 测试列表查询
        from apps.cases.services import CaseService
        from apps.contracts.services import ContractServiceAdapter

        service = CaseService(contract_service=ContractServiceAdapter(contract_service=ContractService()))
        cases = service.list_cases(
            case_type="civil",
            status=None,
            user=None,
            org_access=None,
            perm_open_access=True  # 开放访问用于测试
        )

        # 断言结果
        assert cases.count() >= 2

    def test_get_case_success(self):
        """测试获取单个案件成功"""
        # 创建测试案件
        case = Case.objects.create(
            name="测试案件",
            contract=self.contract,
            is_archived=False
        )

        # 测试获取案件
        from apps.cases.services import CaseService
        from apps.contracts.services import ContractServiceAdapter

        service = CaseService(contract_service=ContractServiceAdapter(contract_service=ContractService()))
        result = service.get_case(
            case_id=case.id,
            user=None,
            org_access=None,
            perm_open_access=True  # 开放访问用于测试
        )

        # 断言结果
        assert result.id == case.id
        assert result.name == "测试案件"

    def test_get_case_not_found(self):
        """测试获取不存在的案件"""
        from apps.cases.services import CaseService
        from apps.core.exceptions import NotFoundError
        from apps.contracts.services import ContractServiceAdapter

        service = CaseService(contract_service=ContractServiceAdapter(contract_service=ContractService()))

        # 断言抛出异常
        with pytest.raises(NotFoundError):
            service.get_case(
                case_id=999,
                user=None,
                org_access=None,
                perm_open_access=True
            )

    def test_update_case_success(self):
        """测试更新案件成功"""
        # 创建测试案件
        case = Case.objects.create(
            name="原名称",
            contract=self.contract,
            is_archived=False
        )
        from apps.cases.models import CaseAssignment
        CaseAssignment.objects.create(case=case, lawyer=self.lawyer)

        # 测试更新案件
        from apps.cases.services import CaseService
        from apps.contracts.services import ContractServiceAdapter
        from unittest.mock import Mock

        service = CaseService(contract_service=ContractServiceAdapter(contract_service=ContractService()))
        user = Mock()
        user.is_authenticated = True
        user.id = self.lawyer.id

        data = {"name": "新名称"}
        result = service.update_case(
            case.id,
            data,
            user=user,
            org_access={"lawyers": {self.lawyer.id}, "extra_cases": set()},
            perm_open_access=False,
        )

        # 断言结果
        assert result.name == "新名称"

        # 验证数据库
        case.refresh_from_db()
        assert case.name == "新名称"

    def test_delete_case_success(self):
        """测试删除案件成功"""
        # 创建测试案件
        case = Case.objects.create(
            name="测试案件",
            contract=self.contract,
            is_archived=False
        )
        from apps.cases.models import CaseAssignment
        CaseAssignment.objects.create(case=case, lawyer=self.lawyer)

        # 测试删除案件
        from apps.cases.services import CaseService
        from unittest.mock import Mock
        from apps.contracts.services import ContractServiceAdapter

        service = CaseService(contract_service=ContractServiceAdapter(contract_service=ContractService()))
        user = Mock()
        user.is_authenticated = True
        user.id = self.lawyer.id

        result = service.delete_case(
            case.id,
            user=user,
            org_access={"lawyers": {self.lawyer.id}, "extra_cases": set()},
            perm_open_access=False,
        )

        # 断言结果
        assert result is True

        # 验证案件已删除
        assert not Case.objects.filter(id=case.id).exists()

    def test_search_by_case_number(self):
        """测试通过案号搜索"""
        # 创建测试案件和案号
        case = Case.objects.create(
            name="测试案件",
            contract=self.contract,
            is_archived=False
        )

        from apps.cases.models import CaseNumber
        from apps.cases.utils import normalize_case_number

        # 使用规范化的案号存储
        normalized_number = normalize_case_number("（2024）京0101民初12345号")
        case_number_obj = CaseNumber.objects.create(
            case=case,
            number=normalized_number
        )

        # 验证案号已创建
        assert CaseNumber.objects.filter(case=case).exists()

        # 测试搜索（使用完整的案号）
        from apps.cases.services import CaseService
        from apps.contracts.services import ContractServiceAdapter

        service = CaseService(contract_service=ContractServiceAdapter(contract_service=ContractService()))
        results = service.search_by_case_number(
            case_number="（2024）京0101民初12345号",  # 使用完整格式
            user=None,
            org_access=None,
            perm_open_access=True
        )

        # 断言结果
        assert results.count() >= 1, f"Expected at least 1 result, got {results.count()}. Case number in DB: {case_number_obj.number}"
        assert case.id in [c.id for c in results]

    def test_permission_denied(self):
        """测试权限拒绝"""
        # 创建测试案件
        case = Case.objects.create(
            name="测试案件",
            contract=self.contract,
            is_archived=False
        )

        # 测试无权限访问
        from apps.cases.services import CaseService
        from apps.core.exceptions import ForbiddenError
        from unittest.mock import Mock
        from apps.contracts.services import ContractServiceAdapter

        service = CaseService(contract_service=ContractServiceAdapter(contract_service=ContractService()))
        user = Mock()
        user.is_authenticated = True
        user.id = 999  # 不同的用户
        user.is_admin = False

        # 断言抛出权限异常
        with pytest.raises(ForbiddenError):
            service.get_case(
                case_id=case.id,
                user=user,
                org_access={"lawyers": set(), "extra_cases": set()},
                perm_open_access=False
            )
