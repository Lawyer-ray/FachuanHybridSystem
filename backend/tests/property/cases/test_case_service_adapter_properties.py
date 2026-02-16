"""
CaseServiceAdapter Property-Based Tests
测试案件服务适配器的接口实现

Feature: service-layer-decoupling, Property 6: 合同服务案件创建通过接口
Validates: Requirements 1.1
"""

from decimal import Decimal

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from apps.cases.models import Case, CaseAssignment, CaseParty
from apps.cases.services import CaseServiceAdapter
from apps.core.interfaces import CaseDTO


@pytest.mark.django_db
class TestCaseServiceAdapterCreateProperties:
    """
    CaseServiceAdapter 创建方法属性测试

    **Feature: service-layer-decoupling, Property 6: 合同服务案件创建通过接口**
    **Validates: Requirements 1.1**
    """

    @given(
        case_name=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N", "P", "S")), min_size=1, max_size=50
        ).filter(lambda x: x.strip()),
    )
    @settings(max_examples=100)
    def test_create_case_returns_dto(self, case_name):
        """
        Property 6: 案件创建通过接口返回 DTO

        **Feature: service-layer-decoupling, Property 6: 合同服务案件创建通过接口**
        **Validates: Requirements 1.1**

        属性：对于任意有效的案件数据，通过 CaseServiceAdapter.create_case()
        创建的案件应该返回 CaseDTO 类型，且 DTO 的 name 字段与输入一致。
        """
        adapter = CaseServiceAdapter()

        data = {
            "name": case_name,
            "is_archived": False,
        }

        result = adapter.create_case(data)

        # 验证返回类型是 CaseDTO
        assert isinstance(result, CaseDTO), f"Expected CaseDTO, got {type(result)}"

        # 验证 DTO 的 name 字段与输入一致
        assert result.name == case_name

        # 验证 DTO 有有效的 id
        assert result.id is not None
        assert result.id > 0

        # 验证数据库中确实创建了案件
        assert Case.objects.filter(id=result.id).exists()

    @given(
        case_name=st.text(alphabet=st.characters(whitelist_categories=("L", "N")), min_size=1, max_size=30).filter(
            lambda x: x.strip()
        ),
    )
    @settings(max_examples=100)
    def test_create_case_dto_fields_match_database(self, case_name):
        """
        Property: 创建案件后 DTO 字段与数据库一致

        属性：通过接口创建的案件，返回的 DTO 字段应该与数据库中的记录一致。
        """
        adapter = CaseServiceAdapter()

        data = {
            "name": case_name,
            "is_archived": False,
            "cause_of_action": "合同纠纷",
        }

        result = adapter.create_case(data)

        # 从数据库获取案件
        db_case = Case.objects.get(id=result.id)

        # 验证 DTO 字段与数据库一致
        assert result.id == db_case.id
        assert result.name == db_case.name
        assert result.is_archived == db_case.is_archived


