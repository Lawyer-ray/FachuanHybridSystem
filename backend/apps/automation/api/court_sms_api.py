"""
法院短信处理 API
"""
from ninja import Router, Form
from ninja.pagination import paginate, PageNumberPagination
from typing import Optional, List
from datetime import datetime

from ..schemas import (
    CourtSMSSubmitIn, CourtSMSSubmitOut,
    CourtSMSDetailOut, CourtSMSListOut,
    CourtSMSAssignCaseIn, CourtSMSAssignCaseOut
)

router = Router(tags=["法院短信处理"])


def _get_court_sms_service():
    """
    工厂函数：创建法院短信服务实例
    
    通过ServiceLocator获取法院短信服务，确保依赖解耦
    
    Returns:
        CourtSMSService 实例
    """
    from apps.core.interfaces import ServiceLocator
    return ServiceLocator.get_court_sms_service()


# ============================================================================
# 短信提交接口
# ============================================================================

@router.post("/court-sms", response=CourtSMSSubmitOut)
def submit_sms(request, payload: CourtSMSSubmitIn):
    """
    提交法院短信
    
    支持短信转发器直接调用，创建记录并触发异步处理
    """
    service = _get_court_sms_service()
    
    sms = service.submit_sms(
        content=payload.content,
        received_at=payload.received_at,
        sender=payload.sender
    )
    
    return CourtSMSSubmitOut(
        success=True,
        data={
            "id": sms.id,
            "status": sms.status,
            "created_at": sms.created_at
        }
    )


@router.post("/court-sms/form", response=CourtSMSSubmitOut)
def submit_sms_form(
    request,
    content: str = Form(...),
    received_at: Optional[datetime] = Form(None),
    sender: Optional[str] = Form(None)
):
    """
    提交法院短信（表单格式）
    
    支持 form-data 格式提交，便于简单的 HTTP 客户端调用
    """
    service = _get_court_sms_service()
    
    sms = service.submit_sms(
        content=content,
        received_at=received_at,
        sender=sender
    )
    
    return CourtSMSSubmitOut(
        success=True,
        data={
            "id": sms.id,
            "status": sms.status,
            "created_at": sms.created_at
        }
    )


# ============================================================================
# 状态查询接口
# ============================================================================

@router.get("/court-sms/{sms_id}", response=CourtSMSDetailOut)
def get_sms_detail(request, sms_id: int):
    """
    查询短信处理详情
    
    返回短信的完整处理状态和关联信息
    """
    service = _get_court_sms_service()
    
    sms = service.get_sms_detail(sms_id)
    
    return CourtSMSDetailOut.from_model(sms)


@router.get("/court-sms", response=List[CourtSMSListOut])
@paginate(PageNumberPagination, page_size=20)
def list_sms(
    request,
    status: Optional[str] = None,
    sms_type: Optional[str] = None,
    has_case: Optional[bool] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None
):
    """
    查询短信列表
    
    支持按状态、类型、是否关联案件、日期范围筛选
    """
    service = _get_court_sms_service()
    
    sms_list = service.list_sms(
        status=status,
        sms_type=sms_type,
        has_case=has_case,
        date_from=date_from,
        date_to=date_to
    )
    
    return [CourtSMSListOut.from_model(sms) for sms in sms_list]


# ============================================================================
# 手动指定案件接口
# ============================================================================

@router.post("/court-sms/{sms_id}/assign-case", response=CourtSMSAssignCaseOut)
def assign_case(request, sms_id: int, payload: CourtSMSAssignCaseIn):
    """
    手动指定案件
    
    当自动匹配失败时，管理员可以手动指定案件
    """
    service = _get_court_sms_service()
    
    sms = service.assign_case(sms_id, payload.case_id)
    
    return CourtSMSAssignCaseOut(
        success=True,
        data={
            "id": sms.id,
            "status": sms.status,
            "case": {
                "id": sms.case.id,
                "name": sms.case.name
            } if sms.case else None
        }
    )


# ============================================================================
# 重新处理接口
# ============================================================================

@router.post("/court-sms/{sms_id}/retry", response=CourtSMSSubmitOut)
def retry_processing(request, sms_id: int):
    """
    重新处理短信
    
    重置状态并重新执行完整处理流程
    """
    service = _get_court_sms_service()
    
    sms = service.retry_processing(sms_id)
    
    return CourtSMSSubmitOut(
        success=True,
        data={
            "id": sms.id,
            "status": sms.status,
            "created_at": sms.created_at
        }
    )