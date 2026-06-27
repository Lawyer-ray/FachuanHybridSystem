"""案件模板绑定 API

管理案件与文书模板的绑定关系.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from asgiref.sync import sync_to_async
from django.http import HttpRequest, HttpResponse
from ninja import Router

from apps.cases.schemas import UnifiedGenerateRequest
from apps.cases.schemas.template_binding_schemas import (
    AvailableTemplateSchema,
    BindingsResponseSchema,
    BindTemplateRequestSchema,
    GenerateTemplateRequestSchema,
    SuccessResponseSchema,
    TemplateBindingSchema,
)

router = Router()

# ==================== Factory Function ====================


def _get_binding_service() -> Any:
    """工厂函数:获取案件模板绑定服务"""
    from apps.cases.services.template.wiring import get_case_template_binding_service

    return get_case_template_binding_service()


def _get_generation_service() -> Any:
    """工厂函数:获取案件模板生成服务"""
    from apps.cases.services import CaseTemplateGenerationService

    return CaseTemplateGenerationService()


def _get_unified_template_generation_service() -> Any:
    """工厂函数:获取统一模板生成服务"""
    from apps.cases.services import UnifiedTemplateGenerationService

    return UnifiedTemplateGenerationService()


# ==================== API Endpoints ====================


@router.get("/{case_id}/template-bindings", response=BindingsResponseSchema)
async def get_case_template_bindings(request: HttpRequest, case_id: int) -> Any:  # pragma: no cover
    """
    获取案件绑定的模板列表

    按模板分类(case_sub_type)分组返回.
    """
    service = _get_binding_service()

    @sync_to_async
    def _fetch() -> Any:
        return service.get_bindings_for_case(case_id)

    return await _fetch()


@router.post("/{case_id}/template-bindings", response=TemplateBindingSchema)
async def bind_template_to_case(request: HttpRequest, case_id: int, payload: BindTemplateRequestSchema) -> Any:  # pragma: no cover
    """
    绑定模板到案件

    创建手动绑定记录(binding_source='manual_bound').
    """
    service = _get_binding_service()

    @sync_to_async
    def _bind() -> Any:
        return service.bind_template(case_id, payload.template_id)

    return await _bind()


@router.delete("/{case_id}/template-bindings/{binding_id}", response=SuccessResponseSchema)
async def unbind_template_from_case(request: HttpRequest, case_id: int, binding_id: int) -> dict[str, bool]:  # pragma: no cover
    """
    解绑模板

    删除指定的绑定记录.
    """
    service = _get_binding_service()

    @sync_to_async
    def _unbind() -> None:
        service.unbind_template(case_id, binding_id)

    await _unbind()
    return {"success": True}


@router.get("/{case_id}/available-templates", response=list[AvailableTemplateSchema])
async def get_available_templates(request: HttpRequest, case_id: int) -> Any:  # pragma: no cover
    """
    获取可绑定的模板列表

    返回所有活跃的案件模板,排除已绑定的模板.
    """
    service = _get_binding_service()

    @sync_to_async
    def _fetch() -> Any:
        return service.get_available_templates(case_id)

    return await _fetch()


@router.post("/{case_id}/generate-template")
async def generate_template_document(  # pragma: no cover
    request: HttpRequest, case_id: int, payload: GenerateTemplateRequestSchema
) -> HttpResponse:
    """
    生成模板文档并返回文件流

        case_id: 案件ID
        payload.template_id: 模板ID
        payload.client_id: 当事人ID(可选,用于法定代表人身份证明书、单独授权)
        payload.client_ids: 当事人ID列表(可选,用于合并授权)
        payload.mode: 授权模式(可选): 'individual' | 'combined'

        HttpResponse: docx 文件流

    Requirements: 2.1, 2.2, 2.3, 2.4, 6.2, 6.3, 7.2, 7.3, 7.4
    """
    service = _get_generation_service()

    @sync_to_async
    def _generate() -> tuple[bytes, str]:
        return service.generate_document(
            case_id=case_id,
            template_id=payload.template_id,
            client_id=payload.client_id,
            client_ids=payload.client_ids,
            mode=payload.mode,
        )

    content, filename = await _generate()

    response = HttpResponse(
        content, content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    # 使用 RFC 5987 编码处理中文文件名
    response["Content-Disposition"] = f"attachment; filename*=UTF-8''{filename}"
    return response


# ==================== Helper Functions ====================


def _build_file_response(content: bytes, filename: str) -> HttpResponse:
    """
    构建文件下载响应

        content: 文件字节流
        filename: 文件名

        HttpResponse: 文件下载响应
    """
    response = HttpResponse(
        content, content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    # 使用 RFC 5987 编码处理中文文件名
    encoded_filename = quote(filename)
    response["Content-Disposition"] = f"attachment; filename*=UTF-8''{encoded_filename}"
    return response


# ==================== Unified Template Generation API ====================


@router.post("/{case_id}/unified-generate")
async def unified_generate_template(request: HttpRequest, case_id: int, payload: UnifiedGenerateRequest) -> HttpResponse:  # pragma: no cover
    """
    统一模板生成 API(新端点)

    支持通过 template_id 或 function_code 生成文档.

        case_id: 案件ID
        payload.template_id: 模板ID(可选,优先使用)
        payload.function_code: 功能标识(可选,当 template_id 为空时使用)
        payload.client_id: 当事人ID(可选,用于法定代表人身份证明书、单独授权)
        payload.client_ids: 当事人ID列表(可选,用于合并授权)
        payload.mode: 授权模式(可选): 'individual' | 'combined'

        HttpResponse: docx 文件流

    Requirements: 1.5
    """
    service = _get_unified_template_generation_service()

    @sync_to_async
    def _generate() -> tuple[bytes, str]:
        return service.generate_document(
            case_id=case_id,
            template_id=payload.template_id,
            function_code=payload.function_code,
            client_id=payload.client_id,
            client_ids=payload.client_ids,
            mode=payload.mode,
        )

    content, filename = await _generate()
    return _build_file_response(content, filename)
