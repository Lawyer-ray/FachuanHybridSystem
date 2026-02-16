"""API schemas and serializers."""

from __future__ import annotations

"""财产保全询价 Schemas"""

from datetime import datetime
from decimal import Decimal
from typing import Any, ClassVar, cast

from pydantic import BaseModel, Field, field_validator


class PreservationQuoteCreateSchema(BaseModel):
    """创建询价任务的输入 Schema"""

    preserve_amount: Decimal = Field(
        ..., gt=0, description="保全金额,必须为正数", json_schema_extra={"example": 100000.00}
    )
    corp_id: str = Field(
        ..., min_length=1, max_length=32, description="企业/法院ID", json_schema_extra={"example": "440100"}
    )
    category_id: str = Field(
        ..., min_length=1, max_length=32, description="分类ID (cPid)", json_schema_extra={"example": "1"}
    )
    credential_id: int = Field(..., gt=0, description="账号凭证ID", json_schema_extra={"example": 1})

    @field_validator("preserve_amount")
    @classmethod
    def validate_preserve_amount(cls, v: Decimal) -> Decimal:
        """验证保全金额必须为正数"""
        if v <= 0:
            raise ValueError("保全金额必须为正数")
        return v

    @field_validator("corp_id", "category_id")
    @classmethod
    def validate_not_empty(cls, v: str) -> str:
        """验证字段不能为空"""
        if not v or not v.strip():
            raise ValueError("字段不能为空")
        return v.strip()


class InsuranceQuoteSchema(BaseModel):
    """保险公司报价输出 Schema"""

    id: int = Field(..., description="报价记录ID")
    preservation_quote_id: int = Field(..., description="询价任务ID")
    company_id: str = Field(..., description="保险公司ID")
    company_code: str = Field(..., description="保险公司编码")
    company_name: str = Field(..., description="保险公司名称")
    premium: Decimal | None = Field(None, description="报价金额")
    min_rate: Decimal | None = Field(None, description="最低费率")
    max_rate: Decimal | None = Field(None, description="最高费率")
    status: str = Field(..., description="查询状态 (success/failed)")
    error_message: str | None = Field(None, description="错误信息")
    response_data: dict[str, Any] | None = Field(None, description="完整响应数据")
    created_at: datetime = Field(..., description="创建时间")

    class Config:
        from_attributes: bool = True
        json_encoders: ClassVar = {
            Decimal: lambda v: float(v) if v is not None else None,
            datetime: lambda v: v.isoformat() if v is not None else None,
        }


class PreservationQuoteSchema(BaseModel):
    """询价任务输出 Schema"""

    id: int = Field(..., description="任务ID")
    preserve_amount: Decimal = Field(..., description="保全金额")
    corp_id: str = Field(..., description="企业/法院ID")
    category_id: str = Field(..., description="分类ID")
    credential_id: int | None = Field(None, description="凭证ID")
    status: str = Field(..., description="任务状态")
    total_companies: int = Field(..., description="保险公司总数")
    success_count: int = Field(..., description="成功查询数")
    failed_count: int = Field(..., description="失败查询数")
    error_message: str | None = Field(None, description="错误信息")
    created_at: datetime = Field(..., description="创建时间")
    started_at: datetime | None = Field(None, description="开始时间")
    finished_at: datetime | None = Field(None, description="完成时间")
    quotes: list[InsuranceQuoteSchema] = Field(default_factory=list, description="保险公司报价列表")

    @classmethod
    def from_model(cls, obj: Any) -> PreservationQuoteCreateSchema:
        """从 Django Model 创建 Schema,处理关联查询"""
        return cls(  # type: ignore[return-value]
            id=cast(int, obj.id),
            preserve_amount=obj.preserve_amount,
            corp_id=obj.corp_id,
            category_id=obj.category_id,
            credential_id=obj.credential_id,
            status=obj.status,
            total_companies=obj.total_companies,
            success_count=obj.success_count,
            failed_count=obj.failed_count,
            error_message=obj.error_message,
            created_at=cast(Any, obj.created_at),
            started_at=obj.started_at,
            finished_at=obj.finished_at,
            quotes=[],
        )

    class Config:
        from_attributes: bool = True
        json_encoders: ClassVar = {
            Decimal: lambda v: float(v) if v is not None else None,
            datetime: lambda v: v.isoformat() if v is not None else None,
        }


class QuoteListItemSchema(BaseModel):
    """询价任务列表项 Schema(不包含详细报价)"""

    id: int = Field(..., description="任务ID")
    preserve_amount: Decimal = Field(..., description="保全金额")
    corp_id: str = Field(..., description="企业/法院ID")
    category_id: str = Field(..., description="分类ID")
    status: str = Field(..., description="任务状态")
    total_companies: int = Field(..., description="保险公司总数")
    success_count: int = Field(..., description="成功查询数")
    failed_count: int = Field(..., description="失败查询数")
    success_rate: float = Field(..., description="成功率(百分比)")
    created_at: datetime = Field(..., description="创建时间")
    started_at: datetime | None = Field(None, description="开始时间")
    finished_at: datetime | None = Field(None, description="完成时间")

    @classmethod
    def from_model(cls, obj: Any) -> PreservationQuoteCreateSchema:
        """从 Django Model 创建 Schema,计算 success_rate"""
        return cls(  # type: ignore[return-value]
            id=cast(int, obj.id),
            preserve_amount=obj.preserve_amount,
            corp_id=obj.corp_id,
            category_id=obj.category_id,
            status=obj.status,
            total_companies=obj.total_companies,
            success_count=obj.success_count,
            failed_count=obj.failed_count,
            success_rate=obj.get_success_rate(),
            created_at=cast(Any, obj.created_at),
            started_at=obj.started_at,
            finished_at=obj.finished_at,
        )

    class Config:
        from_attributes: bool = True
        json_encoders: ClassVar = {
            Decimal: lambda v: float(v) if v is not None else None,
            datetime: lambda v: v.isoformat() if v is not None else None,
        }


class QuoteListSchema(BaseModel):
    """询价任务分页列表响应 Schema"""

    total: int = Field(..., description="总记录数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页记录数")
    total_pages: int = Field(..., description="总页数")
    items: list[QuoteListItemSchema] = Field(..., description="任务列表")

    class Config:
        json_encoders: ClassVar = {
            Decimal: lambda v: float(v) if v is not None else None,
            datetime: lambda v: v.isoformat() if v is not None else None,
        }


class QuoteExecuteResponseSchema(BaseModel):
    """执行询价任务响应 Schema"""

    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="响应消息")
    data: PreservationQuoteSchema | None = Field(None, description="询价结果")

    class Config:
        json_encoders: ClassVar = {
            Decimal: lambda v: float(v) if v is not None else None,
            datetime: lambda v: v.isoformat() if v is not None else None,
        }
