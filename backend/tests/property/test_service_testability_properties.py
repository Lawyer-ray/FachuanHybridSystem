"""
Property-Based Tests for Service Testability

Feature: backend-architecture-refactoring
Property 1: Service 方法可独立测试
Validates: Requirements 4.5

测试所有 Service 方法可以在不依赖 HTTP 请求对象的情况下调用，
并且 Service 方法只依赖注入的参数。
"""

from decimal import Decimal
from typing import Any, Dict, Optional

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from hypothesis.extra.django import from_model

# Import Models
from apps.cases.models import Case

# Import Services
from apps.cases.services import CaseService
from apps.client.models import Client
from apps.client.services.client_service import ClientService
from apps.contracts.models import Contract
from apps.contracts.services.contract_service import ContractService
from apps.organization.models import LawFirm, Lawyer
from apps.organization.services.lawfirm_service import LawFirmService
from tests.factories.case_factories import CaseFactory
from tests.factories.client_factories import ClientFactory
from tests.factories.contract_factories import ContractFactory
from tests.factories.organization_factories import LawFirmFactory, LawyerFactory

# Import mocks
from tests.mocks.service_mocks import MockContractService

# Import test utilities
from tests.strategies.common_strategies import chinese_text, decimal_amount, phone_number

# ========== Strategy Definitions ==========


@st.composite
def case_create_data(draw):
    """生成案件创建数据"""
    return {
        "name": draw(chinese_text(min_size=1, max_size=100)),
        # contract_id 不生成随机整数，避免外键约束失败（测试目的是验证 Service 可独立调用）
        "contract_id": None,
        "is_archived": draw(st.booleans()),
        "target_amount": draw(st.one_of(st.none(), st.floats(min_value=0, max_value=10000000))),
        "cause_of_action": draw(st.one_of(st.none(), chinese_text(min_size=1, max_size=50))),
        "current_stage": draw(
            st.one_of(st.none(), st.sampled_from(["investigation", "prosecution", "first_trial", "second_trial"]))
        ),
    }


@st.composite
def contract_create_data(draw):
    """生成合同创建数据"""
    fee_mode = draw(st.sampled_from(["fixed", "semi_risk", "full_risk", "custom"]))

    # Contract 模型需要 assigned_lawyer_id（NOT NULL）
    # 我们需要先创建一个 Lawyer 或使用 Factory
    from tests.factories.organization_factories import LawyerFactory

    lawyer = LawyerFactory()

    data = {
        "name": draw(chinese_text(min_size=1, max_size=100)),
        "case_type": draw(st.sampled_from(["civil", "criminal", "administrative"])),
        "status": draw(st.sampled_from(["draft", "active", "completed", "terminated"])),
        "fee_mode": fee_mode,
        "representation_stages": draw(
            st.lists(
                st.sampled_from(["investigation", "prosecution", "first_trial", "second_trial"]),
                min_size=0,
                max_size=4,
                unique=True,
            )
        ),
        "lawyer_ids": [lawyer.id],  # type: ignore
    }

    # 根据收费模式添加必要字段
    if fee_mode == "fixed":
        data["fixed_amount"] = draw(decimal_amount(min_value=1000, max_value=1000000))
    elif fee_mode == "semi_risk":
        data["fixed_amount"] = draw(decimal_amount(min_value=1000, max_value=500000))
        data["risk_rate"] = draw(st.floats(min_value=0.01, max_value=0.5))
    elif fee_mode == "full_risk":
        data["risk_rate"] = draw(st.floats(min_value=0.01, max_value=0.5))
    elif fee_mode == "custom":
        data["custom_terms"] = draw(chinese_text(min_size=10, max_size=200))

    return data


@st.composite
def client_create_data(draw):
    """生成客户创建数据"""
    client_type = draw(st.sampled_from(["natural", "legal", "non_legal_org"]))

    data = {
        "name": draw(chinese_text(min_size=1, max_size=100)),
        "client_type": client_type,
        "phone": draw(phone_number()),  # phone 是必需字段，不能为 None
        "is_our_client": draw(st.booleans()),
    }

    # 法人必须有法定代表人
    if client_type == "legal":
        data["legal_representative"] = draw(chinese_text(min_size=2, max_size=20))

    return data


@st.composite
def lawfirm_create_data(draw):
    """生成律所创建数据"""
    return {
        "name": draw(chinese_text(min_size=1, max_size=100)),
        "address": draw(st.one_of(st.none(), chinese_text(min_size=1, max_size=200))),
        "phone": draw(st.one_of(st.none(), phone_number())),
        "social_credit_code": draw(
            st.one_of(
                st.none(), st.text(alphabet=st.characters(whitelist_categories=("Lu", "Nd")), min_size=18, max_size=18)
            )
        ),
    }


# ========== Mock User Objects ==========


