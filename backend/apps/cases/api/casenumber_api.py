"""
案件案号 API
符合四层架构规范：只做请求/响应处理，业务逻辑在 Service 层
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, cast

from django.conf import settings
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
def list_case_numbers(request: HttpRequest, case_id: int | None = None) -> list[CaseNumberOut]:
    """获取案号列表"""
    service = _get_case_number_service()
    ctx = extract_request_context(request)
    return cast(list[CaseNumberOut], service.list_numbers(case_id=case_id, user=ctx.user))


@router.get("/case-numbers/{number_id}", response=CaseNumberOut)
def get_case_number(request: HttpRequest, number_id: int) -> CaseNumberOut:
    """获取单个案号"""
    service = _get_case_number_service()
    ctx = extract_request_context(request)
    return cast(CaseNumberOut, service.get_number(number_id=number_id, user=ctx.user))


@router.post("/case-numbers", response=CaseNumberOut)
def create_case_number(request: HttpRequest, payload: CaseNumberIn) -> CaseNumberOut:
    """创建案号"""
    service = _get_case_number_service()
    ctx = extract_request_context(request)
    return cast(
        CaseNumberOut,
        service.create_number(case_id=payload.case_id, number=payload.number, remarks=payload.remarks, user=ctx.user),
    )


@router.put("/case-numbers/{number_id}", response=CaseNumberOut)
def update_case_number(request: HttpRequest, number_id: int, payload: CaseNumberUpdate) -> CaseNumberOut:
    """更新案号"""
    service = _get_case_number_service()
    ctx = extract_request_context(request)
    data = payload.model_dump(exclude_unset=True)
    return cast(CaseNumberOut, service.update_number(number_id=number_id, data=data, user=ctx.user))


@router.delete("/case-numbers/{number_id}")
def delete_case_number(request: HttpRequest, number_id: int) -> Any:
    """删除案号"""
    service = _get_case_number_service()
    ctx = extract_request_context(request)
    return service.delete_number(number_id=number_id, user=ctx.user)


@router.post("/upload-temp-document")
def upload_temp_document(request: HttpRequest) -> dict[str, Any]:
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

        # 创建临时目录
        temp_dir = Path(settings.MEDIA_ROOT) / "case_documents" / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)

        # 防止 path traversal：只保留文件名部分，去掉路径分隔符
        safe_name = Path(str(file.name or "")).name
        temp_filename = f"{uuid.uuid4().hex}_{safe_name}"
        temp_path = temp_dir / temp_filename

        # 保存文件
        with open(temp_path, "wb+") as destination:
            for chunk in file.chunks():
                destination.write(chunk)

        return {
            "success": True,
            "temp_file_path": str(temp_path),
            "temp_file_name": file.name,
        }

    except Exception as e:
        return {"success": False, "error": f"上传失败: {e!s}"}
