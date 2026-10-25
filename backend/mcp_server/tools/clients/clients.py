"""客户 CRUD MCP tools"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field

from mcp_server.client import client
from mcp_server.tool_shaping import list_result

#: 与 apps.client.models.client.ClientType 同源(测试逐值对账)。
_ClientTypeL = Literal["natural", "legal", "non_legal_org"]


def list_clients(
    search: Annotated[str | None, Field(description="姓名/公司名关键词")] = None,
    client_type: Annotated[
        _ClientTypeL | None,
        Field(description="客户类型:natural 自然人/legal 法人/non_legal_org 非法人组织"),
    ] = None,
    is_our_client: Annotated[bool | None, Field(description="是否我方客户")] = None,
    limit: Annotated[int, Field(description="最多返回条数(默认 50,上限 2000)", ge=1, le=2000)] = 50,
    offset: Annotated[int, Field(description="跳过前 offset 条再取——truncated=true 时续取翻页用(第 N 页传 offset=N×limit)", ge=0)] = 0,
) -> dict[str, Any]:
    """查询客户列表。支持按姓名/公司名搜索（search）、客户类型（client_type：natural/legal/non_legal_org）、是否我方客户（is_our_client）筛选。

    limit 默认 50（REST 默认 1000 是给前端表格的,对模型上下文过大）;
    truncated=true 时用 offset 续取(第 N 页传 offset=N×limit),或换更窄筛选。

    Args:
        search: 姓名/公司名关键词。
        client_type: 客户类型——natural(自然人)/legal(法人)/non_legal_org(非法人组织)。
        is_our_client: 是否我方客户。
        limit: 最多返回条数(默认 50),上限 2000。
        offset: 跳过前 offset 条再取——续取翻页用。
    """
    params: dict[str, Any] = {"limit": limit + 1, "offset": offset}  # limit+1 探测:知还有更多
    if search:
        params["search"] = search
    if client_type:
        params["client_type"] = client_type
    if is_our_client is not None:
        params["is_our_client"] = is_our_client
    return list_result(client.get("/client/clients", params=params), limit=limit)


def get_client(client_id: int) -> dict[str, Any]:
    """获取单个客户的详细信息，包含身份证件、联系方式等。"""
    return client.get(f"/client/clients/{client_id}")  # type: ignore[no-any-return]


def create_client(
    name: Annotated[str, Field(description="客户名称(自然人姓名或机构全称)")],
    client_type: Annotated[_ClientTypeL, Field(description="客户类型:natural 自然人/legal 法人/non_legal_org 非法人组织")],
    phone: Annotated[str | None, Field(description="联系电话")] = None,
    address: Annotated[str | None, Field(description="地址")] = None,
    id_number: Annotated[str | None, Field(description="证件号(自然人身份证号/机构统一社会信用代码)")] = None,
    legal_representative: Annotated[str | None, Field(description="法定代表人(仅 legal/non_legal_org 需要)")] = None,
    is_our_client: Annotated[bool, Field(description="是否本所客户(默认 true)")] = True,
) -> dict[str, Any]:
    """创建新客户。client_type：natural（自然人）、legal（法人）或 non_legal_org（非法人组织）。legal_representative 仅法人/非法人组织客户需要填写。"""
    payload: dict[str, Any] = {"name": name, "client_type": client_type, "is_our_client": is_our_client}
    if phone:
        payload["phone"] = phone
    if address:
        payload["address"] = address
    if id_number:
        payload["id_number"] = id_number
    if legal_representative:
        payload["legal_representative"] = legal_representative
    return client.post("/client/clients", json=payload)  # type: ignore[no-any-return]


def parse_client_text(text: str) -> dict[str, Any]:
    """从自然语言文本中解析客户信息（姓名、电话、身份证号等），返回结构化数据。适合从聊天记录或文件中提取客户信息。"""
    return client.post("/client/clients/parse-text", json={"text": text})  # type: ignore[no-any-return]


def update_client(
    client_id: Annotated[int, Field(description="客户 ID", ge=1)],
    name: Annotated[str | None, Field(description="客户名称(不改不传)")] = None,
    client_type: Annotated[_ClientTypeL | None, Field(description="客户类型:natural/legal/non_legal_org(不改不传)")] = None,
    phone: Annotated[str | None, Field(description="联系电话")] = None,
    address: Annotated[str | None, Field(description="地址")] = None,
    id_number: Annotated[str | None, Field(description="证件号(身份证号/统一社会信用代码)")] = None,
    legal_representative: Annotated[str | None, Field(description="法定代表人(仅 legal/non_legal_org)")] = None,
    is_our_client: Annotated[bool | None, Field(description="是否本所客户")] = None,
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
    return client.put(f"/client/clients/{client_id}", json=payload)  # type: ignore[no-any-return]


def delete_client(client_id: int) -> None:
    """删除客户档案——硬删除,不可恢复;被案件/合同引用时后端拒绝。"""
    client.delete(f"/client/clients/{client_id}")


def list_clients_with_docs(
    client_type: str | None = None,
    is_our_client: bool | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """按条件列出客户（MCP 场景无法附带文档上传，仅做查询）。

    实际委托 ``GET /client/clients``（REST 返回裸数组,工具侧包成
    ``{total, items}`` 信封）。名字里的 ``with_docs`` 是历史命名，工具本身
    不返回文档。limit 默认 50（见 ``list_clients``）;truncated=true 时用
    offset 续取。

    Args:
        client_type: 客户类型——natural/legal/non_legal_org。
        is_our_client: 是否我方客户。
        search: 姓名/公司名关键词。
        limit: 最多返回条数(默认 50)。
        offset: 跳过前 offset 条再取——续取翻页用。
    """
    params: dict[str, Any] = {"limit": limit + 1, "offset": offset}  # limit+1 探测:知还有更多
    if client_type is not None:
        params["client_type"] = client_type
    if is_our_client is not None:
        params["is_our_client"] = is_our_client
    if search is not None:
        params["search"] = search
    return list_result(client.get("/client/clients", params=params), limit=limit)


def get_identity_doc_task(task_id: str) -> dict[str, Any]:
    """查询证件识别（OCR）任务的状态与结果。"""
    return client.get(f"/client/identity-doc/task/{task_id}")  # type: ignore[no-any-return]


def submit_identity_doc_recognition() -> dict[str, Any]:
    """提交证件识别异步任务（需文件，MCP 场景不可用，保留接口定义）。"""
    return client.post("/client/identity-doc/recognize/submit", json={})  # type: ignore[no-any-return]


def merge_id_card_manual(
    front_image_path: str, back_image_path: str, front_corners: list[list[int]], back_corners: list[list[int]]
) -> dict[str, Any]:
    """手动指定四角坐标合并身份证正反面为 PDF。

    Args:
        front_image_path: 正面照片的 media 相对路径或绝对路径。
        back_image_path: 背面照片的路径。
        front_corners: 正面四角像素坐标,[[x,y]×4] 按左上/右上/右下/左下顺序。
        back_corners: 背面四角坐标,同上格式。
    """
    return client.post(  # type: ignore[no-any-return]
        "/client/identity-docs/merge-id-card-manual",
        json={
            "front_image_path": front_image_path,
            "back_image_path": back_image_path,
            "front_corners": front_corners,
            "back_corners": back_corners,
        },
    )
