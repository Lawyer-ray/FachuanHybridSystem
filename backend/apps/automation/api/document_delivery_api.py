"""
文书送达自动下载 API
"""
from ninja import Router
from ninja.pagination import paginate, PageNumberPagination
from typing import Optional, List
from datetime import datetime, timedelta
from django.utils import timezone

from ..schemas import (
    DocumentQueryResult as DocumentQueryResultSchema,
    DocumentDeliveryRecord as DocumentDeliveryRecordSchema
)
from pydantic import BaseModel, Field

router = Router(tags=["文书送达自动下载"])


def _get_document_delivery_service():
    """
    工厂函数：创建文书送达服务实例
    
    通过ServiceLocator获取文书送达服务，确保依赖解耦
    
    Returns:
        DocumentDeliveryService 实例
    """
    from ..services.document_delivery.document_delivery_service import DocumentDeliveryService
    return DocumentDeliveryService()


def _get_document_delivery_schedule_service():
    """
    工厂函数：创建文书送达定时任务服务实例
    
    通过ServiceLocator获取定时任务服务，确保依赖解耦
    
    Returns:
        DocumentDeliveryScheduleService 实例
    """
    from ..services.document_delivery.document_delivery_schedule_service import DocumentDeliveryScheduleService
    return DocumentDeliveryScheduleService()


# ============================================================================
# 请求/响应 Schemas
# ============================================================================

class DocumentDeliveryQueryIn(BaseModel):
    """手动查询文书请求"""
    credential_id: int = Field(
        ...,
        gt=0,
        description="账号凭证ID",
        json_schema_extra={"example": 1}
    )
    cutoff_hours: int = Field(
        default=24,
        ge=1,
        le=168,  # 最多7天
        description="截止时间（小时），只处理最近N小时内的文书",
        json_schema_extra={"example": 24}
    )
    tab: str = Field(
        default="pending",
        description="查询标签页：pending=待查阅，reviewed=已查阅",
        json_schema_extra={"example": "pending"}
    )

    class Config:
        json_schema_extra = {
            "example": {
                "credential_id": 1,
                "cutoff_hours": 24,
                "tab": "pending"
            }
        }


class DocumentDeliveryQueryOut(BaseModel):
    """手动查询文书响应"""
    success: bool = Field(..., description="是否成功")
    data: dict = Field(..., description="查询结果")
    message: str = Field(..., description="响应消息")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "data": {
                    "total_found": 5,
                    "processed_count": 3,
                    "skipped_count": 2,
                    "failed_count": 0,
                    "case_log_ids": [101, 102, 103],
                    "errors": []
                },
                "message": "查询完成，处理了3个文书"
            }
        }


class DocumentDeliveryScheduleCreateIn(BaseModel):
    """创建定时任务请求"""
    credential_id: int = Field(
        ...,
        gt=0,
        description="账号凭证ID",
        json_schema_extra={"example": 1}
    )
    runs_per_day: int = Field(
        default=1,
        ge=1,
        le=24,
        description="每天运行次数",
        json_schema_extra={"example": 2}
    )
    hour_interval: int = Field(
        default=24,
        ge=1,
        le=24,
        description="运行间隔（小时）",
        json_schema_extra={"example": 12}
    )
    cutoff_hours: int = Field(
        default=24,
        ge=1,
        le=168,
        description="截止时间（小时），只处理最近N小时内的文书",
        json_schema_extra={"example": 24}
    )
    is_active: bool = Field(
        default=True,
        description="是否启用",
        json_schema_extra={"example": True}
    )

    class Config:
        json_schema_extra = {
            "example": {
                "credential_id": 1,
                "runs_per_day": 2,
                "hour_interval": 12,
                "cutoff_hours": 24,
                "is_active": True
            }
        }


class DocumentDeliveryScheduleUpdateIn(BaseModel):
    """更新定时任务请求"""
    runs_per_day: Optional[int] = Field(
        None,
        ge=1,
        le=24,
        description="每天运行次数",
        json_schema_extra={"example": 3}
    )
    hour_interval: Optional[int] = Field(
        None,
        ge=1,
        le=24,
        description="运行间隔（小时）",
        json_schema_extra={"example": 8}
    )
    cutoff_hours: Optional[int] = Field(
        None,
        ge=1,
        le=168,
        description="截止时间（小时）",
        json_schema_extra={"example": 48}
    )
    is_active: Optional[bool] = Field(
        None,
        description="是否启用",
        json_schema_extra={"example": False}
    )

    class Config:
        json_schema_extra = {
            "example": {
                "runs_per_day": 3,
                "hour_interval": 8,
                "cutoff_hours": 48,
                "is_active": False
            }
        }


