"""证件文档相关 Schema。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ninja import Schema


class ClientIdentityDocOut(Schema):
    """客户证件文档输出 Schema"""

    id: int
    doc_type: str
    file_path: str | None = None
    uploaded_at: datetime
    media_url: str | None = None


class IdentityDocDetailOut(Schema):
    """证件文档详情输出 Schema"""

    id: int
    client_id: int
    doc_type: str
    file_path: str | None = None
    uploaded_at: datetime
    media_url: str | None = None


class IdentityRecognizeOut(Schema):
    """证件识别输出 Schema"""

    success: bool
    doc_type: str
    extracted_data: dict[str, Any]
    confidence: float
    error: str | None = None
    raw_text: str = ""


class MergeIdCardManualIn(Schema):
    """手动合并身份证请求体"""

    front_image_path: str
    back_image_path: str
    front_corners: list[list[int]]
    back_corners: list[list[int]]


class BindMergedDocIn(Schema):
    """绑定合并证件请求体"""

    client_id: int
    pdf_path: str
    doc_type: str = "id_card"
