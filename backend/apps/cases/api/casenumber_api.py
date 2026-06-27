"""
案件案号 API
符合四层架构规范：只做请求/响应处理，业务逻辑在 Service 层
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, cast

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.files.storage import default_storage
from django.http import HttpRequest, JsonResponse
from ninja import Router

from apps.cases.schemas import CaseNumberIn, CaseNumberOut, CaseNumberUpdate
from apps.core.dto.request_context import extract_request_context

router = Router()


def _get_case_number_service() -> Any:
    """工厂函数：创建 CaseNumberService 实例"""
    from apps.cases.services.number.case_number_service import CaseNumberService

    return CaseNumberService()


@router.get("/case-numbers", response=list[CaseNumberOut])
async def list_case_numbers(request: HttpRequest, case_id: int | None = None) -> list[CaseNumberOut]:  # pragma: no cover
    """获取案号列表"""
    service = _get_case_number_service()
    ctx = extract_request_context(request)

    @sync_to_async
    def _fetch() -> list[Any]:
        qs = service.list_numbers(
            case_id=case_id, user=ctx.user, org_access=ctx.org_access, perm_open_access=ctx.perm_open_access,
        )
        # Eagerly evaluate queryset so Django Ninja serialization
        # (which runs in the async event loop) won't trigger sync ORM calls.
        return list(qs)

    return cast(list[CaseNumberOut], await _fetch())


@router.get("/case-numbers/{number_id}", response=CaseNumberOut)
async def get_case_number(request: HttpRequest, number_id: int) -> CaseNumberOut:  # pragma: no cover
    """获取单个案号"""
    service = _get_case_number_service()
    ctx = extract_request_context(request)

    @sync_to_async
    def _get() -> Any:
        return service.get_number(
            number_id=number_id, user=ctx.user, org_access=ctx.org_access, perm_open_access=ctx.perm_open_access,
        )

    return cast(CaseNumberOut, await _get())


@router.post("/case-numbers", response=CaseNumberOut)
async def create_case_number(request: HttpRequest, payload: CaseNumberIn) -> CaseNumberOut:  # pragma: no cover
    """创建案号"""
    service = _get_case_number_service()
    ctx = extract_request_context(request)

    @sync_to_async
    def _create() -> Any:
        return service.create_number(
            case_id=payload.case_id, number=payload.number, remarks=payload.remarks,
            user=ctx.user, org_access=ctx.org_access, perm_open_access=ctx.perm_open_access,
        )

    return cast(CaseNumberOut, await _create())


@router.put("/case-numbers/{number_id}", response=CaseNumberOut)
async def update_case_number(request: HttpRequest, number_id: int, payload: CaseNumberUpdate) -> CaseNumberOut:  # pragma: no cover
    """更新案号"""
    service = _get_case_number_service()
    ctx = extract_request_context(request)
    data = payload.model_dump(exclude_unset=True)

    @sync_to_async
    def _update() -> Any:
        return service.update_number(
            number_id=number_id, data=data, user=ctx.user,
            org_access=ctx.org_access, perm_open_access=ctx.perm_open_access,
        )

    return cast(CaseNumberOut, await _update())


@router.delete("/case-numbers/{number_id}")
async def delete_case_number(request: HttpRequest, number_id: int) -> Any:  # pragma: no cover
    """删除案号"""
    service = _get_case_number_service()
    ctx = extract_request_context(request)

    @sync_to_async
    def _delete() -> Any:
        return service.delete_number(
            number_id=number_id, user=ctx.user, org_access=ctx.org_access, perm_open_access=ctx.perm_open_access,
        )

    return await _delete()


@router.post("/upload-temp-document")
async def upload_temp_document(request: HttpRequest) -> dict[str, Any]:  # pragma: no cover
    """上传裁判文书到临时目录（供前端解析使用）"""
    import os

    try:
        file = request.FILES.get("file")
        if not file:
            return {"success": False, "error": "未上传文件"}

        # 验证文件类型
        ext = os.path.splitext(file.name or "")[1].lower()
        if ext not in [".pdf"]:
            return {"success": False, "error": "仅支持 PDF 格式"}

        # 防止 path traversal：只保留文件名部分，去掉路径分隔符
        safe_name = Path(str(file.name or "")).name
        temp_filename = f"{uuid.uuid4().hex}_{safe_name}"
        rel_path = f"case_documents/temp/{temp_filename}"

        # 保存文件 — default_storage.save 本质是同步 I/O，用 sync_to_async 包装
        @sync_to_async
        def _save() -> str:
            return default_storage.save(rel_path, file)

        saved_name = await _save()
        temp_path = Path(settings.MEDIA_ROOT) / saved_name

        return {
            "success": True,
            "temp_file_path": str(temp_path),
            "temp_file_name": file.name,
        }

    except (OSError, ValueError) as e:
        return {"success": False, "error": f"上传失败: {e!s}"}
