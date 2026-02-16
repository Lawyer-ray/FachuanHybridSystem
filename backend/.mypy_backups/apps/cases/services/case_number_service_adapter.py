"""
案号服务适配器

实现 ICaseNumberService 接口，供跨模块调用
"""
from typing import Optional, List, Any

from apps.core.interfaces import ICaseNumberService


class CaseNumberServiceAdapter(ICaseNumberService):
    """
    案号服务适配器
    
    实现跨模块接口，委托给 CaseNumberService 执行
    """
    
    def __init__(self, case_number_service: Optional[Any] = None):
        self._case_number_service = case_number_service
    
    @property
    def case_number_service(self):
        """延迟加载 CaseNumberService"""
        if self._case_number_service is None:
            from .case_number_service import CaseNumberService
            self._case_number_service = CaseNumberService()
        return self._case_number_service
    
    def list_numbers_internal(self, case_id: int) -> List[Any]:
        """内部方法：获取案件的所有案号"""
        return list(self.case_number_service.list_numbers(case_id=case_id))
    
    def create_number_internal(
        self,
        case_id: int,
        number: str,
        remarks: Optional[str] = None
    ) -> Any:
        """内部方法：创建案号"""
        return self.case_number_service.create_number(
            case_id=case_id,
            number=number,
            remarks=remarks
        )
    
    def normalize_case_number(self, number: str) -> str:
        """规范化案号"""
        return self.case_number_service.normalize_case_number(number)
