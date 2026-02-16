"""
合同服务 Property-Based Testing
"""

import pytest
from django.db import connection
from django.test.utils import override_settings
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.contracts.models import ContractAssignment
from apps.contracts.services import ContractService
from tests.factories import ContractFactory, ContractPaymentFactory, LawyerFactory


@pytest.mark.django_db
class TestContractServiceProperties:
    """合同服务属性测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.service = ContractService()

    @given(st.integers(min_value=1, max_value=20))
    @settings(max_examples=100, deadline=None)
    @override_settings(DEBUG=True)
    def test_list_contracts_no_n_plus_1(self, contract_count):
        """
        Property 6: 多对多关系预加载

        Feature: backend-architecture-refactoring, Property 6: 多对多关系预加载
        Validates: Requirements 6.3

        测试 list_contracts 方法不会产生 N+1 查询
        访问 cases、payments 等关系时不会额外查询
        """
        # 重置查询计数
        from django.db import reset_queries

        reset_queries()

        # 创建测试数据：每个合同有多个收款记录
        contracts = []
        for i in range(contract_count):
            contract = ContractFactory()
            # 为每个合同创建主办律师
            lawyer = LawyerFactory()
            ContractAssignment.objects.create(contract=contract, lawyer=lawyer, is_primary=True, order=0)
            # 为每个合同创建 2-3 个收款记录
            ContractPaymentFactory.create_batch(2, contract=contract)
            contracts.append(contract)

        # 重置查询计数
        reset_queries()

        # 执行列表查询
        queryset = self.service.list_contracts()
        contract_list = list(queryset)

        # 访问关联对象
        for contract in contract_list:
            # 访问律师指派关系（应该已经预加载）
            assignments = list(contract.assignments.all())
            if assignments:
                _ = assignments[0].lawyer.real_name

            # 访问反向外键关系（应该已经预加载）
            _ = list(contract.payments.all())
            _ = list(contract.cases.all())

        # 获取查询次数
        query_count = len(connection.queries)

        # 验证：应该只有少量查询（不超过 10 次）
        # 1 次主查询 + select_related 的 JOIN + prefetch_related 的额外查询
        assert query_count <= 10, (
            f"查询次数过多: {query_count} 次，可能存在 N+1 问题。" f"查询详情: {[q['sql'] for q in connection.queries]}"
        )

    @given(st.integers(min_value=1, max_value=10))
    @settings(max_examples=100, deadline=None)
    @override_settings(DEBUG=True)
    def test_get_contract_no_n_plus_1(self, payment_count):
        """
        Property 6: 多对多关系预加载

        Feature: backend-architecture-refactoring, Property 6: 多对多关系预加载
        Validates: Requirements 6.3

        测试 get_contract 方法不会产生 N+1 查询
        """
        # 创建测试数据
        contract = ContractFactory()
        lawyer = LawyerFactory()
        ContractAssignment.objects.create(contract=contract, lawyer=lawyer, is_primary=True, order=0)
        ContractPaymentFactory.create_batch(payment_count, contract=contract)

        # 重置查询计数
        from django.db import reset_queries

        reset_queries()

        # 执行查询（使用 perm_open_access=True 绕过权限检查）
        result = self.service.get_contract(contract.id, perm_open_access=True)

        # 访问关联对象
        assignments = list(result.assignments.all())
        if assignments:
            _ = assignments[0].lawyer.real_name
        _ = list(result.payments.all())
        _ = list(result.cases.all())

        # 获取查询次数
        query_count = len(connection.queries)

        # 验证：应该只有少量查询
        assert query_count <= 10, f"查询次数过多: {query_count} 次，可能存在 N+1 问题"

    @given(st.integers(min_value=1, max_value=10), st.integers(min_value=1, max_value=5))
    @settings(max_examples=50, deadline=None)
    @override_settings(DEBUG=True)
    def test_get_finance_summary_efficient(self, contract_count, payment_per_contract):
        """
        Property 6: 多对多关系预加载

        Feature: backend-architecture-refactoring, Property 6: 多对多关系预加载
        Validates: Requirements 6.3

        测试 get_finance_summary 方法查询效率
        """
        # 创建测试数据
        contracts = []
        for i in range(contract_count):
            contract = ContractFactory()
            ContractPaymentFactory.create_batch(payment_per_contract, contract=contract)
            contracts.append(contract)

        # 重置查询计数
        from django.db import reset_queries

        reset_queries()

        # 对每个合同获取财务汇总
        for contract in contracts:
            summary = self.service.get_finance_summary(contract.id)
            assert summary["contract_id"] == contract.id
            assert "total_received" in summary
            assert "total_invoiced" in summary

        # 获取查询次数
        query_count = len(connection.queries)

        # 验证：查询次数应该是线性的，不应该是 O(n²)
        # 每个合同大约 5-6 次查询（获取合同 + 获取收款记录 + 聚合查询）
        max_expected_queries = contract_count * 6 + 2
        assert (
            query_count <= max_expected_queries
        ), f"查询次数过多: {query_count} 次，预期不超过 {max_expected_queries} 次"
