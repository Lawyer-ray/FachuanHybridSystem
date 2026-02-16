"""
客户 API 层
只负责请求/响应处理，不包含业务逻辑
"""
from typing import List, Optional
from django.conf import settings
import os
from ninja import Router, File
from ninja.files import UploadedFile
from pydantic import BaseModel

from ..models import Client
from ..schemas import ClientOut, ClientIn, ClientUpdateIn


class ParseTextRequest(BaseModel):
    text: str
    parse_multiple: bool = False


router = Router(tags=["Client"])


def _get_client_service():
    """工厂函数：创建 ClientService 实例"""
    from ..services import ClientService
    return ClientService()


def _get_identity_doc_service():
    """工厂函数：创建 ClientIdentityDocService 实例"""
    from ..services import ClientIdentityDocService
    return ClientIdentityDocService()


@router.get("/clients", response=List[ClientOut])
def list_clients(
    request,
    page: int = 1,
    page_size: Optional[int] = None,
    client_type: Optional[str] = None,
    is_our_client: Optional[bool] = None,
    search: Optional[str] = None,
):
    """
    获取客户列表

    API 层职责：
    1. 参数验证（通过 Schema 自动完成）
    2. 调用 Service 方法
    3. 返回响应
    """
    # 创建 Service 实例
    service = _get_client_service()

    # 调用 Service 方法（传递用户，如果已认证）
    user = getattr(request, 'auth', None) or getattr(request, 'user', None)
    clients = service.list_clients(
        page=page,
        page_size=page_size,
        client_type=client_type,
        is_our_client=is_our_client,
        search=search,
        user=user
    )

    # 返回响应
    return list(clients)


@router.post("/clients/parse-text")
def parse_client_text(request, payload: ParseTextRequest):
    """
    解析客户文本信息
    
    Args:
        payload: 包含文本和解析选项的请求体
        
    Returns:
        解析后的客户数据
    """
    service = _get_client_service()
    
    if payload.parse_multiple:
        # 解析多个客户
        from ..services.text_parser import parse_multiple_clients_text
        parsed_clients = parse_multiple_clients_text(payload.text)
        results = [c for c in parsed_clients if c.get("name")]
        return {"success": True, "clients": results}
    else:
        # 解析单个客户
        result = service.parse_client_text(payload.text)
        if result.get("name"):
            return {"success": True, "client": result}
        else:
            return {"success": False, "error": "未能解析出客户信息"}


@router.get("/clients/{client_id}", response=ClientOut)
def get_client(request, client_id: int):
    """
    获取单个客户

    API 层只负责：
    1. 接收路径参数
    2. 调用 Service
    3. 返回结果
    """
    service = _get_client_service()
    user = getattr(request, 'auth', None) or getattr(request, 'user', None)
    client = service.get_client(client_id, user)
    return client


@router.post("/clients", response=ClientOut)
def create_client(request, payload: ClientIn):
    """
    创建客户

    API 层只负责：
    1. 接收参数
    2. 调用 Service
    3. 返回结果
    """
    # 创建 Service 实例
    service = _get_client_service()

    # 调用 Service 创建客户
    user = getattr(request, 'auth', None) or getattr(request, 'user', None)
    client = service.create_client(
        data=payload.dict(),
        user=user
    )

    # 返回响应
    return client


@router.post("/clients-with-docs", response=ClientOut)
def create_client_with_docs(
    request,
    payload: ClientIn,
    doc_types: List[str],
    files: List[UploadedFile] = File(...),
):
    """
    创建客户并上传文档

    API 层只负责：
    1. 接收参数
    2. 调用 Service
    3. 处理文件上传（UI 相关逻辑）
    4. 返回结果
    """
    # 创建 Service 实例
    service = _get_client_service()

    # 调用 Service 创建客户
    user = getattr(request, 'auth', None) or getattr(request, 'user', None)
    client = service.create_client(
        data=payload.dict(),
        user=user
    )

    # 处理文件上传（UI 相关逻辑，保留在 API 层）
    if doc_types and files:
        identity_doc_service = _get_identity_doc_service()
        base_dir = os.path.join(settings.MEDIA_ROOT, "client_docs", str(client.id))
        os.makedirs(base_dir, exist_ok=True)

        for doc_type, file in zip(doc_types, files):
            target_path = os.path.join(base_dir, file.name)
            with open(target_path, "wb+") as f:
                for chunk in file.chunks():
                    f.write(chunk)

            # 委托给 ClientIdentityDocService
            identity_doc_service.add_identity_doc(
                client_id=client.id,
                doc_type=doc_type,
                file_path=os.path.abspath(target_path),
                user=user
            )

    # 返回响应
    return client


@router.put("/clients/{client_id}", response=ClientOut)
def update_client(request, client_id: int, payload: ClientUpdateIn):
    """
    更新客户

    API 层只负责：
    1. 接收参数
    2. 调用 Service
    3. 返回结果
    """
    service = _get_client_service()

    # 只传递非空字段
    data = payload.dict(exclude_unset=True)

    user = getattr(request, 'auth', None) or getattr(request, 'user', None)
    client = service.update_client(
        client_id=client_id,
        data=data,
        user=user
    )

    return client


@router.delete("/clients/{client_id}", response={204: None})
def delete_client(request, client_id: int):
    """
    删除客户

    API 层只负责：
    1. 接收参数
    2. 调用 Service
    3. 返回 204 状态码
    """
    service = _get_client_service()

    user = getattr(request, 'auth', None) or getattr(request, 'user', None)
    service.delete_client(
        client_id=client_id,
        user=user
    )

    return 204, None



