"""create_lawyer 的请求形状钉子。

2026-10-25 修复:该端点带 File() 参数(PDF/头像)是 **multipart 形状**,
表单里只有一个 ``payload`` 字段装 JSON 字符串。此前工具直接发扁平
JSON,9 个月里每次调用都 422 ``Field required: body.payload``——
靠参数契约二轮审计才现形。本测试把正确形状钉死,防止回归。
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

from mcp_server.tools.organization import lawyers


def test_create_lawyer_sends_form_wrapped_payload() -> None:
    """必须是 data={"payload": <json 串>},绝不能再回到扁平 json=。"""
    with patch.object(lawyers.client, "post", return_value={"id": 1}) as post:
        lawyers.create_lawyer(
            username="u1",
            password="Pw123456!",  # pragma: allowlist secret 测试用假密码
            real_name="张律师",
            lawyer_team_ids=[1, 2],
        )
    post.assert_called_once()
    path = post.call_args.args[0]
    kwargs: dict[str, Any] = post.call_args.kwargs
    assert path == "/organization/lawyers"
    assert "json" not in kwargs, "回到扁平 json= 会 422 Field required: body.payload"
    assert set(kwargs.get("data", {})) == {"payload"}
    body = json.loads(kwargs["data"]["payload"])
    assert body["username"] == "u1"
    assert body["real_name"] == "张律师"
    assert body["lawyer_team_ids"] == [1, 2]
