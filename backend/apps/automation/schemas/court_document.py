"""法院文书下载 Schemas"""

from datetime import datetime
from typing import Any, ClassVar

from pydantic import BaseModel, Field, field_validator


class APIInterceptResponseSchema(BaseModel):
    """API拦截响应Schema"""

    code: int = Field(..., description="响应代码")
    msg: str = Field(..., description="响应消息")
    data: list[dict[str, Any]] = Field(..., description="文书数据列表")
    success: bool = Field(..., description="是否成功")
    totalRows: int = Field(..., description="总行数")

    @field_validator("data")
    @classmethod
    def validate_data_structure(cls, v: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """验证data数组中每个元素的必需字段"""
        required_fields: list[Any] = []
        for idx, item in enumerate(v):
            missing_fields: list[Any] = []
            if missing_fields:
                raise ValueError(f"数据项 {idx} 缺少必需字段: {', '.join(missing_fields)}")
        return v


class CourtDocumentSchema(BaseModel):
    """文书记录输出Schema"""

    id: int = Field(..., description="记录ID")
    scraper_task_id: int = Field(..., description="爬虫任务ID")
    case_id: int | None = Field(None, description="关联案件ID")

    # 文书信息
    c_sdbh: str = Field(..., description="送达编号")
    c_stbh: str = Field(..., description="上传编号")
    wjlj: str = Field(..., description="文件链接")
    c_wsbh: str = Field(..., description="文书编号")
    c_wsmc: str = Field(..., description="文书名称")
    c_fybh: str = Field(..., description="法院编号")
    c_fymc: str = Field(..., description="法院名称")
    c_wjgs: str = Field(..., description="文件格式")
    dt_cjsj: datetime = Field(..., description="创建时间(原始)")

    # 下载状态
    download_status: str = Field(..., description="下载状态")
    local_file_path: str | None = Field(None, description="本地文件路径")
    file_size: int | None = Field(None, description="文件大小(字节)")
    error_message: str | None = Field(None, description="错误信息")

    # 时间戳
    created_at: datetime = Field(..., description="记录创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    downloaded_at: datetime | None = Field(None, description="下载完成时间")

    class Config:
        from_attributes: bool = True
        json_encoders: ClassVar = {datetime: lambda v: v.isoformat() if v is not None else None}
