"""
测试框架设置验证

验证 pytest、factory-boy、hypothesis 配置是否正确
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tests.factories import CaseFactory, LawyerFactory
from tests.mocks import MockContractService
from tests.strategies import chinese_text, phone_number


@pytest.mark.django_db
class TestFactorySetup:
    """测试 Factory-Boy 设置"""

    def test_lawyer_factory(self):
        """测试律师工厂"""
        lawyer = LawyerFactory()

        assert lawyer.id is not None  # type: ignore[attr-defined]
        assert lawyer.username
        assert lawyer.law_firm is not None

    def test_case_factory(self):
        """测试案件工厂"""
        case = CaseFactory()

        assert case.id is not None  # type: ignore[attr-defined]
        assert case.name
        assert case.contract is not None


class TestHypothesisSetup:
    """测试 Hypothesis 设置"""

    @given(chinese_text(min_size=2, max_size=10))
    def test_chinese_text_strategy(self, text):
        """测试中文文本策略"""
        assert isinstance(text, str)
        assert 2 <= len(text) <= 10

    @given(phone_number())
    def test_phone_number_strategy(self, phone):
        """测试手机号码策略"""
        assert isinstance(phone, str)
        assert len(phone) == 11
        assert phone[0] == "1"


class TestMockSetup:
    """测试 Mock 设置"""

    def test_mock_contract_service(self):
        """测试 Mock 合同服务"""
        from apps.core.interfaces import ContractDTO

        mock_service = MockContractService()

        # 设置返回值
        expected_contract = ContractDTO(
            id=1,
            name="测试合同",
            case_type="civil",
            status="active",
            representation_stages=["first_trial"],
            fixed_amount=None,
        )
        mock_service.set_return("get_contract", expected_contract)

        # 调用方法
        result = mock_service.get_contract(1)

        # 验证结果
        assert result == expected_contract
        assert mock_service.get_call_count("get_contract") == 1
        assert mock_service.get_call_args("get_contract", 0) == {"contract_id": 1}


@pytest.mark.django_db
def test_query_counter_fixture(query_counter):
    """测试查询计数器 fixture"""
    from apps.cases.models import Case

    # 创建测试数据
    CaseFactory.create_batch(5)

    # 使用查询计数器（需要调用函数）
    with query_counter() as counter:
        cases = Case.objects.all()
        list(cases)

    # 验证查询次数
    assert counter.count == 1


@pytest.mark.django_db
def test_assert_num_queries_fixture(assert_num_queries):
    """测试断言查询次数 fixture"""
    from apps.cases.models import Case

    # 创建测试数据
    CaseFactory.create_batch(5)

    # 断言查询次数
    with assert_num_queries(1):
        cases = Case.objects.all()
        list(cases)
