from __future__ import annotations

from datetime import datetime

from ninja import Schema


class ExecuteFilingIn(Schema):
    site_name: str
    contract_id: int
    case_id: int | None = None


class FilingSessionOut(Schema):
    """OA 立案会话（后台线程的执行记录）。

    ⚠️ 类名必须带 `Filing` 前缀，不能叫 `SessionOut`：
    本项目里 social_auth 也有一个 `SessionOut`（登录票据：success/goto/state/
    expires_in/message）。OpenAPI 的 components.schemas 按**类名**做 key，
    两个同名类只有一个能活下来——实测被 social_auth 那个覆盖了。
    后果是：契约里 oa-filing 的 execute/session 返回值变成 {success, goto,
    state, expires_in, message}，**没有 id**。前端照契约写就永远拿不到
    session_id，只能一直轮询失败；而生成物看起来「有类型」，编译器不会报错，
    属于最难查的一类契约污染。

    同目录的 ArchiveSessionOut / StampSessionOut 本来就带领域前缀，只有这个漏了。
    """

    id: int
    status: str
    error_message: str
    created_at: datetime


class OAConfigOut(Schema):
    id: str
    oa_system_name: str
    has_credential: bool


class FilingAttachmentOut(Schema):
    material_id: int
    filename: str
    already_exists: bool
