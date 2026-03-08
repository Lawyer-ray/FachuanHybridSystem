"""客户相关 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_clients(
    search: str | None = None,
    client_type: str | None = None,
    is_our_client: bool | None = None,
    page_size: int = 20,
) -> list[dict[str, Any]]:
    """查询客户列表。支持按姓名/公司名搜索（search）、客户类型（client_type：individual/company）、是否我方客户（is_our_client）筛选。"""
    params: dict[str, Any] = {"page_size": page_size}
    if search:
        params["search"] = search
    if client_type:
        params["client_type"] = client_type
    if is_our_client is not None:
        params["is_our_client"] = is_our_client
    return client.get("/client/clients", params=params)  # type: ignore[return-value]


def get_client(client_id: int) -> dict[str, Any]:
    """获取单个客户的详细信息，包含身份证件、联系方式等。"""
    return client.get(f"/client/clients/{client_id}")  # type: ignore[return-value]


def create_client(
    name: str,
    client_type: str,
    phone: str | None = None,
    address: str | None = None,
    id_number: str | None = None,
    legal_representative: str | None = None,
    is_our_client: bool = True,
) -> dict[str, Any]:
    """创建新客户。client_type：individual（个人）或 company（公司）。legal_representative 仅公司客户需要填写。"""
    payload: dict[str, Any] = {"name": name, "client_type": client_type, "is_our_client": is_our_client}
    if phone:
        payload["phone"] = phone
    if address:
        payload["address"] = address
    if id_number:
        payload["id_number"] = id_number
    if legal_representative:
        payload["legal_representative"] = legal_representative
    return client.post("/client/clients", json=payload)  # type: ignore[return-value]


def parse_client_text(text: str) -> dict[str, Any]:
    """从自然语言文本中解析客户信息（姓名、电话、身份证号等），返回结构化数据。适合从聊天记录或文件中提取客户信息。"""
    return client.post("/client/clients/parse-text", json={"text": text})  # type: ignore[return-value]
