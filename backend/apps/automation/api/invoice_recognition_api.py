"""
发票识别 API

提供发票文件上传、识别状态查询和下载接口。
"""

from __future__ import annotations

import logging
from typing import Any

from django.http import HttpResponse
from django.utils.translation import gettext as _
from ninja import File, Router
from ninja.errors import HttpError
from ninja.files import UploadedFile

logger = logging.getLogger("apps.automation")

router = Router(tags=["发票识别"])


def _get_recognition_service() -> Any:
    from apps.automation.services.wiring import get_invoice_recognition_service

    return get_invoice_recognition_service()


def _get_download_service() -> Any:
    from apps.automation.services.wiring import get_invoice_download_service

    return get_invoice_download_service()


@router.post("/{task_id}/upload")
def upload_invoices(
    request: Any,
    task_id: int,
    files: list[UploadedFile] = File(...),
) -> dict[str, Any]:
    """多文件上传 + 自动识别"""
    from django.core.exceptions import ObjectDoesNotExist, ValidationError

    service = _get_recognition_service()
    try:
        records = service.upload_and_recognize(task_id, files)
    except ObjectDoesNotExist:
        raise HttpError(404, _("任务不存在"))
    except ValidationError as exc:
        raise HttpError(400, str(exc.message if hasattr(exc, "message") else exc))

    record_list: list[dict[str, Any]] = [
        {
            "id": r.id,
            "original_filename": r.original_filename,
            "status": r.status,
            "invoice_code": r.invoice_code,
            "invoice_number": r.invoice_number,
            "is_duplicate": r.is_duplicate,
            "category": r.category,
        }
        for r in records
    ]
    return {"success": True, "count": len(records), "records": record_list}


@router.get("/{task_id}/status")
def get_task_status(
    request: Any,
    task_id: int,
) -> dict[str, Any]:
    """任务状态 + 发票记录列表"""
    from django.core.exceptions import ObjectDoesNotExist

    service = _get_recognition_service()
    try:
        data = service.get_task_status(task_id)
    except ObjectDoesNotExist:
        raise HttpError(404, _("任务不存在"))

    # 序列化 datetime/date/Decimal 为字符串
    def _serialize(obj: Any) -> Any:
        import datetime
        from decimal import Decimal

        if isinstance(obj, (datetime.datetime, datetime.date)):
            return str(obj)
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, dict):
            return {k: _serialize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_serialize(item) for item in obj]
        return obj

    serialized = _serialize(data)
    assert isinstance(serialized, dict)
    return serialized


@router.get("/{task_id}/download")
def download_invoices(
    request: Any,
    task_id: int,
    scope: str,
    fmt: str = "zip",
    invoice_id: int | None = None,
    category: str | None = None,
) -> HttpResponse:
    """灵活下载：scope=single/category/all，fmt=pdf/zip"""
    from django.core.exceptions import ObjectDoesNotExist

    content_type_map: dict[str, str] = {
        "pdf": "application/pdf",
        "zip": "application/zip",
    }
    content_type = content_type_map.get(fmt, "application/octet-stream")

    download_service = _get_download_service()

    try:
        if scope == "single":
            if invoice_id is None:
                raise HttpError(400, _("scope=single 时必须提供 invoice_id"))
            file_path, filename = download_service.download_single(invoice_id)
            with open(file_path, "rb") as f:
                data = f.read()
        elif scope == "category":
            if category is None:
                raise HttpError(400, _("scope=category 时必须提供 category"))
            data, filename = download_service.download_by_category(task_id, category, fmt)
        elif scope == "all":
            data, filename = download_service.download_all(task_id, fmt)
        else:
            raise HttpError(400, _("无效的 scope 参数，允许值：single/category/all"))
    except ObjectDoesNotExist:
        raise HttpError(404, _("任务或发票不存在"))

    response = HttpResponse(data, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
