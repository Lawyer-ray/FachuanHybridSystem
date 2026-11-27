"""UI 动作下发 + 回执（v2-A）—— 让 AI 能操作页面，并且把**结果**带回模型。

## v1 → v2 改了什么，以及为什么

v1 里 ``publish_ui_action`` 写死 ``observed: False``，理由是「跨请求回执要新表 + pending
补拉 + 超时清理，这笔账不成立」。v2-A 把它拆开看清了：**注入点就是工具返回值本身**
（工具调用发生在模型循环内部），所以回执既不需要表、也不需要再开一次请求，只需要
① ``publish`` 之后 ``await`` 最多 2 秒；② 没等到就进进程内积压，由同一会话的下一次
工具调用或 ``ui_action_results`` 取走（机制见 :mod:`.ack`）。

v1 那条「不该知道的就别让它说」并没有被推翻，它约束的是**措辞**而不是**能力**：
``observed`` 为真才允许断言页面变了；为假时 note 必须明确说「拿到回执前不要断言」。

## 为什么等 2 秒而不是像 ``ask_user`` 那样等 180 秒

``question.py`` 敢阻塞，因为等的是**答案**——没有答案模型没法继续。这里等的是
一次已经发生的页面跳转（实测 100~600ms），等更久只是白占 pi 的进程池槽位。
窗口由 ``FACHUAN_UI_ACTION_ACK_WAIT`` 控制（默认 2.0，clamp 0~8，0 = 完全不等）。

## 积压的历史结果放在哪个字段

独立字段 ``earlier_results``（人类可读的字符串数组），不并进 ``note``：``note`` 只描述
**本次**动作，混进别的动作的历史，模型很容易把上一次的「成功」当成这一次的结果——
法律场景里说错一次「已完成」就是事故。字段名（earlier）把时序说清了。

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

from . import ack
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
    """把动作推到会话的 SSE 通道，并等最多 ``ACK_WAIT`` 秒把执行结果带回来。

    Returns:
        ``{"status": "dispatched"|"dry_run"|"no_channel"|"disabled"|"invalid_args", ...}``
        ——返回值整个交给模型，状态本身就是它下一步的依据。
        ``dispatched`` 有两种形态：``observed=true`` 附真实 ``outcome`` / ``code`` /
        ``location``；``observed=false`` 附 ``pending=true``（稍后可用
        ``ui_action_results`` 取）。详细的字段口径见 :func:`_dispatched_result`。
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
    wait_seconds = ack.ack_wait_seconds()
    # 归属先落盘：前端拿到 call_id 后可能立刻回执，而那条 POST 是在**另一个进程**里
    # 校验归属的，晚一步写就会让第一份回执被判成「未知 call_id」。
    ack.mark_dispatch_session(call_id, session_id)
    # 登记等待者必须在 publish **之前**（同 ``question.py:283`` 的踩坑记录）：顺序反了，
    # 前端 200ms 内的回执会落在「没有等待者」上，然后一路走到超时——回执明明来了却拿不到。
    # ``ACK_WAIT=0`` 时不登记：没人在等，登记只是留一个永不释放的等待对象。
    if wait_seconds > 0:
        await ack.register(call_id)
    observed: dict[str, Any] | None = None
    delivered = False
    try:
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
        observed = await ack.wait(call_id, wait_seconds)
    finally:
        await ack.discard(call_id)
    logger.info(
        "ui_action ack session=%s action=%s call_id=%s observed=%s outcome=%s",
        session_id,
        action.name,
        call_id,
        observed is not None,
        (observed or {}).get("outcome", ""),
    )
    # drain 必须在 push 之前：当次动作还没进积压表，这里取到的天然只有「上一次及更早」
    # 的积压，不会自己拼自己。两者都是同步函数，中间没有 await 点。
    earlier = ack.drain_pending(session_id)
    if observed is None:
        ack.push_pending(session_id, {"call_id": call_id, "action": action.name})
    result = _dispatched_result(
        call_id=call_id,
        delivered=delivered,
        observed=observed,
        wait_seconds=wait_seconds,
    )
    if earlier:
        result["earlier_results"] = [_describe_pending(item) for item in earlier]
    return result


def _dispatched_result(
    *,
    call_id: str,
    delivered: bool,
    observed: dict[str, Any] | None,
    wait_seconds: float,
) -> dict[str, Any]:
    """``status=dispatched`` 的两种形态（拿到回执 / 没拿到）。

    分成一个函数而不是在 :func:`publish_ui_action` 里堆 if：这两组字段是**冻结契约**
    （前端与模型两侧照抄），分开写才能一眼看出「``observed=true`` 时多了哪些键、
    ``observed=false`` 时一个都不该有」。
    """
    if observed is None:
        return {
            "status": "dispatched",
            "call_id": call_id,
            "delivered": delivered,
            "observed": False,
            "pending": True,
            "note": _unobserved_note(delivered=delivered, wait_seconds=wait_seconds),
        }
    outcome = str(observed.get("outcome") or "unknown")
    result: dict[str, Any] = {
        "status": "dispatched",
        "call_id": call_id,
        "delivered": delivered,
        "observed": True,
        "outcome": outcome,
    }
    # ``code`` 只对 error 有意义：别的 outcome 带着 code，模型会把「中止」误读成路由故障。
    if outcome == "error":
        code = str(observed.get("code") or "").strip()
        if code:
            result["code"] = code
    location = str(observed.get("location") or "").strip()
    if location:
        result["location"] = location
    # note 放最后：契约里它就是最后一项，读返回值的人从字段一路读到这句话。
    result["note"] = _observed_note(outcome, observed)
    return result


