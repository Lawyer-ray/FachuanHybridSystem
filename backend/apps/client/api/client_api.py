"""
客户 API 层
只负责请求/响应处理，不包含业务逻辑
"""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _

from ninja import File, Router
from ninja.files import UploadedFile
from pydantic import BaseModel

from apps.core.exceptions import ValidationException
from apps.core.request_context import extract_request_context

from apps.client.schemas import ClientIn, ClientOut, ClientUpdateIn
from apps.client.services.text_parser import parse_client_text as _parse_client, parse_multiple_clients_text as _parse_multi


class ParseTextRequest(BaseModel):
    text: str
    parse_multiple: bool = False


router = Router(tags=["Client"])


def _get_query_facade() -> Any:
    """工厂函数：创建 ClientQueryFacade 实例"""
    from apps.client.services.client_query_facade import ClientQueryFacade

    return ClientQueryFacade()


def _get_mutation_service() -> Any:
    """工厂函数：创建 ClientMutationService 实例"""
    from apps.client.services.client_mutation_service import ClientMutationService

    return ClientMutationService()


@router.get("/clients", response=list[ClientOut])
def list_clients(
    request: Any,
    page: int = 1,
    page_size: int | None = None,
    client_type: str | None = None,
    is_our_client: bool | None = None,
    search: str | None = None,
) -> list[ClientOut]:
    """获取客户列表"""
    facade = _get_query_facade()
    user = getattr(request, "auth", None) or extract_request_context(request).user
    clients = facade.list_clients(
        page=page,
        page_size=page_size or 20,
        client_type=client_type,
        is_our_client=is_our_client,
        search=search,
        user=user,
    )
    return list(clients)


@router.post("/clients/parse-text")
def parse_client_text(request: Any, payload: ParseTextRequest) -> dict[str, Any]:
    """解析客户文本信息"""
    if payload.parse_multiple:
        results = [c for c in _parse_multi(payload.text) if c.get("name")]
        return {"success": True, "clients": results}
    else:
        result = _parse_client(payload.text)
        if result.get("name"):
            return {"success": True, "client": result}
        else:
            return {"success": False, "error": str(_("未能解析出客户信息"))}


@router.get("/parse-text")
def parse_text_get(request: Any, text: str = "") -> dict[str, Any]:
    """解析客户文本（GET 方式）。"""
    return _parse_client(text)


@router.get("/clients/{client_id}", response=ClientOut)
def get_client(request: Any, client_id: int) -> Any:
    """获取单个客户"""
    facade = _get_query_facade()
    user = getattr(request, "auth", None) or extract_request_context(request).user
    return facade.get_client(client_id=client_id, user=user)


@router.post("/clients", response=ClientOut)
def create_client(request: Any, payload: ClientIn) -> Any:
    """创建客户"""
    service = _get_mutation_service()
    user = getattr(request, "auth", None) or extract_request_context(request).user
    return service.create_client(data=payload.model_dump(), user=user)


@router.post("/clients-with-docs", response=ClientOut)
def create_client_with_docs(
    request: Any,
    payload: ClientIn,
    doc_types: list[str],
    files: list[UploadedFile] = File(...),  # type: ignore[call-overload]
) -> Any:
    """创建客户并上传文档"""
    if doc_types and files and len(doc_types) != len(files):
        raise ValidationException(
            message=_("证件类型数量与文件数量不一致"),
            code="DOC_FILES_MISMATCH",
            errors={"doc_types": str(_("doc_types 与 files 长度必须一致"))},
        )

    mutation_service = _get_mutation_service()
    user = getattr(request, "auth", None) or extract_request_context(request).user
    return mutation_service.create_client_with_docs(
        data=payload.model_dump(),
        doc_types=doc_types,
        files=list(files),
        user=user,
    )


@router.put("/clients/{client_id}", response=ClientOut)
def update_client(request: Any, client_id: int, payload: ClientUpdateIn) -> Any:
    """更新客户"""
    service = _get_mutation_service()
    data = payload.model_dump(exclude_unset=True)
    user = getattr(request, "auth", None) or extract_request_context(request).user
    return service.update_client(client_id=client_id, data=data, user=user)


@router.delete("/clients/{client_id}", response={204: None})
def delete_client(request: Any, client_id: int) -> tuple[int, None]:
    """删除客户"""
    service = _get_mutation_service()
    user = getattr(request, "auth", None) or extract_request_context(request).user
    service.delete_client(client_id=client_id, user=user)

    return 204, None
