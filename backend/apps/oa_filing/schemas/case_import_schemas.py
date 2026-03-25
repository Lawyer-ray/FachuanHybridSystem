"""案件导入 Schema 定义。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ninja import Field, Schema


class CaseImportSessionOut(Schema):
    """案件导入会话输出。"""

    id: int
    status: str
    phase: str
    uploaded_filename: str = ""
    total_count: int = 0
    matched_count: int = 0
    unmatched_count: int = 0
    success_count: int = 0
    skip_count: int = 0
    error_count: int = 0
    progress_message: str = ""
    error_message: str = ""
    result_data: dict[str, Any] = {}
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CasePreviewItem(Schema):
    """案件预览项。"""

    case_no: str = Field(alias="case_no", description="OA案件编号")
    status: str = Field(description="matched=已匹配, unmatched=需从OA导入, error=错误")
    existing_contract_id: int | None = Field(description="已存在的合同ID（matched时）")
    customer_names: list[str] = Field(default_factory=list, description="客户名称列表")
    error_message: str = Field(default="", description="错误信息")


class CasePreviewResponse(Schema):
    """案件预览响应。"""

    total_cases: int = Field(description="总案件数")
    matched: int = Field(description="已匹配数")
    unmatched: int = Field(description="需从OA导入数")
    preview: list[CasePreviewItem] = Field(default_factory=list, description="预览列表")


class CaseImportResult(Schema):
    """单个案件导入结果。"""

    case_no: str
    status: str = Field(description="created=新建, updated=更新, skipped=跳过, error=错误")
    contract_id: int | None = Field(default=None, description="合同ID")
    message: str = ""
    customer_ids: list[int] = Field(default_factory=list, description="创建的客户ID列表")
    conflict_warnings: list[str] = Field(default_factory=list, description="利益冲突警告")


class CaseImportResponse(Schema):
    """案件导入执行响应。"""

    success: int = Field(description="成功数量")
    failed: int = Field(description="失败数量")
    skipped: int = Field(default=0, description="跳过数量")
    total: int = Field(description="总数量")
    details: list[CaseImportResult] = Field(default_factory=list, description="详细结果")