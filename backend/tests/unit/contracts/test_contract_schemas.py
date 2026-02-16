"""
合同 Schema 单元测试
"""
import pytest
from pydantic import ValidationError

from apps.contracts.schemas import ContractIn, ContractOut, ContractAssignmentOut
from apps.contracts.models import Contract, ContractAssignment
from tests.factories import ContractFactory, LawyerFactory


@pytest.mark.django_db
class TestContractInSchema:
    """测试 ContractIn Schema"""

    def test_lawyer_ids_required(self):
        """测试 lawyer_ids 必填"""
        with pytest.raises(ValidationError) as exc_info:
            ContractIn(
                name="测试合同",
                case_type="civil",
                status="active",
                lawyer_ids=[]  # 空列表应该失败
            )
        
        assert "至少需要指派一个律师" in str(exc_info.value)

    def test_lawyer_ids_valid(self):
        """测试有效的 lawyer_ids"""
        contract_in = ContractIn(
            name="测试合同",
            case_type="civil",
            status="active",
            lawyer_ids=[1, 2, 3],
            fee_mode="FIXED",
            fixed_amount=10000.0
        )
        
        assert contract_in.lawyer_ids == [1, 2, 3]
        assert contract_in.name == "测试合同"

    def test_no_assigned_lawyer_id_field(self):
        """测试 assigned_lawyer_id 字段已移除"""
        # 尝试使用旧字段应该失败
        with pytest.raises(ValidationError):
            ContractIn(
                name="测试合同",
                case_type="civil",
                status="active",
                assigned_lawyer_id=1,  # 旧字段
                fee_mode="FIXED",
                fixed_amount=10000.0
            )


@pytest.mark.django_db
class TestContractAssignmentOutSchema:
    """测试 ContractAssignmentOut Schema"""

    def test_from_assignment(self):
        """测试从 ContractAssignment 创建 Schema"""
        lawyer = LawyerFactory(real_name="张律师")
        contract = ContractFactory()
        assignment = ContractAssignment.objects.create(
            contract=contract,
            lawyer=lawyer,
            is_primary=True,
            order=0
        )

        schema = ContractAssignmentOut.from_assignment(assignment)

        assert schema.id == assignment.id
        assert schema.lawyer_id == lawyer.id
        assert schema.lawyer_name == "张律师"
        assert schema.is_primary is True
        assert schema.order == 0

    def test_from_assignment_no_real_name(self):
        """测试律师没有真实姓名时使用用户名"""
        lawyer = LawyerFactory(real_name="", username="lawyer1")
        contract = ContractFactory()
        assignment = ContractAssignment.objects.create(
            contract=contract,
            lawyer=lawyer,
            is_primary=False,
            order=1
        )

        schema = ContractAssignmentOut.from_assignment(assignment)

        assert schema.lawyer_name == "lawyer1"


@pytest.mark.django_db
class TestContractOutSchema:
    """测试 ContractOut Schema"""

    def test_resolve_assignments(self):
        """测试解析 assignments 字段"""
        lawyer1 = LawyerFactory(real_name="主办律师")
        lawyer2 = LawyerFactory(real_name="协办律师")
        contract = ContractFactory()
        
        # 创建指派
        ContractAssignment.objects.create(
            contract=contract,
            lawyer=lawyer1,
            is_primary=True,
            order=0
        )
        ContractAssignment.objects.create(
            contract=contract,
            lawyer=lawyer2,
            is_primary=False,
            order=1
        )

        # 解析 assignments
        assignments = ContractOut.resolve_assignments(contract)

        assert len(assignments) == 2
        assert assignments[0].is_primary is True
        assert assignments[0].lawyer_name == "主办律师"
        assert assignments[1].is_primary is False
        assert assignments[1].lawyer_name == "协办律师"

    def test_resolve_primary_lawyer(self):
        """测试解析 primary_lawyer 字段"""
        lawyer = LawyerFactory(real_name="主办律师")
        contract = ContractFactory()
        
        # 创建主办律师指派
        ContractAssignment.objects.create(
            contract=contract,
            lawyer=lawyer,
            is_primary=True,
            order=0
        )

        # 解析 primary_lawyer
        primary_lawyer = ContractOut.resolve_primary_lawyer(contract)

        assert primary_lawyer is not None
        assert primary_lawyer.id == lawyer.id

    def test_resolve_primary_lawyer_no_assignment(self):
        """测试无主办律师指派时返回 None"""
        contract = ContractFactory()

        # 没有 ContractAssignment，应该返回 None
        primary_lawyer = ContractOut.resolve_primary_lawyer(contract)

        assert primary_lawyer is None
