"""
测试 ContractDTO 和 IContractService 的更新

验证新增的 primary_lawyer_id 和 primary_lawyer_name 字段，
以及 get_contract_lawyers 方法
"""
import pytest
from apps.core.interfaces import ContractDTO
from apps.contracts.services import ContractServiceAdapter
from apps.contracts.services.contract.contract_service import ContractService
from tests.factories.contract_factories import ContractFactory, ContractAssignmentFactory
from tests.factories.organization_factories import LawyerFactory


@pytest.mark.django_db
class TestContractDTOUpdate:
    """测试 ContractDTO 的更新"""

    def test_contract_dto_has_primary_lawyer_fields(self):
        """测试 ContractDTO 包含 primary_lawyer_id 和 primary_lawyer_name 字段"""
        lawyer = LawyerFactory(real_name="张三")
        contract = ContractFactory()
        # 使用 ContractAssignment 创建主办律师
        ContractAssignmentFactory(contract=contract, lawyer=lawyer, is_primary=True)
        
        dto = ContractDTO.from_model(contract)
        
        # 验证新字段存在
        assert hasattr(dto, 'primary_lawyer_id')
        assert hasattr(dto, 'primary_lawyer_name')
        
        # 验证值正确
        assert dto.primary_lawyer_id == lawyer.id
        assert dto.primary_lawyer_name == "张三"

    def test_contract_dto_primary_lawyer_with_assignment(self):
        """测试 ContractDTO 使用 ContractAssignment 的主办律师"""
        from apps.contracts.models import ContractAssignment
        
        # 创建合同和律师
        primary_lawyer = LawyerFactory(real_name="主办律师")
        secondary_lawyer = LawyerFactory(real_name="协办律师")
        contract = ContractFactory()
        
        # 创建主办律师指派
        ContractAssignment.objects.create(
            contract=contract,
            lawyer=primary_lawyer,
            is_primary=True,
            order=0
        )
        # 创建协办律师指派
        ContractAssignment.objects.create(
            contract=contract,
            lawyer=secondary_lawyer,
            is_primary=False,
            order=1
        )
        
        dto = ContractDTO.from_model(contract)
        
        # 应该使用 ContractAssignment 的主办律师
        assert dto.primary_lawyer_id == primary_lawyer.id
        assert dto.primary_lawyer_name == "主办律师"

    def test_contract_dto_no_primary_lawyer(self):
        """测试 ContractDTO 无主办律师时的情况"""
        contract = ContractFactory()
        
        dto = ContractDTO.from_model(contract)
        
        # 无主办律师时应为 None
        assert dto.primary_lawyer_id is None
        assert dto.primary_lawyer_name is None


@pytest.mark.django_db
class TestContractServiceAdapterUpdate:
    """测试 ContractServiceAdapter 的更新"""

    def setup_method(self):
        """设置测试"""
        self.adapter = ContractServiceAdapter(contract_service=ContractService())

    def test_get_contract_assigned_lawyer_id_uses_primary_lawyer(self):
        """测试 get_contract_assigned_lawyer_id 使用 primary_lawyer"""
        from apps.contracts.models import ContractAssignment
        
        # 创建合同和律师
        primary_lawyer = LawyerFactory()
        secondary_lawyer = LawyerFactory()
        contract = ContractFactory()
        
        # 创建主办律师指派
        ContractAssignment.objects.create(
            contract=contract,
            lawyer=primary_lawyer,
            is_primary=True,
            order=0
        )
        # 创建协办律师指派
        ContractAssignment.objects.create(
            contract=contract,
            lawyer=secondary_lawyer,
            is_primary=False,
            order=1
        )
        
        # 应该返回主办律师的 ID
        lawyer_id = self.adapter.get_contract_assigned_lawyer_id(contract.id)
        assert lawyer_id == primary_lawyer.id

    def test_get_contract_lawyers(self):
        """测试 get_contract_lawyers 方法"""
        from apps.contracts.models import ContractAssignment
        from apps.core.interfaces import LawyerDTO
        
        # 创建合同和律师
        lawyer1 = LawyerFactory(real_name="主办律师")
        lawyer2 = LawyerFactory(real_name="协办律师1")
        lawyer3 = LawyerFactory(real_name="协办律师2")
        contract = ContractFactory()
        
        # 创建律师指派
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
        ContractAssignment.objects.create(
            contract=contract,
            lawyer=lawyer3,
            is_primary=False,
            order=2
        )
        
        # 获取所有律师
        lawyers = self.adapter.get_contract_lawyers(contract.id)
        
        # 验证返回类型
        assert isinstance(lawyers, list)
        assert len(lawyers) == 3
        assert all(isinstance(lawyer, LawyerDTO) for lawyer in lawyers)
        
        # 验证排序（主办律师在前）
        assert lawyers[0].id == lawyer1.id
        assert lawyers[0].real_name == "主办律师"
        assert lawyers[1].id == lawyer2.id
        assert lawyers[2].id == lawyer3.id

    def test_get_contract_lawyers_empty(self):
        """测试 get_contract_lawyers 无律师指派时"""
        contract = ContractFactory()
        
        lawyers = self.adapter.get_contract_lawyers(contract.id)
        
        # 应该返回空列表
        assert isinstance(lawyers, list)
        assert len(lawyers) == 0

    def test_get_contract_lawyers_not_found(self):
        """测试 get_contract_lawyers 合同不存在时"""
        from apps.core.exceptions import NotFoundError
        
        with pytest.raises(NotFoundError):
            self.adapter.get_contract_lawyers(999)
