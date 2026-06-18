"""DocSpace schemas — 请求/响应模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# ── 配置 ──────────────────────────────────────────────────


class DocSpaceConfigOut(BaseModel):
    """DocSpace 配置信息（前端需要 portalUrl 初始化 SDK）。"""

    portal_url: str = ""
    enabled: bool = False


# ── 文档 ──────────────────────────────────────────────────


class DocSpaceDocumentOut(BaseModel):
    """文档列表/详情响应。"""

    id: int
    title: str
    docspace_file_id: int
    docspace_folder_id: int
    file_ext: str = ".docx"
    content_length: int = 0
    web_url: str = ""  # 编辑器 URL
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── 上传 ──────────────────────────────────────────────────


class DocSpaceUploadIn(BaseModel):
    """上传请求参数。"""

    folder_id: int | None = Field(default=None, description="目标文件夹 ID，留空使用默认")


class DocSpaceUploadOut(BaseModel):
    """上传响应。"""

    id: int
    title: str
    docspace_file_id: int
    web_url: str
    file_ext: str = ".docx"
    content_length: int = 0
