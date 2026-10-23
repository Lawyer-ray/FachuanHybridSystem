"""身份与时间 MCP tools —— 让模型知道「我在为谁、在什么时间」工作。

## 为什么单独成模块

MCP 工具全部以律师本人身份调 REST（`identity.py` 透传 token），行级过滤与
审计都跑在该律师名下——但**模型自己不知道这件事**。没有 `get_current_user`
时，用户问「你知道我是谁吗」，模型只能回答不知道；涉及「我的案件」「我团队」
的请求也只能按用户口头描述去猜。

同理，`get_server_time` 解决「今天几号」这类问题。此前模型只能从
``web_search`` 的搜索摘要里抄时间戳，一旦摘要里出现多个日期就会自相矛盾
（实测出现过同一次回答里同时出现 10-08 与 10-26）。

两个工具都很薄，但它们是系统提示词里「先确认身份/时间再下结论」这条
行为规范能够成立的**唯一支点**。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.utils import timezone

from mcp_server.client import client

#: 中文星期名，避免模型自己推算
_WEEKDAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


def get_current_user() -> dict[str, Any]:
    """获取当前对话的用户（律师）身份信息。

    返回包含 id、username、real_name、所属律所、团队、是否管理员等字段。
    涉及「我的/我团队/我负责」这类请求前应先调用本工具确认身份，
    不要凭空假设当前用户是谁。
    """
    return client.get("/organization/me")  # type: ignore[return-value]


def get_server_time() -> dict[str, Any]:
    """获取服务器当前时间与时区。

    回答「今天/现在/本周/还有几天」这类问题**必须**先调用本工具，
    不要从搜索结果或历史对话里推断日期——那样容易得到互相矛盾的时间。

    返回 ``iso``（完整 ISO 时间）、``date``（YYYY-MM-DD）、``time``（HH:MM:SS）、
    ``weekday``（中文星期）、``timezone``（时区名）、``timestamp``（Unix 秒）。
    """
    now: datetime = timezone.localtime()
    return {
        "iso": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": _WEEKDAYS[now.weekday()],
        "timezone": str(timezone.get_current_timezone()),
        "timestamp": int(now.timestamp()),
    }