def _unobserved_note(*, delivered: bool, wait_seconds: float) -> str:
    """没拿到回执时的 note —— 三种情形文案必须不同，否则模型会替页面编结果。

    ``delivered`` 判据沿用 v1 的评审结论（P2-4）：没人收听时若仍说「已下发到当前页面」，
    模型就会向律师断言页面变了，而事实上可能根本没人看到。
    """
    if not delivered:
        return (
            "动作已发出，但当前没有页面在收听（律师可能没打开助手或已断开）；回执可能永远不会有。"
            "不要断言页面已经变化，可以提醒他打开后重试。"
        )
    if wait_seconds <= 0:
        return (
            f"动作已下发，但服务端当前不等待回执（{ack.ACK_WAIT_ENV}=0）。"
            "结果稍后可用 ui_action_results 取；拿到回执前不要断言页面已经变成什么样。"
        )
    return (
        f"动作已下发，但 {wait_seconds:g} 秒内没有收到页面回执（页面可能在切换中或律师没在看）。"
        "结果稍后可用 ui_action_results 取；拿到回执前不要断言页面已经变成什么样。"
    )


def _observed_note(outcome: str, observed: dict[str, Any]) -> str:
    """拿到回执时的 note —— 按 outcome 分叉，三种结局对模型的下一步含义完全不同。"""
    detail = str(observed.get("detail") or "").strip()
    location = str(observed.get("location") or "").strip()
    tail = f"（页面说明：{detail}）" if detail else ""
    if outcome == "ok":
        where = f"页面当前地址 {location}。" if location else ""
        return f"页面已执行该动作并回传结果：成功。{where}{tail}这一点现在可以基于事实陈述。"
    if outcome == "error":
        code = str(observed.get("code") or "unknown").strip()
        return f"页面执行该动作失败（{code}）。{tail}不要把这次动作说成已完成；可以据此换一条路或告诉律师没成功。"
    return f"页面中止了该动作（律师可能离开页面或手动取消）。{tail}不要断言页面已经变成什么样。"


def _describe_pending(item: dict[str, Any]) -> str:
    """一条积压结果 → 一句话。模型读人话比读嵌套 JSON 更不容易读错。"""
    action_name = str(item.get("action") or "未知动作")
    outcome = str(item.get("outcome") or "unknown")
    detail = str(item.get("detail") or "").strip()
    tail = f"（{detail}）" if detail else ""
    if outcome == "ok":
        location = str(item.get("location") or "").strip()
        return f"{action_name} 成功" + (f"，页面当前地址 {location}" if location else "")
    if outcome == "error":
        return f"{action_name} 失败（{item.get('code') or 'unknown'}）{tail}"
    if outcome == "aborted":
        return f"{action_name} 被页面中止{tail}"
    return f"{action_name} 结果未知（页面始终没有回执）"


async def collect_ui_action_results(session_id: str | None) -> dict[str, Any]:
    """取走本会话积压的 UI 动作结果（``ui_action_results`` 工具的实现）。

    为什么要有这个工具：``publish_ui_action`` 只等 ``ACK_WAIT`` 秒，超时后结果进积压；
    而**模型是唯一能把它写进上下文的人**（Django 插不进 pi 的子进程会话）。所以必须
    给模型一个主动取件的动作，否则积压只能在「下一次下发」时被动漏出来。

    Returns:
        ``{"status": "ok"|"no_session", "count": int, "results": [...], "note": str}``。
        ``results[].outcome`` 为 ``unknown`` 表示页面始终没有回执——**不等于成功**。
    """
    if not session_id:
        return {
            "status": "no_session",
            "count": 0,
            "results": [],
            "note": "当前工具调用没有会话上下文，取不到任何回执；不要据此判断页面有没有变化。",
        }
    results = ack.drain_pending(session_id)
    if not results:
        return {
            "status": "ok",
            "count": 0,
            "results": [],
            "note": "没有待取的回执（自上次取件以来没有下发过动作，或结果已被取走）。",
        }
    return {
        "status": "ok",
        "count": len(results),
        "results": results,
        "note": (
            "每项的 outcome：ok / error / aborted 是页面回传的真实结果；"
            "unknown 表示页面始终没有回执——不要把它当成功，也不要重复下发同一个动作。"
        ),
    }