@pytest.mark.django_db
class TestCaseServiceAdapterAssignmentProperties:
    """CaseServiceAdapter 案件指派属性测试"""

    @given(
        case_name=st.text(alphabet=st.characters(whitelist_categories=("L", "N")), min_size=1, max_size=30).filter(
            lambda x: x.strip()
        ),
    )
    @settings(max_examples=50, deadline=None)
    def test_create_case_assignment_success(self, case_name):
        """
        Property: 案件指派创建成功

        属性：对于存在的案件和律师，create_case_assignment 应该返回 True
        并在数据库中创建指派记录。
        """
        from tests.factories import LawyerFactory

        adapter = CaseServiceAdapter()

        # 创建案件
        case = Case.objects.create(name=case_name, is_archived=False)

        # 创建律师
        lawyer = LawyerFactory()

        # 创建指派
        result = adapter.create_case_assignment(case.id, lawyer.id)

        # 验证返回 True
        assert result is True

        # 验证数据库中存在指派记录
        assert CaseAssignment.objects.filter(case_id=case.id, lawyer_id=lawyer.id).exists()

    @given(
        case_name=st.text(alphabet=st.characters(whitelist_categories=("L", "N")), min_size=1, max_size=30).filter(
            lambda x: x.strip()
        ),
    )
    @settings(max_examples=50, deadline=None)
    def test_create_case_assignment_idempotent(self, case_name):
        """
        Property: 案件指派创建幂等性

        属性：对于相同的案件和律师，多次调用 create_case_assignment
        应该都返回 True，且数据库中只有一条记录。
        """
        from tests.factories import LawyerFactory

        adapter = CaseServiceAdapter()

        # 创建案件
        case = Case.objects.create(name=case_name, is_archived=False)

        # 创建律师
        lawyer = LawyerFactory()

        # 多次创建指派
        result1 = adapter.create_case_assignment(case.id, lawyer.id)
        result2 = adapter.create_case_assignment(case.id, lawyer.id)

        # 验证都返回 True
        assert result1 is True
        assert result2 is True

        # 验证数据库中只有一条记录
        count = CaseAssignment.objects.filter(case_id=case.id, lawyer_id=lawyer.id).count()
        assert count == 1

    def test_create_case_assignment_nonexistent_case(self):
        """
        Property: 不存在的案件指派返回 False

        属性：对于不存在的案件 ID，create_case_assignment 应该返回 False。
        """
        adapter = CaseServiceAdapter()

        # 使用不存在的案件 ID
        result = adapter.create_case_assignment(999999, 1)

        # 验证返回 False
        assert result is False


@pytest.mark.django_db
class TestCaseServiceAdapterPartyProperties:
    """CaseServiceAdapter 案件当事人属性测试"""

    @given(
        case_name=st.text(alphabet=st.characters(whitelist_categories=("L", "N")), min_size=1, max_size=30).filter(
            lambda x: x.strip()
        ),
        legal_status=st.sampled_from([None, "plaintiff", "defendant", "third"]),
    )
    @settings(max_examples=50)
    def test_create_case_party_success(self, case_name, legal_status):
        """
        Property: 案件当事人创建成功

        属性：对于存在的案件和客户，create_case_party 应该返回 True
        并在数据库中创建当事人记录。
        """
        from tests.factories import ClientFactory

        adapter = CaseServiceAdapter()

        # 创建案件
        case = Case.objects.create(name=case_name, is_archived=False)

        # 创建客户
        client = ClientFactory()

        # 创建当事人
        result = adapter.create_case_party(case.id, client.id, legal_status)

        # 验证返回 True
        assert result is True

        # 验证数据库中存在当事人记录
        party = CaseParty.objects.filter(case_id=case.id, client_id=client.id).first()
        assert party is not None
        assert party.legal_status == legal_status

    @given(
        case_name=st.text(alphabet=st.characters(whitelist_categories=("L", "N")), min_size=1, max_size=30).filter(
            lambda x: x.strip()
        ),
    )
    @settings(max_examples=50)
    def test_create_case_party_idempotent(self, case_name):
        """
        Property: 案件当事人创建幂等性

        属性：对于相同的案件和客户，多次调用 create_case_party
        应该都返回 True，且数据库中只有一条记录。
        """
        from tests.factories import ClientFactory

        adapter = CaseServiceAdapter()

        # 创建案件
        case = Case.objects.create(name=case_name, is_archived=False)

        # 创建客户
        client = ClientFactory()

        # 多次创建当事人
        result1 = adapter.create_case_party(case.id, client.id, "plaintiff")
        result2 = adapter.create_case_party(case.id, client.id, "defendant")

        # 验证都返回 True
        assert result1 is True
        assert result2 is True

        # 验证数据库中只有一条记录
        count = CaseParty.objects.filter(case_id=case.id, client_id=client.id).count()
        assert count == 1

    def test_create_case_party_nonexistent_case(self):
        """
        Property: 不存在的案件当事人返回 False

        属性：对于不存在的案件 ID，create_case_party 应该返回 False。
        """
        adapter = CaseServiceAdapter()

        # 使用不存在的案件 ID
        result = adapter.create_case_party(999999, 1, "plaintiff")

        # 验证返回 False
        assert result is False
