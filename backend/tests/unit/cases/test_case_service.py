"""
CaseService 单元测试
"""

from decimal import Decimal
from unittest.mock import MagicMock, Mock

import pytest

from apps.cases.models import Case, CaseAssignment, CaseParty
from apps.cases.services import CaseService
from apps.core.exceptions import ConflictError, NotFoundError, ValidationException
from apps.core.interfaces import ContractDTO
from tests.factories.client_factories import ClientFactory
from tests.factories.contract_factories import ContractFactory
from tests.factories.organization_factories import LawFirmFactory, LawyerFactory


@pytest.mark.django_db
class TestCaseService:
    """案件服务测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        # 创建 Mock 合同服务
        self.mock_contract_service = Mock()

        # 创建 Service 实例（注入 Mock）
        self.service = CaseService(contract_service=self.mock_contract_service)

    def test_create_case_success(self):
        """测试创建案件成功"""
        # 创建真实的合同对象（避免外键约束错误）
        from apps.contracts.models import Contract, ContractAssignment
        from apps.organization.models import LawFirm, Lawyer

        law_firm = LawFirm.objects.create(name="测试律所")
        lawyer = Lawyer.objects.create(username="testlawyer", real_name="测试律师", law_firm=law_firm)

        contract = Contract.objects.create(
            name="测试合同", case_type="civil", status="active", representation_stages=["first_trial", "second_trial"]
        )
        # 使用 ContractAssignment 关联律师
        ContractAssignment.objects.create(contract=contract, lawyer=lawyer, is_primary=True)

        # 创建 Mock 用户（避免 is_authenticated 属性问题）
        user = Mock()
        user.is_authenticated = True
        user.id = 1

        # 准备测试数据
        data = {
            "name": "测试案件",
            "contract_id": contract.id,
            "current_stage": "first_trial",
            "is_archived": False,
        }

        # 配置 Mock 行为
        self.mock_contract_service.get_contract.return_value = ContractDTO(
            id=contract.id,
            name="测试合同",
            case_type="civil",
            status="active",
            representation_stages=["first_trial", "second_trial"],
        )
        self.mock_contract_service.validate_contract_active.return_value = True

        # 执行测试
        case = self.service.create_case(data, user=user)

        # 断言结果
        assert case.id is not None
        assert case.name == "测试案件"
        assert case.contract_id == contract.id
        assert case.current_stage == "first_trial"

        # 验证 Mock 调用
        self.mock_contract_service.get_contract.assert_called_with(contract.id)
        self.mock_contract_service.validate_contract_active.assert_called_with(contract.id)

    def test_create_case_contract_not_found(self):
        """测试创建案件时合同不存在"""
        # 创建 Mock 用户
        user = Mock()
        user.is_authenticated = True
        user.id = 1

        data = {
            "name": "测试案件",
            "contract_id": 999,
        }

        # 配置 Mock：合同不存在
        self.mock_contract_service.get_contract.return_value = None

        # 断言抛出异常
        with pytest.raises(ValidationException) as exc_info:
            self.service.create_case(data, user=user)

        assert "合同不存在" in exc_info.value.message  # type: ignore[operator]
        assert exc_info.value.code == "CONTRACT_NOT_FOUND"

    def test_create_case_contract_inactive(self):
        """测试创建案件时合同未激活"""
        # 创建 Mock 用户
        user = Mock()
        user.is_authenticated = True
        user.id = 1

        data = {
            "name": "测试案件",
            "contract_id": 1,
        }

        # 配置 Mock
        self.mock_contract_service.get_contract.return_value = ContractDTO(
            id=1, name="测试合同", case_type="civil", status="draft", representation_stages=[]
        )
        self.mock_contract_service.validate_contract_active.return_value = False

        # 断言抛出异常
        with pytest.raises(ValidationException) as exc_info:
            self.service.create_case(data, user=user)

        assert "合同未激活" in exc_info.value.message  # type: ignore[operator]
        assert exc_info.value.code == "CONTRACT_INACTIVE"

    def test_create_case_without_contract(self):
        """测试创建案件不关联合同"""
        # 创建 Mock 用户
        user = Mock()
        user.is_authenticated = True
        user.id = 1

        data = {
            "name": "测试案件",
            "is_archived": False,
        }

        # 执行测试（不应该调用合同服务）
        case = self.service.create_case(data, user=user)

        # 断言结果
        assert case.id is not None
        assert case.name == "测试案件"
        assert case.contract_id is None

        # 验证 Mock 未被调用
        self.mock_contract_service.get_contract.assert_not_called()

    def test_update_case_success(self):
        """测试更新案件成功"""
        # 创建 Mock 用户
        user = Mock()
        user.is_authenticated = True
        user.id = 1

        # 创建测试案件
        case = Case.objects.create(name="原案件名称", is_archived=False)

        # 准备更新数据
        data = {
            "name": "新案件名称",
            "current_stage": "second_trial",
        }

        # 配置 Mock
        self.mock_contract_service.get_contract.return_value = ContractDTO(
            id=1,
            name="测试合同",
            case_type="civil",
            status="active",
            representation_stages=["first_trial", "second_trial"],
        )

        # 执行测试
        updated_case = self.service.update_case(case.id, data, user=user)

        # 断言结果
        assert updated_case.name == "新案件名称"
        assert updated_case.current_stage == "second_trial"

        # 验证数据库
        case.refresh_from_db()
        assert case.name == "新案件名称"

    def test_update_case_not_found(self):
        """测试更新不存在的案件"""
        # 创建 Mock 用户
        user = Mock()
        user.is_authenticated = True
        user.id = 1

        data = {"name": "新名称"}

        # 断言抛出异常
        with pytest.raises(NotFoundError):
            self.service.update_case(999, data, user=user)

    def test_update_case_with_new_contract(self):
        """测试更新案件关联新合同"""
        # 创建真实的合同对象
        from apps.contracts.models import Contract, ContractAssignment
        from apps.organization.models import LawFirm, Lawyer

        law_firm = LawFirm.objects.create(name="测试律所")
        lawyer = Lawyer.objects.create(username="testlawyer", real_name="测试律师", law_firm=law_firm)

        new_contract = Contract.objects.create(
            name="新合同", case_type="criminal", status="active", representation_stages=[]
        )
        # 使用 ContractAssignment 关联律师
        ContractAssignment.objects.create(contract=new_contract, lawyer=lawyer, is_primary=True)

        # 创建 Mock 用户
        user = Mock()
        user.is_authenticated = True
        user.id = 1

        # 创建测试案件
        case = Case.objects.create(name="测试案件", is_archived=False)

        # 准备更新数据
        data = {
            "contract_id": new_contract.id,
        }

        # 配置 Mock
        self.mock_contract_service.get_contract.return_value = ContractDTO(
            id=new_contract.id, name="新合同", case_type="criminal", status="active", representation_stages=[]
        )

        # 执行测试
        updated_case = self.service.update_case(case.id, data, user=user)

        # 断言结果
        assert updated_case.contract_id == new_contract.id

        # 验证 Mock 调用
        self.mock_contract_service.get_contract.assert_called_with(new_contract.id)

    def test_delete_case_success(self):
        """测试删除案件成功"""
        # 创建 Mock 用户
        user = Mock()
        user.is_authenticated = True
        user.id = 1

        # 创建测试案件
        case = Case.objects.create(name="测试案件", is_archived=False)

        # 执行测试（返回 None）
        result = self.service.delete_case(case.id, user=user)

        # 断言返回 None
        assert result is None

        # 验证案件已删除
        assert not Case.objects.filter(id=case.id).exists()

    def test_delete_case_not_found(self):
        """测试删除不存在的案件"""
        # 创建 Mock 用户
        user = Mock()
        user.is_authenticated = True
        user.id = 1

        # 断言抛出异常
        with pytest.raises(NotFoundError):
            self.service.delete_case(999, user=user)

    def test_validate_stage_success(self):
        """测试验证阶段成功"""
        # 执行测试
        result = self.service._validate_stage(
            stage="first_trial", case_type="civil", representation_stages=["first_trial", "second_trial"]
        )

        # 断言结果
        assert result == "first_trial"

    def test_validate_stage_not_in_representation_stages(self):
        """测试验证阶段不在代理阶段范围内"""
        # 断言抛出异常
        with pytest.raises(ValidationException) as exc_info:
            self.service._validate_stage(
                stage="enforcement", case_type="civil", representation_stages=["first_trial", "second_trial"]
            )

        assert "阶段不在代理范围内" in str(exc_info.value.errors)

    def test_create_case_full_success(self):
        """测试创建完整案件成功"""
        # 创建真实的关联对象
        lawyer = LawyerFactory()
        contract = ContractFactory()
        # 使用 ContractAssignment 关联律师
        from apps.contracts.models import ContractAssignment

        ContractAssignment.objects.create(contract=contract, lawyer=lawyer, is_primary=True)  # type: ignore[misc]
        client1 = ClientFactory(name="客户1")
        client2 = ClientFactory(name="客户2")

        # 创建 Mock 用户
        user = Mock()
        user.is_authenticated = True
        user.id = lawyer.id  # type: ignore[attr-defined]

        # 准备测试数据
        data = {
            "case": {
                "name": "完整案件",
                "contract_id": contract.id,  # type: ignore[attr-defined]
                "is_archived": False,
            },
            "parties": [
                {"client_id": client1.id, "legal_status": "plaintiff"},  # type: ignore[attr-defined]
                {"client_id": client2.id, "legal_status": "defendant"},  # type: ignore[attr-defined]
            ],
            "assignments": [
                {"lawyer_id": lawyer.id},  # type: ignore[attr-defined]
            ],
            "logs": [
                {"content": "案件创建"},
            ],
            "supervising_authorities": [],
        }

        # 配置 Mock
        self.mock_contract_service.get_contract.return_value = ContractDTO(
            id=contract.id, name="测试合同", case_type="civil", status="active", representation_stages=[]  # type: ignore[attr-defined]
        )
        self.mock_contract_service.validate_contract_active.return_value = True

        # 执行测试
        result = self.service.create_case_full(data, actor_id=lawyer.id, user=user)  # type: ignore[attr-defined]

        # 断言结果
        assert result["case"].id is not None
        assert len(result["parties"]) == 2
        assert len(result["assignments"]) == 1
        assert len(result["logs"]) == 1

    def test_create_case_full_duplicate_party(self):
        """测试创建完整案件时当事人重复"""
        # 创建真实的客户对象
        client = ClientFactory(name="客户1")

        # 创建 Mock 用户
        user = Mock()
        user.is_authenticated = True
        user.id = 1

        # 创建测试案件
        case = Case.objects.create(name="测试案件", is_archived=False)
        CaseParty.objects.create(case=case, client_id=client.id, legal_status="plaintiff")  # type: ignore[attr-defined]

        # 准备测试数据（包含重复的当事人）
        data = {
            "case": {
                "name": "新案件",
                "is_archived": False,
            },
            "parties": [
                {"client_id": client.id, "legal_status": "plaintiff"},  # type: ignore[attr-defined]
            ],
            "assignments": [],
            "logs": [],
            "supervising_authorities": [],
        }

        # 配置 Mock
        self.mock_contract_service.get_contract.return_value = None

        # 先创建案件
        result = self.service.create_case_full(data, actor_id=None, user=user)

        # 尝试再次添加相同的当事人应该抛出异常
        data2 = {
            "case": {
                "name": "另一个案件",
                "is_archived": False,
            },
            "parties": [
                {"client_id": client.id, "legal_status": "plaintiff"},  # type: ignore[attr-defined]
            ],
            "assignments": [],
            "logs": [],
            "supervising_authorities": [],
        }

        # 这次应该成功，因为是不同的案件
        result2 = self.service.create_case_full(data2, actor_id=None, user=user)
        assert result2["case"].id != result["case"].id


@pytest.mark.django_db
class TestCaseServiceQueryOptimization:
    """案件服务查询优化测试"""

    def test_get_case_queryset_optimization(self):
        """测试 get_case_queryset 预加载优化"""
        # 创建测试数据
        case = Case.objects.create(name="测试案件", is_archived=False)

        # 创建 Service 实例
        service = CaseService()

        # 使用优化的查询集
        from django.db import connection, reset_queries
        from django.test.utils import override_settings

        with override_settings(DEBUG=True):
            reset_queries()

            # 获取案件
            qs = service.get_case_queryset().filter(id=case.id)
            case_obj = qs.first()

            # 访问关联对象不应该产生额外查询
            initial_query_count = len(connection.queries)

            # 访问预加载的关系
            _ = list(case_obj.parties.all())  # type: ignore[union-attr]
            _ = list(case_obj.assignments.all())  # type: ignore[union-attr]
            _ = list(case_obj.case_numbers.all())  # type: ignore[union-attr]

            # 查询次数不应该增加（因为已经预加载）
            final_query_count = len(connection.queries)

            # 由于使用了 prefetch_related，访问关联对象不会产生额外查询
            assert final_query_count == initial_query_count


@pytest.mark.django_db
class TestCaseServiceSearch:
    """案件服务搜索功能测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.service = CaseService()
        self.user = Mock()
        self.user.is_authenticated = True
        self.user.is_admin = False
        self.user.id = 1

    def test_search_by_case_number_exact_match(self):
        """测试按案号精确匹配搜索"""
        from apps.cases.models import CaseNumber

        # 创建测试案件和案号
        case = Case.objects.create(name="测试案件", is_archived=False)
        CaseNumber.objects.create(case=case, number="（2024）粤01民初12345号")

        # 执行精确搜索
        result = self.service.search_by_case_number(
            case_number="（2024）粤01民初12345号", user=self.user, perm_open_access=True, exact_match=True
        )

        # 断言结果
        assert result.count() == 1
        assert result.first().id == case.id  # type: ignore[union-attr]

    def test_search_by_case_number_fuzzy_match(self):
        """测试按案号模糊匹配搜索"""
        from apps.cases.models import CaseNumber

        # 创建测试案件和案号
        case1 = Case.objects.create(name="案件1", is_archived=False)
        case2 = Case.objects.create(name="案件2", is_archived=False)
        CaseNumber.objects.create(case=case1, number="（2024）粤01民初12345号")
        CaseNumber.objects.create(case=case2, number="（2024）粤01民初12346号")

        # 执行模糊搜索
        result = self.service.search_by_case_number(
            case_number="粤01民初1234", user=self.user, perm_open_access=True, exact_match=False
        )

        # 断言结果（应该匹配两个案件）
        assert result.count() == 2

    def test_search_by_case_number_normalize(self):
        """测试案号规范化搜索"""
        from apps.cases.models import CaseNumber

        # 创建测试案件（使用规范化的案号）
        case = Case.objects.create(name="测试案件", is_archived=False)
        CaseNumber.objects.create(case=case, number="（2024）粤01民初12345号")

        # 使用不同格式的案号搜索（英文括号、无"号"字）
        result = self.service.search_by_case_number(
            case_number="(2024)粤01民初12345", user=self.user, perm_open_access=True, exact_match=True
        )

        # 断言结果（应该能找到）
        assert result.count() == 1
        assert result.first().id == case.id  # type: ignore[union-attr]

    def test_search_by_case_number_with_permission(self):
        """测试按案号搜索时的权限控制"""
        from apps.cases.models import CaseNumber
        from apps.organization.models import LawFirm, Lawyer

        # 创建律师和案件
        law_firm = LawFirm.objects.create(name="测试律所")
        lawyer = Lawyer.objects.create(username="testlawyer", real_name="测试律师", law_firm=law_firm)

        case = Case.objects.create(name="测试案件", is_archived=False)
        CaseNumber.objects.create(case=case, number="（2024）粤01民初12345号")
        CaseAssignment.objects.create(case=case, lawyer=lawyer)

        # 配置用户权限
        org_access = {"lawyers": {lawyer.id}, "extra_cases": set()}

        # 执行搜索
        result = self.service.search_by_case_number(
            case_number="（2024）粤01民初12345号",
            user=self.user,
            org_access=org_access,
            perm_open_access=False,
            exact_match=True,
        )

        # 断言结果
        assert result.count() == 1

    def test_search_cases_by_name(self):
        """测试按案件名称搜索"""
        # 创建测试案件
        case1 = Case.objects.create(name="合同纠纷案件", is_archived=False)
        case2 = Case.objects.create(name="侵权纠纷案件", is_archived=False)

        # 执行搜索
        result = self.service.search_cases(query="合同", user=self.user, perm_open_access=True)

        # 断言结果
        assert len(result) == 1
        assert result[0].id == case1.id

    def test_search_cases_by_party_name(self):
        """测试按当事人姓名搜索"""
        from apps.client.models import Client

        # 创建客户和案件
        client = Client.objects.create(name="张三")
        case = Case.objects.create(name="测试案件", is_archived=False)
        CaseParty.objects.create(case=case, client=client, legal_status="plaintiff")

        # 执行搜索
        result = self.service.search_cases(query="张三", user=self.user, perm_open_access=True)

        # 断言结果
        assert len(result) == 1
        assert result[0].id == case.id

    def test_search_cases_empty_query(self):
        """测试空查询返回空列表"""
        result = self.service.search_cases(query="", user=self.user, perm_open_access=True)

        assert len(result) == 0

    def test_search_cases_with_limit(self):
        """测试搜索结果数量限制"""
        # 创建多个案件
        for i in range(15):
            Case.objects.create(name=f"测试案件{i}", is_archived=False)

        # 执行搜索（限制 10 条）
        result = self.service.search_cases(query="测试", limit=10, user=self.user, perm_open_access=True)

        # 断言结果
        assert len(result) == 10


