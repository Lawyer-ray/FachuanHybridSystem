"""UI 动作下发（T1 单向通道）—— 让 AI 能操作页面，但**不假装看见结果**。

## 与 ``ask_user`` 的根本差别：绝不 wait、绝不注册 waiter

``question.py`` 会登记一个等待器并阻塞到律师回答（超时 180 s），因为它要的是**答案**，
答案回来之前模型没法继续。UI 动作要的不是答案：动作是「手势」，下发即完成，
页面在毫秒内自己执行完。

于是本模块**不注册 waiter、不 ``await`` 任何回执**，理由有三条，每条都是本仓库的实测事实：

1. **占位**：pi 的进程池槽位是稀缺资源，一个动作等 8 s 就等于把律师的并发能力按动作数
   打折（``question.py`` 的 180 s 阻塞已经因此被审计收紧过一轮）。
2. **回执要建表**：跨请求回执（AG-UI 式）需要新表 + pending 补拉 + 超时清理，而它换来的
   只是模型"知道页面变了"——这笔账在 P0/P1 里不成立（08 §3、§14.7）。
3. **不该知道的就别让它说**：模型一旦"看到"执行成功，就会向律师断言"已切换到待处理"；
   而真实失败（懒 chunk 没就绪、路由 404）只有前端知道。返回值里写死 ``observed: False``
   是**刻意让模型无法断言结果**，比事后纠正一句假话便宜得多。

## 失败一律用返回值表达，不抛异常

模型只能看到工具返回值：抛异常会被 MCP 包成「工具执行失败」，模型只能拿同样的参数
重试；返回 ``invalid_args`` 附具体字段，模型下一步能改。同样的道理，没通道
（``no_channel``）也不是错误——律师没开页面而已，告诉模型别重复调就行。

## 开关（``FACHUAN_UI_ACTION``）

照 ``mcp_server/tool_approval_gate.py`` 的三值范式：``on``（默认）/ ``dry``（只记日志）/
``off``（完全不下发）。灰度顺序是「先观察 dry，再开 on」，出问题一键 ``off``。
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from .manifest import UiAction
from .schema import validate_arguments

logger = logging.getLogger(__name__)

#: 开关环境变量：``on``（默认）/ ``dry``（只记日志）/ ``off``（不下发）。
MODE_ENV = "FACHUAN_UI_ACTION"
MODE_ON = "on"
MODE_DRY = "dry"
MODE_OFF = "off"

#: 每会话动作序号（``UiActionEvent.sequence``）的进程内计数。前端靠它发现跳号，
#: 只记 warning、**不重排**——两个动作的语义有先后（切 stage 再跳页 ≠ 跳页再切 stage）。
#: 跨 worker 不保证连续：序号是"发现异常"的信号，不是全局唯一顺序。
_SEQUENCES: dict[str, int] = {}
#: 计数字典的会话上限。后台任务可能给几百个会话各发一次动作，无上限就是内存泄漏。
#: 到顶后淘汰最早写入的会话（dict 保持插入序，够用且不用引入 LRU 依赖）。
_SEQUENCE_CAP = 1000


def ui_action_mode() -> str:
    """当前下发模式（默认 ``on``；非法值按 ``on`` 处理——与审批闸门同口径）。"""
    raw = (os.environ.get(MODE_ENV, MODE_ON) or "").strip().lower()
    if raw in (MODE_OFF, "0", "false", "no"):
        return MODE_OFF
    if raw == MODE_DRY:
        return MODE_DRY
    if raw in (MODE_ON, "1", "true", "yes", ""):
        return MODE_ON
    logger.warning("非法 %s=%r，按 %s 处理", MODE_ENV, raw, MODE_ON)
    return MODE_ON


def _next_sequence(session_id: str) -> int:
    if session_id not in _SEQUENCES and len(_SEQUENCES) >= _SEQUENCE_CAP:
        _SEQUENCES.pop(next(iter(_SEQUENCES)), None)
    sequence = _SEQUENCES.get(session_id, 0) + 1
    _SEQUENCES[session_id] = sequence
    return sequence


def _log_dispatch(session_id: str | None, action: UiAction, delivered: bool) -> None:
    """结构化下发日志：审计要求能回答「谁让 AI 干了什么」，``action``/``risk`` 必须在内。"""
    logger.info(
        "ui_action dispatch session=%s action=%s risk=%s delivered=%s",
        session_id,
        action.name,
        action.risk,
        delivered,
    )


async def publish_ui_action(
    *,
    action: UiAction,
    arguments: dict[str, Any],
    session_id: str | None,
) -> dict[str, Any]:
    """把动作推到会话的 SSE 通道；**不等待前端执行**。

    Returns:
        ``{"status": "dispatched"|"dry_run"|"no_channel"|"disabled"|"invalid_args", ...}``
        ——返回值整个交给模型，状态本身就是它下一步的依据。
    """
    mode = ui_action_mode()
    if mode == MODE_OFF:
        _log_dispatch(session_id, action, False)
        return {
            "status": "disabled",
            "delivered": False,
            "note": "服务端已关闭 UI 动作（FACHUAN_UI_ACTION=off），页面不会有任何变化。",
        }

    error = validate_arguments(action.args_schema, arguments)
    if error is not None:
        logger.info("ui_action 参数非法 session=%s action=%s error=%s", session_id, action.name, error)
        return {
            "status": "invalid_args",
            "action": action.name,
            "error": error,
            "note": "参数未通过校验，动作没有下发。请按 error 修正后重试。",
        }

    if mode == MODE_DRY:
        _log_dispatch(session_id, action, False)
        logger.info("ui_action dry 模式：只记日志未下发 session=%s action=%s", session_id, action.name)
        return {
            "status": "dry_run",
            "delivered": False,
            "note": "灰度 dry 模式：动作只记了日志，没有下发到页面；不要断言页面有任何变化。",
        }

    # 没会话 id = 不可能有 SSE 通道（后台任务 / 未挂会话的直连调用）。
    # 立即返回而不是"发了算"，理由同 ``question.py::no_channel``：白等只会占位。
    if not session_id:
        _log_dispatch(session_id, action, False)
        return {
            "status": "no_channel",
            "delivered": False,
            "note": "当前没有可接收动作的页面（律师未打开该会话）。不要假定页面已变化，也不要重复调用。",
        }

    # 延迟 import：本模块要能被 ``python -m apps.agent.services.ui_action --ts``
    # 在无 Django settings 的环境里 import（生成器只碰 manifest/schema）。
    from ..event_bus import get_bus

    bus = get_bus()
    # 判据照 ``question.py:285-298``：问真正的订阅事实（本地队列数 + 跨进程计数），
    # 而不是"缓存后端是不是 Redis"——后者在生产恒为 True，会让 delivered 永远为真。
    has_remote = bool(await bus.has_subscribers(session_id)) or bool(await bus.remote_subscriber_count(session_id))
    call_id = uuid.uuid4().hex
    published = await bus.publish(
        session_id,
        {
            "type": "ui_action",
            "call_id": call_id,
            "action": action.name,
            "arguments": arguments,
            # 期望路由只作提示：真正决定去哪由前端 registry 的执行器算
            "route": action.route,
            "sequence": _next_sequence(session_id),
        },
    )
    delivered = bool(published) or has_remote
    _log_dispatch(session_id, action, delivered)
    # note 是模型转述给律师的素材，必须和 ``delivered`` 一致：
    # 「没人收听」时依旧说「已下发到当前页面」，模型就会向律师断言页面变了——
    # 而事实上可能根本没人看到（评审 P2-4）。所以按 delivered 分叉两句。
    note = (
        "动作已下发到当前页面；执行结果不回传，不要断言页面已经变成什么样。"
        if delivered
        else "动作已发出，但当前没有页面在收听（律师可能没打开助手或已断开）；"
        "不要断言页面已经变化，可以提醒他打开后重试。"
    )
    return {
        "status": "dispatched",
        "call_id": call_id,
        "delivered": delivered,
        "observed": False,
        "note": note,
    }
