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

from apps.core.request_context import extract_request_context

from apps.client.schemas import ClientIn, ClientOut, ClientUpdateIn


class ParseTextRequest(BaseModel):
    text: str
    parse_multiple: bool = False


router = Router(tags=["Client"])


def _get_client_service() -> Any:
    """工厂函数：创建 ClientService 实例"""
    from apps.client.services import ClientService

    return ClientService()


def _get_identity_doc_service() -> Any:
    """工厂函数：创建 ClientIdentityDocService 实例"""
    from apps.client.services import ClientIdentityDocService

    return ClientIdentityDocService()


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
    service = _get_client_service()
    ctx = extract_request_context(request)
    # client_api 使用 auth 或 user，保持原有逻辑
    user = getattr(request, "auth", None) or ctx.user
    clients = service.list_clients(
        page=page, page_size=page_size, client_type=client_type, is_our_client=is_our_client, search=search, user=user
    )

    return list(clients)


@router.post("/clients/parse-text")
def parse_client_text(request: Any, payload: ParseTextRequest) -> dict[str, Any]:
    """解析客户文本信息"""
    service = _get_client_service()

    if payload.parse_multiple:
        from apps.client.services.text_parser import parse_multiple_clients_text

        parsed_clients = parse_multiple_clients_text(payload.text)
        results = [c for c in parsed_clients if c.get("name")]
        return {"success": True, "clients": results}
    else:
        result = service.parse_client_text(payload.text)
        if result.get("name"):
            return {"success": True, "client": result}
        else:
            return {"success": False, "error": _("未能解析出客户信息")}


@router.get("/clients/{client_id}", response=ClientOut)
def get_client(request: Any, client_id: int) -> Any:
    """获取单个客户"""
    service = _get_client_service()
    user = getattr(request, "auth", None) or extract_request_context(request).user
    return service.get_client(client_id, user)


@router.post("/clients", response=ClientOut)
def create_client(request: Any, payload: ClientIn) -> Any:
    """创建客户"""
    service = _get_client_service()
    user = getattr(request, "auth", None) or extract_request_context(request).user
    return service.create_client(data=payload.dict(), user=user)


@router.post("/clients-with-docs", response=ClientOut)
def create_client_with_docs(
    request: Any,
    payload: ClientIn,
    doc_types: list[str],
    files: list[UploadedFile] = File(...),  # type: ignore[call-overload]
) -> Any:
    """创建客户并上传文档"""
    service = _get_client_service()
    user = getattr(request, "auth", None) or extract_request_context(request).user
    client = service.create_client(data=payload.dict(), user=user)

    if doc_types and files:
        identity_doc_service = _get_identity_doc_service()
        for doc_type, file in zip(doc_types, files, strict=False):
            identity_doc_service.add_identity_doc_from_upload(
                client_id=client.id,
                doc_type=doc_type,
                uploaded_file=file,
                user=user,
            )

    return client


@router.put("/clients/{client_id}", response=ClientOut)
def update_client(request: Any, client_id: int, payload: ClientUpdateIn) -> Any:
    """更新客户"""
    service = _get_client_service()
    data = payload.dict(exclude_unset=True)
    user = getattr(request, "auth", None) or extract_request_context(request).user
    return service.update_client(client_id=client_id, data=data, user=user)


@router.delete("/clients/{client_id}", response={204: None})
def delete_client(request: Any, client_id: int) -> tuple[int, None]:
    """删除客户"""
    service = _get_client_service()
    user = getattr(request, "auth", None) or extract_request_context(request).user
    service.delete_client(client_id=client_id, user=user)

    return 204, None