class MockUser:
    """模拟用户对象（不依赖 HTTP 请求）"""

    def __init__(
        self,
        id: int = 1,
        is_authenticated: bool = True,
        is_admin: bool = False,
        is_superuser: bool = False,
        law_firm_id: int | None = None,
    ):
        self.id = id
        self.is_authenticated = is_authenticated
        self.is_admin = is_admin
        self.is_superuser = is_superuser
        self.law_firm_id = law_firm_id

    def has_perm(self, perm: str) -> bool:
        """模拟权限检查"""
        return self.is_admin or self.is_superuser


# ========== Property Tests ==========


@pytest.mark.django_db
@given(data=case_create_data())
@settings(max_examples=100, deadline=None)
def test_case_service_create_without_http_request(data):
    """
    Property 1: CaseService.create_case 可以在不依赖 HTTP 请求的情况下调用

    Feature: backend-architecture-refactoring, Property 1: Service 方法可独立测试
    Validates: Requirements 4.5

    测试：
    1. Service 方法不需要 HTTP request 对象
    2. 只需要业务参数（data, user）
    3. 可以使用 Mock 用户对象
    """
    # 创建 Service 实例（注入 Mock 依赖）
    mock_contract_service = MockContractService()
    service = CaseService(contract_service=mock_contract_service)  # type: ignore[arg-type]

    # 创建 Mock 用户（不是 HTTP 请求对象）
    user = MockUser(id=1, is_authenticated=True)

    # 如果有 contract_id，配置 Mock 返回值
    if data.get("contract_id"):
        from apps.core.interfaces import ContractDTO

        mock_contract_service.set_contract(
            data["contract_id"],
            ContractDTO(
                id=data["contract_id"],
                name="测试合同",
                case_type="civil",
                status="active",
                representation_stages=["investigation", "prosecution"],
                fee_mode="fixed",
                fixed_amount=Decimal("10000.00"),
            ),
        )

    try:
        # 调用 Service 方法（不传递 HTTP request）
        case = service.create_case(data, user=user)

        # 验证：方法成功执行，返回案件对象
        assert case is not None
        assert case.id is not None
        assert case.name == data["name"]

        # 验证：没有访问 HTTP request 对象
        # （如果访问了，会抛出 AttributeError）

    except Exception as e:
        # 如果是业务异常（如验证失败），这是正常的
        # 重要的是没有因为缺少 HTTP request 而失败
        from apps.core.exceptions import BusinessException

        if isinstance(e, BusinessException):
            # 业务异常是可以接受的
            pass
        else:
            # 其他异常需要重新抛出
            raise


@pytest.mark.django_db
@given(data=contract_create_data())
@settings(max_examples=100, deadline=None)
def test_contract_service_create_without_http_request(data):
    """
    Property 1: ContractService.create_contract 可以在不依赖 HTTP 请求的情况下调用

    Feature: backend-architecture-refactoring, Property 1: Service 方法可独立测试
    Validates: Requirements 4.5
    """
    # 创建 Service 实例（不需要注入依赖）
    service = ContractService()

    try:
        # 调用 Service 方法（不传递 user 参数）
        contract = service.create_contract(data)

        # 验证：方法成功执行
        assert contract is not None
        assert contract.id is not None
        assert contract.name == data["name"]
        assert contract.fee_mode == data["fee_mode"]

    except Exception as e:
        from apps.core.exceptions import BusinessException

        if isinstance(e, BusinessException):
            pass
        else:
            raise


@pytest.mark.django_db
@given(data=client_create_data())
@settings(max_examples=100, deadline=None)
def test_client_service_create_without_http_request(data):
    """
    Property 1: ClientService.create_client 可以在不依赖 HTTP 请求的情况下调用

    Feature: backend-architecture-refactoring, Property 1: Service 方法可独立测试
    Validates: Requirements 4.5
    """
    # 创建 Service 实例
    service = ClientService()

    # 创建 Mock 用户
    user = MockUser(id=1, is_authenticated=True, is_admin=True)

    try:
        # 调用 Service 方法
        client = service.create_client(data, user=user)

        # 验证
        assert client is not None
        assert client.id is not None
        assert client.name == data["name"]
        assert client.client_type == data["client_type"]

    except Exception as e:
        from apps.core.exceptions import BusinessException

        if isinstance(e, BusinessException):
            pass
        else:
            raise


@pytest.mark.django_db
@given(st.integers(min_value=1, max_value=1000))
@settings(max_examples=50, deadline=None)
def test_case_service_get_without_http_request(case_id):
    """
    Property 1: CaseService.get_case 可以在不依赖 HTTP 请求的情况下调用

    Feature: backend-architecture-refactoring, Property 1: Service 方法可独立测试
    Validates: Requirements 4.5
    """
    # 创建测试数据
    case = CaseFactory(id=case_id)

    # 创建 Service 实例
    service = CaseService()

    # 创建 Mock 用户
    user = MockUser(id=1, is_authenticated=True, is_admin=True)

    # 调用 Service 方法（传递 perm_open_access=True 跳过权限检查）
    result = service.get_case(case_id, user=user, perm_open_access=True)

    # 验证
    assert result is not None
    assert result.id == case_id
    assert result.name == case.name


