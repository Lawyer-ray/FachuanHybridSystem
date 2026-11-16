"""运行中插话 / 追加 / 撤回排队的请求响应契约。"""

from __future__ import annotations

from ninja import Schema


class SteerIn(Schema):
    """运行中插话 / 追加一轮的请求体。"""

    message: str


class SteerOut(Schema):
    """插话结果。``disposition`` 为 queued（已排队）或 handled（被扩展消费）。"""

    success: bool
    disposition: str


class ClearQueueOut(Schema):
    """撤回排队消息的结果；``messages`` 是被撤回的原文。"""

    success: bool
    messages: list[str]
