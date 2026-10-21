"""会话历史回放 —— 多轮对话的上下文供给。

pi 以 ``--no-session`` + 每请求新进程的方式运行，天然无记忆。多轮对话
靠把 ``AgentMessage`` 表里的历史渲染成 transcript、附在 prompt 前实现。

渲染是纯函数（输入只要带 ``role`` / ``content`` / ``tool_name`` 属性的对象），
便于单测；取数与落库在 chat_service。
"""

from __future__ import annotations

from typing import Any

#: 回放窗口：最多带多少条历史消息
MAX_HISTORY_MESSAGES = 30
#: 单条消息截断长度（历史只求延续上下文，不求完整）
PER_MESSAGE_LIMIT = 4000
#: transcript 总预算（约 8k~16k token 量级，防长会话撑爆上下文）
TOTAL_LIMIT = 24000

_ROLE_USER = "user"
_ROLE_ASSISTANT = "assistant"
_ROLE_TOOL = "tool"


def _label(message: Any) -> str:
    role = getattr(message, "role", "")
    if role == _ROLE_TOOL:
        return f"工具[{getattr(message, 'tool_name', '') or '未知'}]"
    if role == _ROLE_ASSISTANT:
        return "助手"
    return "用户"


def render_transcript(
    messages: Any,
    user_message: str,
    *,
    max_messages: int = MAX_HISTORY_MESSAGES,
    per_message_limit: int = PER_MESSAGE_LIMIT,
    total_limit: int = TOTAL_LIMIT,
) -> str:
    """把历史消息渲染成附在 prompt 前的 transcript。

    无历史时原样返回 ``user_message``（单轮对话不包壳，行为与之前一致）。
    总长超 ``total_limit`` 时从最旧的历史开始丢弃，最新消息永远保留。
    """
    entries: list[str] = []
    for message in list(messages)[-max_messages:]:
        content = str(getattr(message, "content", "") or "")[:per_message_limit]
        if not content.strip():
            continue
        entries.append(f"{_label(message)}: {content}")

    while entries and sum(len(entry) for entry in entries) + len(user_message) > total_limit:
        entries.pop(0)

    if not entries:
        return user_message

    history = "\n\n".join(entries)
    return (
        "以下是与法穿 AI 法律助手的历史对话记录（供延续上下文），"
        "请只针对最后的「最新用户消息」作答。\n\n"
        f"【历史对话】\n{history}\n\n"
        f"【最新用户消息】\n{user_message}"
    )
