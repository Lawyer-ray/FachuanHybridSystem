"""UI 动作下发 + 回执（v2-A）—— 让 AI 能操作页面，并且把**结果**带回模型。

## v1 → v2 改了什么，以及为什么

v1 里 ``publish_ui_action`` 写死 ``observed: False``，理由是「跨请求回执要新表 + pending
补拉 + 超时清理，这笔账不成立」。v2-A 把它拆开看清了：**注入点就是工具返回值本身**
（工具调用发生在模型循环内部），所以回执的**等待链路**既不需要表、也不需要再开一次
请求，只需要① ``publish`` 之后 ``await`` 最多 2 秒；② 没等到就进进程内积压，由同一会话
的下一次工具调用或 ``ui_action_results`` 取走（机制见 :mod:`.ack`）。

M1 补的是另一件事：``confirm`` / ``guarded`` 档动作要留**审计台账**（``AgentUiAction``，
见 :mod:`.audit`）。那张表不参与等待与补拉——它是「谁让 AI 干了什么、页面回了什么」的
持久痕迹，写失败也照样下发、照样收回执。

## 为什么「页面说成功」还要再核实一遍

``outcome`` 的唯一来源是前端回执，而回执就是**页面自己说**的话。对服务端自己拥有数据的
动作（如 ``ui_material_prep_judge`` 改的是 ``InboxMessage.draft_state``），这就等于让
页面给库里的事实作证。所以拿到 ``ok`` 回执后，动作若在清单里声明了 ``verify``，
本模块会跑一次 :mod:`.verify` 去看库里真的变了没有，并把 ``verified`` / ``verify_note``
拼进**工具返回值**——那是模型唯一看得见的地方，文案在那里就定死了它能不能对律师说
「已完成」。没声明 ``verify``、或没拿到回执时，返回值一个字段都不加。

v1 那条「不该知道的就别让它说」并没有被推翻，它约束的是**措辞**而不是**能力**：
``observed`` 为真才允许断言页面变了；为假时 note 必须明确说「拿到回执前不要断言」。

## 为什么等 2 秒而不是像 ``ask_user`` 那样等 180 秒

``question.py`` 敢阻塞，因为等的是**答案**——没有答案模型没法继续。这里等的是
一次已经发生的页面跳转（实测 100~600ms），等更久只是白占 pi 的进程池槽位。
窗口由 ``FACHUAN_UI_ACTION_ACK_WAIT`` 控制（默认 2.0，clamp 0~8，0 = 完全不等）。

## 「同一动作同参数只允许一个在飞」为什么是数据库约束，而不是下发前的一次查询

模型没在 2 秒窗口里拿到回执时会**原样重发**同一个写动作；前端那条 5 秒同参窗只覆盖
同一个标签页，跨 worker / 跨设备完全挡不住。上一版在下发前查一眼台账，而两个 worker
同时下发同一条动作时**两边都会查空**——于是同一个写库被执行两遍。这一版把判据交给
数据库：``AgentUiAction`` 带一条部分唯一索引
``(session, action, arguments_hash) WHERE outcome='unknown'``（见 ``models/ui_action.py``），
下发前先用 :func:`audit.reserve_dispatch` **占位**：插不进去就是「已有一条在飞」，返回
``duplicate`` 并把那条的 ``call_id`` 交回去——模型下一步是去取那一次的结果
（``ui_action_results``），而不是再发一遍。

**仍然不新建 pending 表**：台账里 ``outcome="unknown"`` 那一行本身就是「已下发、没有结局」
的事实（对照 OpenHands：pending = 没有匹配 observation 的 action）。另建表会养出两个真相：
补拉、超时清理、进程重启后的对账全要在两张表之间对齐，而两张表总有一张会先漏。

**只对需要审计的档生效**（``audit.AUDITED_RISKS`` = ``confirm`` / ``guarded``）：跳页、
开面板这类 ``safe`` 动作不写台账，也就不占位、不会被拦——它重复执行无害，拦它只是
平白弄坏律师的操作。这也正是「幂等动作永不被去重」的实现方式：不再靠
``action.idempotent`` 多判一次，而是因为它根本不进这条约束。

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

返回值装配与给模型看的文案（``_dispatched_result`` / 三种 note / 核实拼装）见 :mod:`.result`。
"""

from __future__ import annotations

import logging
import math
import os
import uuid
from typing import Any

from . import ack, audit
from .manifest import UiAction

# 纯 re-export（含发布路径在用的 ``_attach_verification``）：测试直接 import 过这些私有名，
# 名字与所在模块保持不变，别删。
from .result import (
    _attach_verification,
    _describe_pending,
    _dispatched_result,
    _observed_note,
    _unobserved_note,
    _verified_note,
)
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


