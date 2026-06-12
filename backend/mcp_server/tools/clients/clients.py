"""客户 CRUD MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_clients(
    search: str | None = None,
    client_type: str | None = None,
    is_our_client: bool | None = None,
) -> list[dict[str, Any]]:
    """查询客户列表。支持按姓名/公司名搜索（search）、客户类型（client_type：individual/company）、是否我方客户（is_our_client）筛选。"""
    params: dict[str, Any] = {}
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


def update_client(
    client_id: int,
    name: str | None = None,
    client_type: str | None = None,
    phone: str | None = None,
    address: str | None = None,
    id_number: str | None = None,
    legal_representative: str | None = None,
    is_our_client: bool | None = None,
) -> dict[str, Any]:
    """更新客户信息。client_type：natural（自然人）、legal（法人）、non_legal_org（非法人组织）。只传需要修改的字段。"""
    payload: dict[str, Any] = {}
    if name is not None:
        payload["name"] = name
    if client_type is not None:
        payload["client_type"] = client_type
    if phone is not None:
        payload["phone"] = phone
    if address is not None:
        payload["address"] = address
    if id_number is not None:
        payload["id_number"] = id_number
    if legal_representative is not None:
        payload["legal_representative"] = legal_representative
    if is_our_client is not None:
        payload["is_our_client"] = is_our_client
    return client.put(f"/client/clients/{client_id}", json=payload)  # type: ignore[return-value]


def delete_client(client_id: int) -> None:
    """删除客户。"""
    client.delete(f"/client/clients/{client_id}")


def list_clients_with_docs(
    client_type: str | None = None, is_our_client: bool | None = None, search: str | None = None
) -> dict[str, Any]:
    """创建客户并上传文档（需要文件，MCP 场景仅创建客户不附带文档）。"""
    params: dict[str, Any] = {}
    if client_type is not None:
        params["client_type"] = client_type
    if is_our_client is not None:
        params["is_our_client"] = is_our_client
    if search is not None:
        params["search"] = search
    return client.get("/client/clients", params=params)  # type: ignore[return-value]


def get_identity_doc_task(task_id: str) -> dict[str, Any]:
    """查询证件识别任务状态。"""
    return client.get(f"/client/identity-doc/task/{task_id}")  # type: ignore[return-value]


def submit_identity_doc_recognition() -> dict[str, Any]:
    """提交证件识别异步任务（需文件，MCP 场景不可用，保留接口定义）。"""
    return client.post("/client/identity-doc/recognize/submit", json={})  # type: ignore[return-value]


def merge_id_card_manual(
    front_image_path: str, back_image_path: str, front_corners: list[list[int]], back_corners: list[list[int]]
) -> dict[str, Any]:
    """手动指定四角坐标合并身份证正反面为 PDF。"""
    return client.post(
        "/client/identity-docs/merge-id-card-manual",
        json={
            "front_image_path": front_image_path,
            "back_image_path": back_image_path,
            "front_corners": front_corners,
            "back_corners": back_corners,
        },
    )  # type: ignore[return-value]