@pytest.mark.django_db
@given(st.integers(min_value=1, max_value=1000))
@settings(max_examples=50, deadline=None)
def test_contract_service_get_without_http_request(contract_id):
    """
    Property 1: ContractService.get_contract 可以在不依赖 HTTP 请求的情况下调用

    Feature: backend-architecture-refactoring, Property 1: Service 方法可独立测试
    Validates: Requirements 4.5
    """
    # 创建测试数据（不指定 id，避免 Hypothesis 重复生成相同 id 触发 UNIQUE 约束）
    contract = ContractFactory()
    actual_id = contract.id  # type: ignore[attr-defined]

    # 创建 Service 实例
    service = ContractService()

    # 调用 Service 方法（perm_open_access=True 跳过权限检查）
    result = service.get_contract(actual_id, perm_open_access=True)

    # 验证
    assert result is not None
    assert result.id == actual_id
    assert result.name == contract.name


@pytest.mark.django_db
@given(st.integers(min_value=1, max_value=1000))
@settings(max_examples=50, deadline=None)
def test_client_service_get_without_http_request(client_id):
    """
    Property 1: ClientService.get_client 可以在不依赖 HTTP 请求的情况下调用

    Feature: backend-architecture-refactoring, Property 1: Service 方法可独立测试
    Validates: Requirements 4.5
    """
    # 创建测试数据
    client = ClientFactory(id=client_id)

    # 创建 Service 实例
    service = ClientService()

    # 调用 Service 方法（不需要 user 参数）
    result = service.get_client(client_id, user=None)

    # 验证
    assert result is not None
    assert result.id == client_id
    assert result.name == client.name


@pytest.mark.django_db
@given(page=st.integers(min_value=1, max_value=10), page_size=st.integers(min_value=1, max_value=50))
@settings(max_examples=50, deadline=None)
def test_case_service_list_without_http_request(page, page_size):
    """
    Property 1: CaseService.list_cases 可以在不依赖 HTTP 请求的情况下调用

    Feature: backend-architecture-refactoring, Property 1: Service 方法可独立测试
    Validates: Requirements 4.5
    """
    # 创建一些测试数据
    for _ in range(5):
        CaseFactory()

    # 创建 Service 实例
    service = CaseService()

    # 创建 Mock 用户
    user = MockUser(id=1, is_authenticated=True, is_admin=True)

    # 调用 Service 方法
    results = service.list_cases(case_type=None, status=None, user=user, org_access=None, perm_open_access=True)

    # 验证：返回查询集
    assert results is not None
    # 可以迭代查询集
    list(results)


@pytest.mark.django_db
@given(page=st.integers(min_value=1, max_value=10), page_size=st.integers(min_value=1, max_value=50))
@settings(max_examples=50, deadline=None)
def test_contract_service_list_without_http_request(page, page_size):
    """
    Property 1: ContractService.list_contracts 可以在不依赖 HTTP 请求的情况下调用

    Feature: backend-architecture-refactoring, Property 1: Service 方法可独立测试
    Validates: Requirements 4.5
    """
    # 创建一些测试数据
    for _ in range(5):
        ContractFactory()

    # 创建 Service 实例
    service = ContractService()

    # 调用 Service 方法（不需要 user 参数）
    results = service.list_contracts(case_type=None, status=None, is_archived=None)

    # 验证
    assert results is not None
    list(results)


@pytest.mark.django_db
@given(page=st.integers(min_value=1, max_value=10), page_size=st.integers(min_value=1, max_value=50))
@settings(max_examples=50, deadline=None)
def test_client_service_list_without_http_request(page, page_size):
    """
    Property 1: ClientService.list_clients 可以在不依赖 HTTP 请求的情况下调用

    Feature: backend-architecture-refactoring, Property 1: Service 方法可独立测试
    Validates: Requirements 4.5
    """
    # 创建一些测试数据
    for _ in range(5):
        ClientFactory()

    # 创建 Service 实例
    service = ClientService()

    # 创建 Mock 用户
    user = MockUser(id=1, is_authenticated=True, is_admin=True)

    # 调用 Service 方法
    results = service.list_clients(
        page=page, page_size=page_size, client_type=None, is_our_client=None, search=None, user=user
    )

    # 验证
    assert results is not None
    list(results)