@pytest.mark.django_db
class TestCaseServiceList:
    """案件服务列表功能测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.service = CaseService()
        self.user = Mock()
        self.user.is_authenticated = True
        self.user.is_admin = False
        self.user.id = 1

    def test_list_cases_all(self):
        """测试获取所有案件"""
        # 创建测试案件
        case1 = Case.objects.create(name="案件1", is_archived=False)
        case2 = Case.objects.create(name="案件2", is_archived=False)

        # 执行查询
        result = self.service.list_cases(perm_open_access=True)

        # 断言结果
        assert result.count() == 2

    def test_list_cases_with_admin_permission(self):
        """测试管理员权限获取所有案件"""
        # 创建测试案件
        Case.objects.create(name="案件1", is_archived=False)
        Case.objects.create(name="案件2", is_archived=False)

        # 配置管理员用户
        admin_user = Mock()
        admin_user.is_authenticated = True
        admin_user.is_admin = True

        # 执行查询
        result = self.service.list_cases(user=admin_user, perm_open_access=False)

        # 断言结果
        assert result.count() == 2

    def test_list_cases_with_lawyer_permission(self):
        """测试律师权限只能看到自己的案件"""
        from apps.organization.models import LawFirm, Lawyer

        # 创建律师
        law_firm = LawFirm.objects.create(name="测试律所")
        lawyer = Lawyer.objects.create(username="testlawyer", real_name="测试律师", law_firm=law_firm)

        # 创建案件
        case1 = Case.objects.create(name="我的案件", is_archived=False)
        case2 = Case.objects.create(name="其他案件", is_archived=False)

        # 只给第一个案件分配律师
        CaseAssignment.objects.create(case=case1, lawyer=lawyer)

        # 配置权限
        org_access = {"lawyers": {lawyer.id}, "extra_cases": set()}

        # 执行查询
        result = self.service.list_cases(user=self.user, org_access=org_access, perm_open_access=False)

        # 断言结果（只能看到分配给自己的案件）
        assert result.count() == 1
        assert result.first().id == case1.id  # type: ignore[union-attr]


@pytest.mark.django_db
class TestCaseServiceGetCase:
    """案件服务获取单个案件测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.service = CaseService()
        self.user = Mock()
        self.user.is_authenticated = True
        self.user.is_admin = False
        self.user.id = 1

    def test_get_case_success(self):
        """测试成功获取案件"""
        # 创建测试案件
        case = Case.objects.create(name="测试案件", is_archived=False)

        # 执行查询
        result = self.service.get_case(case_id=case.id, user=self.user, perm_open_access=True)

        # 断言结果
        assert result.id == case.id
        assert result.name == "测试案件"

    def test_get_case_not_found(self):
        """测试获取不存在的案件"""
        # 断言抛出异常
        with pytest.raises(NotFoundError):
            self.service.get_case(case_id=999, user=self.user, perm_open_access=True)

    def test_get_case_forbidden(self):
        """测试无权限访问案件"""
        from apps.core.exceptions import ForbiddenError

        # 创建测试案件
        case = Case.objects.create(name="测试案件", is_archived=False)

        # 配置无权限
        org_access: dict[str, set[int]] = {"lawyers": set(), "extra_cases": set()}

        # 断言抛出异常
        with pytest.raises(ForbiddenError):
            self.service.get_case(case_id=case.id, user=self.user, org_access=org_access, perm_open_access=False)

    def test_get_case_with_admin(self):
        """测试管理员可以访问任何案件"""
        # 创建测试案件
        case = Case.objects.create(name="测试案件", is_archived=False)

        # 配置管理员用户
        admin_user = Mock()
        admin_user.is_authenticated = True
        admin_user.is_admin = True

        # 执行查询
        result = self.service.get_case(case_id=case.id, user=admin_user, perm_open_access=False)

        # 断言结果
        assert result.id == case.id


