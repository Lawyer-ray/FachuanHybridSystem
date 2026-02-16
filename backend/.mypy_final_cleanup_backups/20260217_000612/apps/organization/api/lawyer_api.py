"""
律师 API
只负责请求/响应处理，业务逻辑在 Service 层
"""
from typing import List
from ninja import Router, File
from ninja.files import UploadedFile

from ..schemas import LawyerOut, LawyerCreateIn, LawyerUpdateIn

router = Router()


def _get_lawyer_service():
    """工厂函数：创建 LawyerService 实例"""
    from ..services import LawyerService
    return LawyerService()


@router.get("/lawyers", response=List[LawyerOut])
def list_lawyers(request):
    """列表查询律师"""
    service = _get_lawyer_service()
    user = getattr(request, 'auth', None) or getattr(request, 'user', None)
    lawyers = service.list_lawyers(user=user)
    return list(lawyers)


@router.get("/lawyers/{lawyer_id}", response=LawyerOut)
def get_lawyer(request, lawyer_id: int):
    """获取律师详情"""
    service = _get_lawyer_service()
    user = getattr(request, 'auth', None) or getattr(request, 'user', None)
    lawyer = service.get_lawyer(lawyer_id, user)
    return lawyer


@router.post("/lawyers", response=LawyerOut)
def create_lawyer(
    request,
    payload: LawyerCreateIn,
    license_pdf: UploadedFile | None = File(None)
):
    """创建律师"""
    service = _get_lawyer_service()
    user = getattr(request, 'auth', None) or getattr(request, 'user', None)
    lawyer = service.create_lawyer(
        data=payload,
        user=user,
        license_pdf=license_pdf
    )
    return lawyer


@router.put("/lawyers/{lawyer_id}", response=LawyerOut)
def update_lawyer(
    request,
    lawyer_id: int,
    payload: LawyerUpdateIn,
    license_pdf: UploadedFile | None = File(None)
):
    """更新律师"""
    service = _get_lawyer_service()
    user = getattr(request, 'auth', None) or getattr(request, 'user', None)
    lawyer = service.update_lawyer(
        lawyer_id=lawyer_id,
        data=payload,
        user=user,
        license_pdf=license_pdf
    )
    return lawyer


@router.delete("/lawyers/{lawyer_id}")
def delete_lawyer(request, lawyer_id: int):
    """删除律师"""
    service = _get_lawyer_service()
    user = getattr(request, 'auth', None) or getattr(request, 'user', None)
    service.delete_lawyer(lawyer_id, user)
    return {"success": True}
