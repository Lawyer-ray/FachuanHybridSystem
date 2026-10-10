"""要素式转换 API 层。"""

from __future__ import annotations

import logging
import urllib.parse
from datetime import datetime
from typing import Any

from asgiref.sync import sync_to_async
from django.conf import settings
from django.http import FileResponse, HttpRequest, HttpResponse
from ninja import File, Form, Router, Schema
from ninja.files import UploadedFile

from apps.core.exceptions import NotFoundError
from apps.doc_convert.constants import MbidDefinition
from apps.doc_convert.exceptions import ZnszjDisabledError, ZnszjNotConfiguredError
from apps.doc_convert.models import DocConvertRecord
from apps.doc_convert.services.doc_convert_service import DocConvertService
from apps.doc_convert.services.record_service import DocConvertRecordService


def _request_user(request: Any) -> Any:
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        user = getattr(request, "auth", None)
    return user


def _failure_error_message(exc: Exception) -> str:
    """历史记录用的失败原因：用户可读 message + 技术细节（errors.detail/step）。"""
    message = str(exc)
    errors = getattr(exc, "errors", None) or {}
    context = "；".join(str(errors[k]) for k in ("step", "detail") if errors.get(k))
    return f"{message}（{context}）" if context else message


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


class DocConvertRecordOut(Schema):
    """要素式转换记录列表项。"""

    id: int
    original_name: str
    mbid: str
    mbid_name: str
    status: str
    """success / failed"""

    error_message: str | None = None
    has_file: bool
    """成功记录才有产物文件可下载"""

    created_at: datetime | None = None


class DocConvertRecordListOut(Schema):
    """要素式转换记录分页响应。"""

    items: list[DocConvertRecordOut]
    count: int
    page: int
    num_pages: int


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
def get_mbid_list(request: HttpRequest) -> Any:  # pragma: no cover
    """
    返回所有支持的文书类型（mbid），按类别分组。

    不依赖私有模块，始终可用（不受 ZNSZJ_ENABLED 开关控制）。
    """
    from apps.doc_convert.constants import get_mbid_by_category

    grouped = get_mbid_by_category()
    return _build_mbid_list_response(grouped)


@router.post("/convert", summary="传统文书转要素式文书")
async def convert_document(  # pragma: no cover
    request: HttpRequest,
    file: UploadedFile = File(...),
    mbid: str = Form(...),
) -> HttpResponse:
    """
    上传传统文书，转换为要素式文书并返回下载。

    - file: .docx/.doc/.pdf 文件，最大 20MB
    - mbid: 文书类型标识符（参见 /mbid-list）

    需要 ZNSZJ_ENABLED=True。每次转换会落一条历史记录（含产物文件），
    供 /records 历史弹窗重新下载。
    """
    _file = file
    _mbid = mbid
    _user = getattr(request, "user", None)

    def _do_convert() -> HttpResponse:
        _check_znszj_enabled()
        service = _get_doc_convert_service()
        records = DocConvertRecordService()

        file_content = _file.read()
        filename = _file.name or "document.docx"

        try:
            result_bytes = service.convert_document(
                file_content=file_content,
                filename=filename,
                mbid=_mbid,
            )
        except Exception as exc:
            records.record_failure(
                original_name=filename, mbid=_mbid, error_message=_failure_error_message(exc), created_by=_user
            )
            raise

        records.record_success(original_name=filename, mbid=_mbid, content=result_bytes, created_by=_user)

        # 构造下载文件名
        encoded_name = urllib.parse.quote("要素式文书.docx", safe="")
        response = HttpResponse(
            content=result_bytes,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        response["Content-Disposition"] = f"attachment; filename*=UTF-8''{encoded_name}"
        return response

    return await sync_to_async(_do_convert, thread_sensitive=False)()


# ──────────────────────────────────────────────
# 历史记录
# ──────────────────────────────────────────────


@router.get("/records", response=DocConvertRecordListOut, summary="要素式转换历史记录")
def list_convert_records(  # pragma: no cover
    request: HttpRequest, status: str | None = None, page: int = 1, page_size: int = 20
) -> DocConvertRecordListOut:
    """分页列出历史转换记录（最新在前），供前端历史弹窗浏览与重新下载。"""
    items, count, num_pages = DocConvertRecordService().list_records(
        status=status, page=page, page_size=page_size, user=_request_user(request)
    )
    return DocConvertRecordListOut(
        items=[DocConvertRecordOut(**item) for item in items],
        count=count,
        page=page,
        num_pages=num_pages,
    )


@router.get("/records/{record_id}/download", summary="下载历史转换产物")
def download_convert_record(request: HttpRequest, record_id: int) -> FileResponse:  # pragma: no cover
    """重新下载某次要素式转换的产物 docx。"""
    record = DocConvertRecordService().get_record(record_id, user=_request_user(request))
    if record.status != DocConvertRecord.Status.SUCCESS or not record.output_file:
        raise NotFoundError(
            message="该记录没有可下载的产物（转换失败或文件已清理）",
            code="DOC_CONVERT_RECORD_NO_FILE",
        )

    stem = record.original_name.rsplit(".", 1)[0] if "." in record.original_name else record.original_name
    return FileResponse(
        record.output_file.open("rb"),
        as_attachment=True,
        filename=f"{stem}-要素式.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.delete("/records/{record_id}", summary="删除转换记录")
def delete_convert_record(request: HttpRequest, record_id: int) -> dict[str, str]:  # pragma: no cover
    """删除单条转换记录（产物文件随信号清理）。"""
    record = DocConvertRecordService().get_record(record_id, user=_request_user(request))
    record.delete()
    return {"status": "deleted"}
