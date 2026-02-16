"""
常用服务的 Mock 实现
"""
from typing import Optional, List
from .base import MockService
from apps.core.interfaces import ContractDTO, CaseDTO


class MockContractService(MockService):
    """Mock 合同服务"""
    
    def __init__(self):
        super().__init__()
        self._contracts = {}  # 存储设置的合同数据
        self.get_contract_call_count = 0  # 记录调用次数
    
    def set_contract(self, contract_id: int, contract_dto: ContractDTO):
        """设置 Mock 合同数据"""
        self._contracts[contract_id] = contract_dto
    
    def get_contract(self, contract_id: int) -> Optional[ContractDTO]:
        """获取合同"""
        self.get_contract_call_count += 1
        # 优先返回设置的数据
        if contract_id in self._contracts:
            return self._contracts[contract_id]
        return self._get_mock_return('get_contract', {'contract_id': contract_id})
    
    def get_contract_stages(self, contract_id: int) -> List[str]:
        """获取合同的代理阶段"""
        # 如果有设置的合同数据，返回其阶段
        if contract_id in self._contracts:
            return self._contracts[contract_id].representation_stages or []
        return self._get_mock_return('get_contract_stages', {'contract_id': contract_id}) or []
    
    def validate_contract_active(self, contract_id: int) -> bool:
        """验证合同是否有效"""
        # 如果有设置的合同数据，检查其状态
        if contract_id in self._contracts:
            return self._contracts[contract_id].status == "active"
        result = self._get_mock_return('validate_contract_active', {'contract_id': contract_id})
        return result if result is not None else True


class MockCaseService(MockService):
    """Mock 案件服务"""
    
    def get_case(self, case_id: int) -> Optional[CaseDTO]:
        """获取案件"""
        return self._get_mock_return('get_case', {'case_id': case_id})
    
    def check_case_access(self, user, case_id: int) -> bool:
        """检查案件访问权限"""
        result = self._get_mock_return('check_case_access', {
            'user': user,
            'case_id': case_id
        })
        return result if result is not None else True


class MockPermissionService(MockService):
    """Mock 权限服务"""
    
    def can_create_resource(self, user, resource_type: str) -> bool:
        """检查是否可以创建资源"""
        result = self._get_mock_return('can_create_resource', {
            'user': user,
            'resource_type': resource_type
        })
        return result if result is not None else True
    
    def can_access_resource(self, user, resource) -> bool:
        """检查是否可以访问资源"""
        result = self._get_mock_return('can_access_resource', {
            'user': user,
            'resource': resource
        })
        return result if result is not None else True
    
    def can_modify_resource(self, user, resource) -> bool:
        """检查是否可以修改资源"""
        result = self._get_mock_return('can_modify_resource', {
            'user': user,
            'resource': resource
        })
        return result if result is not None else True
    
    def can_delete_resource(self, user, resource) -> bool:
        """检查是否可以删除资源"""
        result = self._get_mock_return('can_delete_resource', {
            'user': user,
            'resource': resource
        })
        return result if result is not None else True


class MockEmailService(MockService):
    """Mock 邮件服务"""
    
    def send_email(self, to: str, subject: str, body: str) -> bool:
        """发送邮件"""
        result = self._get_mock_return('send_email', {
            'to': to,
            'subject': subject,
            'body': body
        })
        return result if result is not None else True
    
    def send_bulk_email(self, recipients: List[str], subject: str, body: str) -> bool:
        """批量发送邮件"""
        result = self._get_mock_return('send_bulk_email', {
            'recipients': recipients,
            'subject': subject,
            'body': body
        })
        return result if result is not None else True
