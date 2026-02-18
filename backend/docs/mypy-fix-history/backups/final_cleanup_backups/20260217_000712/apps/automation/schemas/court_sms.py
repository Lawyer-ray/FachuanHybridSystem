"""API schemas and serializers."""

from __future__ import annotations

"""法院短信处理 Schemas"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar, cast

from pydantic import BaseModel, Field, field_validator


@dataclass
class SMSParseResult:
    """短信解析结果"""

    sms_type: str
    download_links: list[str]
    case_numbers: list[str]
    party_names: list[str]
    has_valid_download_link: bool


class CourtSMSSubmitIn(BaseModel):
    """提交法院短信请求"""

    content: str = Field(..., min_length=1, description="短信内容", json_schema_extra={})
    received_at: datetime | None = Field(
        None, description="收到时间,默认为当前时间", json_schema_extra={"example": "2025-12-14T10:30:00Z"}
    )
    sender: str | None = Field(None, description="发送方号码", json_schema_extra={"example": "10690..."})

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        """验证短信内容不能为空"""
        if not v or not v.strip():
            raise ValueError("短信内容不能为空")
        return v.strip()


class CourtSMSSubmitOut(BaseModel):
    """提交法院短信响应"""

    success: bool = Field(..., description="是否成功")
    data: dict[str, Any] = Field(..., description="短信记录信息")

    class Config:
        json_schema_extra: ClassVar = {
            "example": {"success": True, "data": {"id": 123, "status": "pending", "created_at": "2025-12-14T10:30:05Z"}}
        }


class CourtSMSDetailOut(BaseModel):
    """短信处理详情响应"""

    id: int = Field(..., description="短信记录ID")
    content: str = Field(..., description="短信内容")
    received_at: datetime = Field(..., description="收到时间")
    sender: str | None = Field(None, description="发送方号码")

    # 解析结果
    sms_type: str | None = Field(None, description="短信类型")
    download_links: list[str] = Field(default_factory=list, description="下载链接列表")
    case_numbers: list[str] = Field(default_factory=list, description="案号列表")
    party_names: list[str] = Field(default_factory=list, description="当事人名称列表")

    # 处理状态
    status: str = Field(..., description="处理状态")
    error_message: str | None = Field(None, description="错误信息")
    retry_count: int = Field(..., description="重试次数")

    # 关联信息
    case: dict[str, Any] | None = Field(None, description="关联案件信息")
    documents: list[dict[str, Any]] = Field(default_factory=list, description="关联文书列表")

    # 飞书通知
    feishu_sent_at: datetime | None = Field(None, description="飞书发送时间")
    feishu_error: str | None = Field(None, description="飞书发送错误")

    # 时间戳
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    @classmethod
    def from_model(cls, obj: Any) -> CourtSMSDetailSchema:  # type: ignore[name-defined]
        """从 Django Model 创建 Schema"""
        return cls(
            id=cast(int, obj.id),
            content=obj.content,
            received_at=obj.received_at,
            sender=obj.sender,
            sms_type=obj.sms_type,
            download_links=obj.download_links,
            case_numbers=obj.case_numbers,
            party_names=obj.party_names,
            status=obj.status,
            error_message=obj.error_message,
            retry_count=obj.retry_count,
            case={},
            documents=[
                {
                    "id": cast(int, doc.id),
                    "name": doc.c_wsmc,
                    "download_url": f"/media/{doc.local_file_path}" if doc.local_file_path else None,
                }
                for doc in obj.scraper_task.court_documents.all()
                if obj.scraper_task
            ],
            feishu_sent_at=obj.feishu_sent_at,
            feishu_error=obj.feishu_error,
            created_at=cast(Any, obj.created_at),
            updated_at=cast(Any, obj.updated_at),
        )

    class Config:
        from_attributes: bool = True
        json_encoders: ClassVar = {datetime: lambda v: v.isoformat() if v is not None else None}


class CourtSMSListOut(BaseModel):
    """短信列表项响应"""

    id: int = Field(..., description="短信记录ID")
    content: str = Field(..., description="短信内容(截取前100字符)")
    received_at: datetime = Field(..., description="收到时间")
    sms_type: str | None = Field(None, description="短信类型")
    status: str = Field(..., description="处理状态")
    case_name: str | None = Field(None, description="关联案件名称")
    has_documents: bool = Field(..., description="是否有关联文书")
    feishu_sent: bool = Field(..., description="是否已发送飞书通知")
    created_at: datetime = Field(..., description="创建时间")

    @classmethod
    def from_model(cls, obj: Any) -> CourtSMSDetailSchema:  # type: ignore[name-defined]
        """从 Django Model 创建 Schema"""
        return cls(
            id=cast(int, obj.id),
            content=obj.content[:100] + "..." if len(obj.content) > 100 else obj.content,
            received_at=obj.received_at,
            sms_type=obj.sms_type,
            status=obj.status,
            case_name=obj.case.name if obj.case else None,
            has_documents=bool(obj.scraper_task and obj.scraper_task.court_documents.exists()),
            feishu_sent=bool(obj.feishu_sent_at),
            created_at=cast(Any, obj.created_at),
        )

    class Config:
        from_attributes: bool = True
        json_encoders: ClassVar = {datetime: lambda v: v.isoformat() if v is not None else None}


class CourtSMSAssignCaseIn(BaseModel):
    """手动指定案件请求"""

    case_id: int = Field(..., gt=0, description="案件ID", json_schema_extra={"example": 456})


class CourtSMSAssignCaseOut(BaseModel):
    """手动指定案件响应"""

    success: bool = Field(..., description="是否成功")
    data: dict[str, Any] = Field(..., description="更新后的短信信息")

    class Config:
        json_schema_extra: ClassVar = {
            "example": {
                "success": True,
                "data": {"id": 123, "status": "matching", "case": {"id": 456, "name": "广州市鸡鸡百货有限公司诉..."}},
            }
        }
