"""
律所 API
只负责请求/响应处理，业务逻辑在 Service 层
"""
from typing import List
from ninja import Router

from ..schemas import LawFirmOut, LawFirmIn, LawFirmUpdateIn

router = Router()


def _get_lawfirm_service():
    """工厂函数：创建 LawFirmService 实例"""
    from ..services import LawFirmService
    return LawFirmService()


@router.get("/lawfirms", response=List[LawFirmOut])
def list_lawfirms(request):
    """列表查询律所"""
    service = _get_lawfirm_service()
    user = getattr(request, 'auth', None) or getattr(request, 'user', None)
    lawfirms = service.list_lawfirms(user=user)
    return list(lawfirms)


@router.get("/lawfirms/{law_firm_id}", response=LawFirmOut)
def get_lawfirm(request, law_firm_id: int):
    """获取律所详情"""
    service = _get_lawfirm_service()
    user = getattr(request, 'auth', None) or getattr(request, 'user', None)
    lawfirm = service.get_lawfirm(law_firm_id, user)
    return lawfirm


@router.post("/lawfirms", response=LawFirmOut)
def create_lawfirm(request, payload: LawFirmIn):
    """创建律所"""
    service = _get_lawfirm_service()
    user = getattr(request, 'auth', None) or getattr(request, 'user', None)
    lawfirm = service.create_lawfirm(data=payload, user=user)
    return lawfirm


@router.put("/lawfirms/{law_firm_id}", response=LawFirmOut)
def update_lawfirm(request, law_firm_id: int, payload: LawFirmUpdateIn):
    """更新律所"""
    service = _get_lawfirm_service()
    user = getattr(request, 'auth', None) or getattr(request, 'user', None)
    lawfirm = service.update_lawfirm(
        lawfirm_id=law_firm_id,
        data=payload,
        user=user
    )
    return lawfirm


@router.delete("/lawfirms/{law_firm_id}")
def delete_lawfirm(request, law_firm_id: int):
    """删除律所"""
    service = _get_lawfirm_service()
    user = getattr(request, 'auth', None) or getattr(request, 'user', None)
    service.delete_lawfirm(law_firm_id, user)
    return {"success": True}