@pytest.mark.django_db
class TestCaseServiceCheckAccess:
    """案件服务权限检查测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.service = CaseService()
        self.user = Mock()
        self.user.is_authenticated = True
        self.user.is_admin = False
        self.user.id = 1

    def test_check_case_access_admin(self):
        """测试管理员总是有权限"""
        # 创建测试案件
        case = Case.objects.create(name="测试案件", is_archived=False)

        # 配置管理员用户
        admin_user = Mock()
        admin_user.is_admin = True

        # 执行检查
        result = self.service.check_case_access(case=case, user=admin_user, org_access=None)

        # 断言结果
        assert result is True

    def test_check_case_access_extra_cases(self):
        """测试额外授权的案件"""
        # 创建测试案件
        case = Case.objects.create(name="测试案件", is_archived=False)

        # 配置额外授权
        org_access = {"lawyers": set(), "extra_cases": {case.id}}

        # 执行检查
        result = self.service.check_case_access(case=case, user=self.user, org_access=org_access)

        # 断言结果
        assert result is True

    def test_check_case_access_assigned_lawyer(self):
        """测试分配的律师有权限"""
        from apps.organization.models import LawFirm, Lawyer

        # 创建律师和案件
        law_firm = LawFirm.objects.create(name="测试律所")
        lawyer = Lawyer.objects.create(username="testlawyer", real_name="测试律师", law_firm=law_firm)

        case = Case.objects.create(name="测试案件", is_archived=False)
        CaseAssignment.objects.create(case=case, lawyer=lawyer)

        # 配置权限
        org_access = {"lawyers": {lawyer.id}, "extra_cases": set()}

        # 执行检查
        result = self.service.check_case_access(case=case, user=self.user, org_access=org_access)

        # 断言结果
        assert result is True

    def test_check_case_access_no_permission(self):
        """测试无权限访问"""
        # 创建测试案件
        case = Case.objects.create(name="测试案件", is_archived=False)

        # 配置无权限
        org_access: dict[str, set[int]] = {"lawyers": set(), "extra_cases": set()}

        # 执行检查
        result = self.service.check_case_access(case=case, user=self.user, org_access=org_access)

        # 断言结果
        assert result is False

    def test_check_case_access_no_org_access(self):
        """测试没有组织访问权限"""
        # 创建测试案件
        case = Case.objects.create(name="测试案件", is_archived=False)

        # 执行检查
        result = self.service.check_case_access(case=case, user=self.user, org_access=None)

        # 断言结果
        assert result is False