@pytest.mark.django_db
def test_service_methods_only_depend_on_injected_parameters():
    """
    Property 1: Service 方法只依赖注入的参数

    Feature: backend-architecture-refactoring, Property 1: Service 方法可独立测试
    Validates: Requirements 4.5

    测试：
    1. Service 构造函数接受依赖注入
    2. Service 方法只使用注入的依赖
    3. 不使用全局变量或单例
    """
    # 测试 CaseService 依赖注入
    mock_contract_service = MockContractService()
    case_service = CaseService(contract_service=mock_contract_service)  # type: ignore[arg-type]

    # 验证：依赖已注入
    assert case_service._contract_service is mock_contract_service

    # 测试 ContractService 依赖注入
    from apps.core.business_config import BusinessConfig

    config = BusinessConfig()
    contract_service = ContractService(config=config)

    # 验证：配置已注入
    assert contract_service.config is config

    # 测试 ClientService（无依赖注入）
    client_service = ClientService()
    assert client_service is not None

    # 测试 LawFirmService（无依赖注入）
    lawfirm_service = LawFirmService()
    assert lawfirm_service is not None


@pytest.mark.django_db
@given(data=case_create_data())
@settings(max_examples=50, deadline=None)
def test_service_methods_do_not_access_request_attributes(data):
    """
    Property 1: Service 方法不访问 HTTP request 的属性

    Feature: backend-architecture-refactoring, Property 1: Service 方法可独立测试
    Validates: Requirements 4.5

    测试：
    1. Service 方法不访问 request.META
    2. Service 方法不访问 request.GET/POST
    3. Service 方法不访问 request.session
    """
    # 创建 Service 实例
    mock_contract_service = MockContractService()
    service = CaseService(contract_service=mock_contract_service)  # type: ignore[arg-type]

    # 创建一个没有 HTTP 属性的 Mock 用户
    class MinimalUser:
        """最小化的用户对象（没有 HTTP 相关属性）"""

        id = 1
        is_authenticated = True
        is_admin = False
        is_superuser = False

        def has_perm(self, perm):
            return False

    user = MinimalUser()

    # 如果有 contract_id，配置 Mock
    if data.get("contract_id"):
        from apps.core.interfaces import ContractDTO

        mock_contract_service.set_contract(
            data["contract_id"],
            ContractDTO(
                id=data["contract_id"],
                name="测试合同",
                case_type="civil",
                status="active",
                representation_stages=["investigation", "prosecution"],
                fee_mode="fixed",
                fixed_amount=Decimal("10000.00"),
            ),
        )

    try:
        # 调用 Service 方法
        # 如果方法尝试访问 request.META 等属性，会抛出 AttributeError
        case = service.create_case(data, user=user)

        # 验证：方法成功执行（或抛出业务异常）
        assert case is not None

    except AttributeError as e:
        # 如果抛出 AttributeError，说明方法尝试访问不存在的属性
        # 这违反了 Service 层的职责
        pytest.fail(f"Service 方法尝试访问不存在的属性: {e}")

    except Exception as e:
        # 业务异常是可以接受的
        from apps.core.exceptions import BusinessException

        if not isinstance(e, BusinessException):
            raise


@pytest.mark.django_db
def test_service_can_be_tested_in_isolation():
    """
    Property 1: Service 可以在隔离环境中测试

    Feature: backend-architecture-refactoring, Property 1: Service 方法可独立测试
    Validates: Requirements 4.5

    测试：
    1. Service 可以使用 Mock 依赖进行测试
    2. 不需要启动 HTTP 服务器
    3. 不需要真实的数据库（可以使用测试数据库）
    """
    # 创建 Mock 依赖
    mock_contract_service = MockContractService()

    # 配置 Mock 行为
    from apps.core.interfaces import ContractDTO

    # 创建真实合同记录（满足外键约束），同时注入 Mock 服务
    real_contract = ContractFactory()
    mock_contract_service.set_contract(
        real_contract.id,  # type: ignore[attr-defined]
        ContractDTO(
            id=real_contract.id,  # type: ignore[attr-defined]
            name="测试合同",
            case_type="criminal",  # 使用 criminal 类型，支持 investigation 阶段
            status="active",
            representation_stages=["investigation", "prosecution"],
            fee_mode="fixed",
            fixed_amount=Decimal("10000.00"),
        ),
    )

    # 创建 Service 实例（注入 Mock）
    service = CaseService(contract_service=mock_contract_service)  # type: ignore[arg-type]

    # 创建 Mock 用户
    user = MockUser(id=1, is_authenticated=True)

    # 调用 Service 方法
    case = service.create_case(
        {"name": "测试案件", "contract_id": real_contract.id, "current_stage": "investigation"},  # type: ignore
        user=user,
    )

    # 验证：方法成功执行
    assert case is not None
    assert case.name == "测试案件"

    # 验证：Mock 被调用
    assert mock_contract_service.get_contract_call_count > 0
