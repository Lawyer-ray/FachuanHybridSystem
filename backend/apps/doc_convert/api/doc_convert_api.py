"""要素式转换 API 层。"""

from __future__ import annotations

import logging
import urllib.parse
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from ninja import File, Form, Router, Schema
from ninja.files import UploadedFile

from apps.doc_convert.constants import MbidDefinition
from apps.doc_convert.exceptions import ZnszjDisabledError, ZnszjNotConfiguredError
from apps.doc_convert.services.doc_convert_service import DocConvertService
from apps.doc_convert.services.znszj_loader import get_znszj_client

logger = logging.getLogger(__name__)

router = Router()


# ──────────────────────────────────────────────
# Schema
# ──────────────────────────────────────────────


class MbidItem(Schema):
    """单个文书类型。"""

    mbid: str
    name: str


class MbidCategoryOut(Schema):
    """文书类型分类。"""

    category: str
    items: list[MbidItem]


class MbidListResponse(Schema):
    """文书类型列表响应。"""

    categories: list[MbidCategoryOut]


# ──────────────────────────────────────────────
# 工厂函数
# ──────────────────────────────────────────────


def _check_znszj_enabled() -> None:
    """检查 ZNSZJ_ENABLED 配置，未启用时抛出 403。"""
    if not getattr(settings, "ZNSZJ_ENABLED", False):
        raise ZnszjDisabledError()


def _get_doc_convert_service() -> DocConvertService:
    """获取 DocConvertService 实例。"""
    client = get_znszj_client()
    if client is None:
        raise ZnszjNotConfiguredError()
    return DocConvertService(znszj_client=client)


def _build_mbid_list_response(grouped: dict[str, list[MbidDefinition]]) -> MbidListResponse:
    """将分组数据转换为响应 Schema。"""
    categories = [
        MbidCategoryOut(
            category=cat,
            items=[MbidItem(mbid=item["mbid"], name=item["name"]) for item in items],
        )
        for cat, items in grouped.items()
    ]
    return MbidListResponse(categories=categories)


# ──────────────────────────────────────────────
# 端点
# ──────────────────────────────────────────────


@router.get("/mbid-list", response=MbidListResponse, summary="获取支持的文书类型列表")
def get_mbid_list(request: HttpRequest) -> Any:
    """
    返回所有支持的文书类型（mbid），按类别分组。

    不依赖私有模块，始终可用（不受 ZNSZJ_ENABLED 开关控制）。
    """
    from apps.doc_convert.constants import get_mbid_by_category

    grouped = get_mbid_by_category()
    return _build_mbid_list_response(grouped)


@router.post("/convert", summary="传统文书转要素式文书")
def convert_document(
    request: HttpRequest,
    file: UploadedFile = File(...),
    mbid: str = Form(...),
) -> HttpResponse:
    """
    上传传统文书，转换为要素式文书并返回下载。

    - file: .docx/.doc/.pdf 文件，最大 20MB
    - mbid: 文书类型标识符（参见 /mbid-list）

    需要 ZNSZJ_ENABLED=True。
    """
    _check_znszj_enabled()
    service = _get_doc_convert_service()

    file_content = file.read()
    filename = file.name or "document.docx"

    result_bytes = service.convert_document(
        file_content=file_content,
        filename=filename,
        mbid=mbid,
    )

    # 构造下载文件名
    encoded_name = urllib.parse.quote("要素式文书.docx", safe="")
    response = HttpResponse(
        content=result_bytes,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    response["Content-Disposition"] = f"attachment; filename*=UTF-8''{encoded_name}"
    return response
