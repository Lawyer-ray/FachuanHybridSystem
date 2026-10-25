"""律师管理 MCP tools"""

from __future__ import annotations

import json
from typing import Annotated, Any

from pydantic import Field

from mcp_server.client import client
from mcp_server.tool_shaping import list_result


def list_lawyers(
    search: Annotated[str | None, Field(description="姓名/用户名关键词;不传返回全部(按权限可见范围)。REST 不支持按团队过滤——按团队找人先查团队拿成员名单")] = None,
    slim: Annotated[bool, Field(description="True 只回 id/姓名/电话/执业证(模型选人够用);False 回全量 DTO(含文件签名 URL 与律所嵌套,500 人律所几百 KB)")] = True,
) -> dict[str, Any]:
    """按姓名/用户名搜索律师。返回律师 ID、姓名、电话、执业证号等，用于指派律师时选择。

    - search：姓名/用户名关键词；不传则返回全部（按权限可见范围）。
    - slim 默认 True——后端全量 DTO 含文件签名 URL 与律所嵌套对象,500 人律所
      一次就是几百 KB;模型选人只需要 id/姓名/电话/执业证。需要完整字段时传
      slim=False。
    - 注意:REST 端点不支持按团队过滤（历史版本曾传 team_id,ninja 静默忽略
      未知查询参数,等于没过滤）——按团队找人请先查团队拿成员名单。
    """
    params: dict[str, Any] = {"slim": slim}
    if search:
        params["search"] = search
    return list_result(client.get("/organization/lawyers", params=params))


def get_lawyer(lawyer_id: int) -> dict[str, Any]:
    """获取单个律师的详细信息，包含律所、团队、执业证号等。"""
    return client.get(f"/organization/lawyers/{lawyer_id}")  # type: ignore[no-any-return]


def create_lawyer(
    username: Annotated[str, Field(description="登录用户名(必填,唯一)")],
    password: Annotated[str, Field(description="初始登录密码(必填,敏感)")],
    real_name: Annotated[str | None, Field(description="姓名")] = None,
    phone: Annotated[str | None, Field(description="手机号")] = None,
    license_no: Annotated[str | None, Field(description="执业证号")] = None,
    id_card: Annotated[str | None, Field(description="身份证号(敏感)")] = None,
    law_firm_id: Annotated[int | None, Field(description="所属律所 ID")] = None,
    is_admin: Annotated[bool, Field(description="是否管理员")] = False,
    lawyer_team_ids: Annotated[list[int] | None, Field(description="律师团队 ID 列表")] = None,
    biz_team_ids: Annotated[list[int] | None, Field(description="业务团队 ID 列表")] = None,
) -> dict[str, Any]:
    """创建新律师账号。username 和 password 必填；law_firm_id 关联律所；
    lawyer_team_ids / biz_team_ids 关联律师团队/业务团队。

    注意:该端点因支持执业证 PDF/头像上传而是 **multipart 形状**——
    表单里只有一个 ``payload`` 字段,值为 JSON 字符串。直接发扁平 JSON
    会 422 ``Field required: body.payload``(2026-10-25 修复前该工具从未
    成功过)。执业证 PDF 与头像本工具不支持,需走 admin/前端上传。
    """
    payload: dict[str, Any] = {
        "username": username,
        "password": password,
        "is_admin": is_admin,
    }
    if real_name:
        payload["real_name"] = real_name
    if phone:
        payload["phone"] = phone
    if license_no:
        payload["license_no"] = license_no
    if id_card:
        payload["id_card"] = id_card
    if law_firm_id is not None:
        payload["law_firm_id"] = law_firm_id
    if lawyer_team_ids is not None:
        payload["lawyer_team_ids"] = lawyer_team_ids
    if biz_team_ids is not None:
        payload["biz_team_ids"] = biz_team_ids
    return client.post("/organization/lawyers", data={"payload": json.dumps(payload)})  # type: ignore[no-any-return]


def update_lawyer(
    lawyer_id: Annotated[int, Field(description="律师 ID")],
    real_name: Annotated[str | None, Field(description="姓名;只传需要修改的字段")] = None,
    phone: Annotated[str | None, Field(description="手机号")] = None,
    license_no: Annotated[str | None, Field(description="执业证号")] = None,
    id_card: Annotated[str | None, Field(description="身份证号(敏感)")] = None,
    law_firm_id: Annotated[int | None, Field(description="所属律所 ID")] = None,
    is_admin: Annotated[bool | None, Field(description="是否管理员")] = None,
    password: Annotated[str | None, Field(description="登录密码(敏感——只在确需重置时传)")] = None,
    lawyer_team_ids: Annotated[list[int] | None, Field(description="律师团队 ID 列表(整体替换)")] = None,
    biz_team_ids: Annotated[list[int] | None, Field(description="业务团队 ID 列表(整体替换)")] = None,
) -> dict[str, Any]:
    """更新律师信息。只传需要修改的字段，未传字段不修改。

    与 create_lawyer 同理:端点带 File() 参数(PDF/头像)是 multipart
    形状,表单单一 ``payload`` 字段装 JSON 串——直接发扁平 JSON 会 422
    (2026-10-25 修复前该工具从未成功过)。

    Args:
        lawyer_id: 律师 ID。
        real_name: 姓名。
        phone: 手机号。
        license_no: 执业证号。
        id_card: 身份证号(敏感)。
        law_firm_id: 所属律所 ID。
        is_admin: 是否管理员。
        password: 登录密码(敏感——只在确需重置时传)。
        lawyer_team_ids: 律师团队 ID 列表(整体替换)。
        biz_team_ids: 业务团队 ID 列表(整体替换)。
    """
    payload: dict[str, Any] = {}
    if real_name is not None:
        payload["real_name"] = real_name
    if phone is not None:
        payload["phone"] = phone
    if license_no is not None:
        payload["license_no"] = license_no
    if id_card is not None:
        payload["id_card"] = id_card
    if law_firm_id is not None:
        payload["law_firm_id"] = law_firm_id
    if is_admin is not None:
        payload["is_admin"] = is_admin
    if password is not None:
        payload["password"] = password
    if lawyer_team_ids is not None:
        payload["lawyer_team_ids"] = lawyer_team_ids
    if biz_team_ids is not None:
        payload["biz_team_ids"] = biz_team_ids
    return client.put(f"/organization/lawyers/{lawyer_id}", data={"payload": json.dumps(payload)})  # type: ignore[no-any-return]


def delete_lawyer(lawyer_id: int) -> None:
    """删除律师账号——管理员操作;该律师创建过案件时后端拒绝,会同时移出全部团队。"""
    client.delete(f"/organization/lawyers/{lawyer_id}")