def _resolve_wait_seconds(override: float | None) -> float:
    """本次等待窗口：``None`` = 环境变量口径，否则 clamp 0~:data:`ack.MAX_ACK_WAIT`。

    非法值（非数字 / NaN / ±inf）回落到环境变量值并告警，口径与
    :func:`ack.ack_wait_seconds` 一致：窗口是运维开关，写错一个字符不该让整条通道失效。
    覆盖值只由本仓代码传（批量下发时第 2 步起传 0），但仍要 clamp——``min(nan, 8)`` 还是
    nan，一路传进 ``asyncio.wait_for`` 就是永不超时。
    """
    if override is None:
        return ack.ack_wait_seconds()
    try:
        seconds = float(override)
    except (TypeError, ValueError):
        logger.warning("非法等待窗口 %r，按 %s 处理", override, ack.ACK_WAIT_ENV)
        return ack.ack_wait_seconds()
    if not math.isfinite(seconds):
        logger.warning("非有限等待窗口 %r，按 %s 处理", override, ack.ACK_WAIT_ENV)
        return ack.ack_wait_seconds()
    return min(max(seconds, 0.0), ack.MAX_ACK_WAIT)


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
    batch_id: str | None = None,
    batch_index: int = 0,
    wait_seconds: float | None = None,
) -> dict[str, Any]:
    """把动作推到会话的 SSE 通道，并等最多 ``ACK_WAIT`` 秒把执行结果带回来。

    ``batch_id`` / ``batch_index`` 是**批量下发**（:mod:`.batch`）注入的批次身份，单步动作
    就是 ``None`` / ``0``。**本函数不认识批量的语义**——整批校验、只等第一步、失败即中止
    全在 batch.py，这里只负责把这两个键写进帧（键恒在，前端才只有一套读取逻辑）。
    ``wait_seconds``：本次等待窗口的覆盖值（``None`` = 按 ``FACHUAN_UI_ACTION_ACK_WAIT``，
    ``0`` = 明确不等；批量里第 2 步起就是这么发的）。

    Returns:
        ``{"status": "dispatched"|"dry_run"|"no_channel"|"disabled"|"invalid_args"|"duplicate", ...}``
        ——返回值整个交给模型，状态本身就是它下一步的依据。
        ``duplicate`` 是「同一动作同一参数还在飞」（``confirm`` / ``guarded`` 才有；``safe``
        不占位、也永远不会被判重复），返回里带的是那一次的 ``call_id``：模型该去取它的
        结果，而不是再发一遍（见模块 docstring）。
        ``dispatched`` 有两种形态：``observed=true`` 附真实 ``outcome`` / ``code`` /
        ``location``；``observed=false`` 附 ``pending=true``（稍后可用
        ``ui_action_results`` 取）。详细的字段口径见 :func:`_dispatched_result`。
        动作声明了 ``verify`` 且回执是 ``ok`` 时，``observed=true`` 那一形态还会多出
        ``verified`` / ``verify_note``（见 :func:`_attach_verification`）。
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

    # 服务端幂等的唯一一道闸：**先占位再下发**。同一会话 + 同一动作 + 同一参数最多一条
    # 「在飞」的台账行，由数据库的部分唯一索引兜底（见 models/ui_action.py 与
    # audit.reserve_dispatch）——先查后发在两个 worker 同时下发时两边都会查空，而那是
    # 同一个写库被执行两遍的直接原因。
    # 顺序必须是「生成 call_id → 占位 → 抢不到就丢掉这个 call_id（不 publish）」：
    # 占位行、下发帧、回执、核实全按同一个 call_id 走，占位之后不能再换 id。
    # 只有需要审计的档（confirm/guarded）才占位：safe 不写台账，也不该被拦。
    call_id = uuid.uuid4().hex
    reserved = False
    if action.risk in audit.AUDITED_RISKS:
        reserved, existing = await audit.reserve_dispatch(
            call_id=call_id,
            action_name=action.name,
            arguments=arguments,
            risk=action.risk,
            session_id=session_id,
            batch_id=batch_id or "",
        )
        if not reserved:
            logger.info(
                "ui_action duplicate session=%s action=%s existing=%s",
                session_id,
                action.name,
                existing,
            )
            return {
                "status": "duplicate",
                "call_id": existing,
                "delivered": False,
                "note": (
                    f"同一动作、同一参数仍在执行中（call_id={existing}）。"
                    "不要原样重发：先用 ui_action_results 取那一次的结果；"
                    "若律师换了设备/刷新过页面，让他重新说一次。"
                ),
            }

    # 延迟 import：本模块要能被 ``python -m apps.agent.services.ui_action --ts``
    # 在无 Django settings 的环境里 import（生成器只碰 manifest/schema）。
    from ..event_bus import get_bus

    bus = get_bus()
    # 判据照 ``question.py:285-298``：问真正的订阅事实（本地队列数 + 跨进程计数），
    # 而不是"缓存后端是不是 Redis"——后者在生产恒为 True，会让 delivered 永远为真。
    has_remote = bool(await bus.has_subscribers(session_id)) or bool(await bus.remote_subscriber_count(session_id))
    wait_seconds = _resolve_wait_seconds(wait_seconds)
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
                # 批次身份恒在（单步 = None / 0），与 ``sse_types.UiActionEvent`` 的默认值一致：
                # 「有值才带」会让前端多一个分支，而这个分支只在批量时走，最容易漏测。
                "batch_id": batch_id,
                "batch_index": batch_index,
            },
        )
        delivered = bool(published) or has_remote
        _log_dispatch(session_id, action, delivered)
        # 占位行在**下发之前**就写好了（回执到达时那一行必须已经存在，否则
        # apply_receipt 的条件 UPDATE 会打在空气上——前端 200ms 内就可能回执），
        # 这里只补「有没有页面在收听」。该不该写、失败要不要吞全由 audit 自己判定，
        # 也不会因为返回 False 就改下发结果（审计没有否决下发的权力）。
        # 批次身份在占位时就已进台账（审核「这一批 5 步」时要把它们串起来）。
        if reserved:
            await audit.mark_delivered(call_id, delivered)
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
    if observed is not None and str(observed.get("outcome") or "") == "ok" and action.verify:
        # 只在「页面自称成功」时核实：先看页面说什么，再看库里是不是真长成了那样。
        # 失败/中止的回执没什么好核实的（页面已经说了没成）。
        result = await _attach_verification(result, call_id=call_id, action=action, arguments=arguments)
    if earlier:
        result["earlier_results"] = [_describe_pending(item) for item in earlier]
    return result


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
