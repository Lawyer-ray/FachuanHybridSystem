"""DocSpace schemas — 请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from apps.core.api.schemas import SchemaMixin


# ── 配置 ──────────────────────────────────────────────────


class DocSpaceConfigOut(SchemaMixin, BaseModel):
    """DocSpace 配置信息（前端需要 portalUrl 初始化 SDK）。"""

    portal_url: str = ""
    enabled: bool = False


# ── 文档 ──────────────────────────────────────────────────


class DocSpaceDocumentOut(SchemaMixin, BaseModel):
    """文档列表/详情响应。"""

    id: int
    title: str
    docspace_file_id: int
    docspace_folder_id: int
    file_ext: str = ".docx"
    content_length: int = 0
    web_url: str = ""  # 编辑器 URL
    created_at: str = ""
    updated_at: str = ""

    model_config = {"from_attributes": True}

    @staticmethod
    def resolve_created_at(obj: object) -> str:
        return SchemaMixin._resolve_datetime_iso(getattr(obj, "created_at", None)) or ""

    @staticmethod
    def resolve_updated_at(obj: object) -> str:
        return SchemaMixin._resolve_datetime_iso(getattr(obj, "updated_at", None)) or ""


# ── 上传 ──────────────────────────────────────────────────


class DocSpaceUploadIn(BaseModel):
    """上传请求参数。"""

    folder_id: int | None = Field(default=None, description="目标文件夹 ID，留空使用默认")


class DocSpaceUploadOut(SchemaMixin, BaseModel):
    """上传响应。"""

    id: int
    title: str
    docspace_file_id: int
    web_url: str
    file_ext: str = ".docx"
    content_length: int = 0
