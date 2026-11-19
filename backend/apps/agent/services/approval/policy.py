"""用户审批策略（P2-5）—— 精确匹配优先于前缀匹配。"""

from __future__ import annotations

from ...models import AgentApprovalPolicy
from .risk import short_tool_name


def lookup_approval_policy(*, user_id: int | None, tool_name: str) -> str | None:
    """查用户对某工具的审批策略（P2-5）。

    Returns:
        "allow" / "deny" / None（无策略或 ask——走系统默认分级）。

    查询优先级：精确匹配 > 前缀匹配；同步函数（request_approval 内
    经 sync_to_async 调用）。
    """
    if user_id is None:
        return None

    # 精确匹配：全名（mcp__fachuan__delete_case）或短名（delete_case）都行
    short_name = short_tool_name(tool_name)
    exact = (
        AgentApprovalPolicy.objects.filter(user_id=user_id, is_prefix=False, tool_pattern__in=[tool_name, short_name])
        .values_list("action", flat=True)
        .first()
    )
    if exact is not None:
        return exact
    # 前缀匹配：策略表里 is_prefix=True 的行，tool_pattern 是前缀
    prefix_rows = AgentApprovalPolicy.objects.filter(user_id=user_id, is_prefix=True).values_list(
        "tool_pattern", "action"
    )
    for pattern, action in prefix_rows:
        if tool_name.startswith(pattern) or short_name.startswith(pattern):
            return action
    return None