class DocumentDeliveryScheduleOut(BaseModel):
    """定时任务响应"""
    id: int = Field(..., description="任务ID")
    credential_id: int = Field(..., description="账号凭证ID")
    runs_per_day: int = Field(..., description="每天运行次数")
    hour_interval: int = Field(..., description="运行间隔（小时）")
    cutoff_hours: int = Field(..., description="截止时间（小时）")
    is_active: bool = Field(..., description="是否启用")
    last_run_at: Optional[datetime] = Field(None, description="上次运行时间")
    next_run_at: Optional[datetime] = Field(None, description="下次运行时间")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    @classmethod
    def from_model(cls, obj):
        """从 Django Model 创建 Schema"""
        return cls(
            id=obj.id,
            credential_id=obj.credential_id,
            runs_per_day=obj.runs_per_day,
            hour_interval=obj.hour_interval,
            cutoff_hours=obj.cutoff_hours,
            is_active=obj.is_active,
            last_run_at=obj.last_run_at,
            next_run_at=obj.next_run_at,
            created_at=obj.created_at,
            updated_at=obj.updated_at
        )

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v is not None else None
        }


# ============================================================================
# 手动查询接口
# ============================================================================

@router.post("/document-delivery/query", response=DocumentDeliveryQueryOut)
def manual_query(request, payload: DocumentDeliveryQueryIn):
    """
    手动触发文书查询
    
    立即执行文书查询和下载，返回处理结果
    """
    service = _get_document_delivery_service()
    
    # 计算截止时间
    cutoff_time = timezone.now() - timedelta(hours=payload.cutoff_hours)
    
    # 执行查询
    result = service.query_and_download(
        credential_id=payload.credential_id,
        cutoff_time=cutoff_time,
        tab=payload.tab
    )
    
    return DocumentDeliveryQueryOut(
        success=True,
        data={
            "total_found": result.total_found,
            "processed_count": result.processed_count,
            "skipped_count": result.skipped_count,
            "failed_count": result.failed_count,
            "case_log_ids": result.case_log_ids,
            "errors": result.errors
        },
        message=f"查询完成，处理了{result.processed_count}个文书"
    )


# ============================================================================
# 定时任务管理接口
# ============================================================================

@router.get("/document-delivery/schedules", response=List[DocumentDeliveryScheduleOut])
@paginate(PageNumberPagination, page_size=20)
def list_schedules(
    request,
    credential_id: Optional[int] = None,
    is_active: Optional[bool] = None
):
    """
    查询定时任务列表
    
    支持按凭证ID和启用状态筛选
    """
    service = _get_document_delivery_schedule_service()
    schedules = service.list_schedules(
        credential_id=credential_id,
        is_active=is_active
    )
    
    return [DocumentDeliveryScheduleOut.from_model(schedule) for schedule in schedules]


@router.post("/document-delivery/schedules", response=DocumentDeliveryScheduleOut)
def create_schedule(request, payload: DocumentDeliveryScheduleCreateIn):
    """
    创建定时任务
    
    为指定的账号凭证创建文书查询定时任务
    """
    service = _get_document_delivery_schedule_service()
    
    schedule = service.create_schedule(
        credential_id=payload.credential_id,
        runs_per_day=payload.runs_per_day,
        hour_interval=payload.hour_interval,
        cutoff_hours=payload.cutoff_hours,
        is_active=payload.is_active
    )
    
    return DocumentDeliveryScheduleOut.from_model(schedule)


@router.put("/document-delivery/schedules/{schedule_id}", response=DocumentDeliveryScheduleOut)
def update_schedule(request, schedule_id: int, payload: DocumentDeliveryScheduleUpdateIn):
    """
    更新定时任务
    
    更新指定定时任务的配置参数
    """
    service = _get_document_delivery_schedule_service()
    
    # 构建更新参数字典，只包含非None的字段
    update_kwargs = {}
    if payload.runs_per_day is not None:
        update_kwargs['runs_per_day'] = payload.runs_per_day
    if payload.hour_interval is not None:
        update_kwargs['hour_interval'] = payload.hour_interval
    if payload.cutoff_hours is not None:
        update_kwargs['cutoff_hours'] = payload.cutoff_hours
    if payload.is_active is not None:
        update_kwargs['is_active'] = payload.is_active
    
    schedule = service.update_schedule(schedule_id, **update_kwargs)
    
    return DocumentDeliveryScheduleOut.from_model(schedule)


@router.delete("/document-delivery/schedules/{schedule_id}")
def delete_schedule(request, schedule_id: int):
    """
    删除定时任务
    
    删除指定的定时任务配置
    """
    service = _get_document_delivery_schedule_service()
    service.delete_schedule(schedule_id)
    
    return {
        "success": True,
        "message": f"定时任务 {schedule_id} 已删除"
    }


@router.get("/document-delivery/schedules/{schedule_id}", response=DocumentDeliveryScheduleOut)
def get_schedule(request, schedule_id: int):
    """
    查询单个定时任务详情
    
    返回指定定时任务的详细配置信息
    """
    service = _get_document_delivery_schedule_service()
    schedule = service.get_schedule(schedule_id)
    return DocumentDeliveryScheduleOut.from_model(schedule)