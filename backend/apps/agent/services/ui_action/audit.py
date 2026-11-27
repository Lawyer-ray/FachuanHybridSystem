"""UI 动作审计 —— 把「AI 让页面干了什么 / 页面回了什么」落成可查的行（M1）。

## 写入口只有三个，且判定都收在本模块里

- :func:`record_dispatch`：下发成功后插一行（``outcome="unknown"``）；
- :func:`record_denial`：审批**未通过**时插一行（``outcome=decision="denied"``）；
- :func:`apply_receipt` / :func:`apply_verification`：回执与核实结论到达后就地更新那一行。

**为什么把「该不该写」放进写入口而不是调用方**：判定散在调用侧，早晚出现一条新路径
忘了判——那张表就不是「高危动作台账」，而是「谁知道要写就写」的抽样。收在这里之后，
调用方只有一个动作：把 facts 交给它。``record_denial`` 尤其如此：它会被**所有**工具的
拒绝路径调用，所以「不在清单里 / 风险档不是 confirm/guarded」必须由它自己静默挡掉。

## 为什么拒绝也要落行

上一版只写了「已下发」这一条路，律师点「拒绝」时库里零记录——于是「他明确拒绝过什么」
这件事事后完全无法回答（对照 MCP elicitation 把 ``decline`` 当正式结果、
OpenHands 的 ``UserRejectObservation`` 带 ``rejection_reason``）。拒绝是**决定**，
不是「什么都没发生」。

## 为什么 ``outcome`` 有 ``denied`` / ``expired`` 两个新终态

``aborted`` 一档混装了四种完全不同的原因：人点拒绝、律师关窗、等太久、前端崩。
这四种对模型的下一步含义不同（别再问 / 可重试 / 可稍后再问），对审计的含义更不同
（有人不同意 / 没人应答）。所以拆开：``denied``（有人明确拒绝）、``expired``（回执窗口
过了，从没执行过或被判为过期）。

## 终态不可变 + 回执窗口

``apply_receipt`` 只改 ``outcome="unknown"`` 的行，且要求 ``expires_at`` 未过
（:data:`RECEIPT_TTL` = 5 分钟）。迟到的回执**不能**改写已经定下的结局——对照 MCP tasks
「一旦 cancelled 必须保持 cancelled，即使执行后来成功」与 AG-UI 的 ``Interrupt.expiresAt``。
迟到的回执只做一件事：把那一行落成 ``expired`` 并把真实结局记进 ``decision_note``
（它仍然是有价值的事实：「页面后来说它成功了，但那时候我们已经按超时处理」）。

## 审计失败绝不打断下发

``publish_ui_action`` 的返回值是模型唯一的视野：为了写一行审计而抛异常，等于为了
台账牺牲掉「动作已经发生」这个事实。所以这里只 catch 具体异常
（``django.db.DatabaseError`` / ``ValueError``）并 ``logger.warning``：仓库的
``test_exception_ratchet`` 禁止扩大 ``except Exception``，而这两类正好覆盖「库挂了 /
参数不可序列化」全部真实失败形态（不可序列化在进库前就被 :func:`sanitize_arguments` /
:func:`arguments_hash_of` 收敛成字符串了）。

## 为什么模块顶层没有 Django 符号

``python -m apps.agent.services.ui_action --ts`` 要在**没有 Django settings** 的
进程里 import 整个包（生成器只碰 manifest / schema）。所以 Django 的模型与
``timezone`` 全部下沉到函数内（同 ``ack.py::_cache`` 的延迟 import）；
:mod:`.manifest` 是纯数据模块（不 import Django），顶层 import 它不违反这条约束。
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from .manifest import UI_ACTIONS

logger = logging.getLogger(__name__)

#: 需要落库的风险档。``safe`` 刻意不在内：量太大且无审计价值（见
#: ``models/ui_action.py`` 的模块 docstring）。
AUDITED_RISKS: frozenset[str] = frozenset({"confirm", "guarded"})

#: 动作名 → 清单项（清单是闭集，唯一来源是 manifest，这里只建一次索引）。
_ACTION_BY_NAME = {action.name: action for action in UI_ACTIONS}

#: 审批关联窗口：批准后多久内下发的动作仍认作「这次批准放行的」。
#: 10 分钟足够覆盖「批完 → 模型下一轮调工具 → 页面执行」，再宽就会把上一次批准
#: 错认成这一次的（审批是一次性，串批等于伪造授权）。
APPROVAL_WINDOW = timedelta(minutes=10)

#: 回执窗口：从下发算起，超过这个时长到达的回执不再改写这一行的结局。
#: 5 分钟远宽于 ack 的 2s 等待（那个窗口只决定「模型这一次看不看得到结果」），
#: 覆盖前端重试与律师缓慢操作；同时短到「一周后的迟到回执」不可能翻掉当时的判断。
RECEIPT_TTL = timedelta(seconds=300)

#: ``outcome`` 的初始值。**不是** ``ok``：回执可能永远不到，默认成功就是撒谎。
OUTCOME_UNKNOWN = "unknown"
#: 从未执行过、由「人/超时」判定的两种结局（``decision`` 同时会写同一个值）。
OUTCOME_DENIED = "denied"
OUTCOME_EXPIRED = "expired"

#: ``decision`` 的取值。空串 = 还没人判定（下发路径在找不到审批行时就是这个状态）。
DECISION_APPROVED = "approved"
DECISION_DENIED = "denied"
DECISION_EXPIRED = "expired"

#: ``error_code`` / ``observed_location`` 的落库上限（与模型字段长度一致，
#: 超长在 PostgreSQL 上是 ``DataError``——整份回执会因此丢掉）。
CODE_MAX = 32
LOCATION_MAX = 300
#: ``decision_note`` / ``verify_note`` 的落库上限（同上，与字段长度一致）。
NOTE_MAX = 300

#: 历史查询的每页硬上限（前端传再大也不给，避免一次拉全表）。
LIST_MAX_LIMIT = 200


def sanitize_arguments(arguments: Any) -> dict[str, Any]:
    """把参数脱敏后再交给 ``JSONField``（快照那条路一直走 ``scrub_for_storage``，台账也必须走）。

    两条路上同一份参数必须在库里长得一样：快照脱敏、台账不脱敏的话，律师填在表单里的
    账号/凭证会原样留在审计表里——而那张表的读者恰恰是事后翻旧账的人。

    为什么还要兜一层「不可序列化就退化成 ``{"_repr": ...}``」：``scrub_for_storage``
    只认 str / dict / list / tuple，别的东西原样返回，而 ``JSONField`` 遇到 ``datetime`` /
    ``Decimal`` / 自定义对象会在写库时抛 ``TypeError``（既不是 ``DatabaseError`` 也不是
    ``ValueError``，整行台账会静默丢掉）。审计宁可记成 ``"_repr": "<Foo object>"``
    也不能丢行——「这一行存在过」本身就是审计要回答的问题。
    """
    # 延迟 import：理由见模块 docstring（core.security 是纯工具模块，但保持同一纪律）。
    from apps.core.security.scrub import scrub_for_storage

    scrubbed = scrub_for_storage(arguments)
    if not isinstance(scrubbed, dict):
        return {"_repr": str(scrubbed)[:NOTE_MAX]}
    try:
        json.dumps(scrubbed, ensure_ascii=False)
    except (TypeError, ValueError):
        return {"_repr": str(scrubbed)[:NOTE_MAX]}
    return scrubbed


def arguments_hash_of(arguments: Any) -> str:
    """参数指纹（sha256 hexdigest）：回答「批准的是**哪一份**参数」。

    哈希的是**原始**参数而不是脱敏后的：脱敏会把值改成 ``13***11``，两个不同的账号
    会算出同一个哈希，那这条指纹就再也防不住「批 A 执行 B」了。脱敏只影响
    ``arguments`` 那一列的存储形态，不影响这列。

    序列化用 ``sort_keys``（键序不该改变指纹）+ 紧凑分隔符（空格也不该）；
    ``ensure_ascii=False`` 让中文参数按原文参与哈希。不可序列化时退回 ``str()``
    的哈希而不是抛异常——这条指纹是**附加证据**，不能因为它把整行台账搞没。
    """
    try:
        payload = json.dumps(arguments or {}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        payload = json.dumps({"_repr": str(arguments)}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _short_action_name(tool_name: str) -> str:
    """``mcp__fachuan__ui_material_prep_judge`` → ``ui_material_prep_judge``。

    前缀取 :func:`apps.agent.backends.toolface.tool_prefix`，不手写字符串：审批链历史上
    有 9 份硬编码的 ``fachuan``，任何一处改名都会让按全名匹配的判定**静默失效**。
    """
    # 延迟 import：toolface 只依赖 stdlib，但保持「顶层不引业务包」的同一纪律。
    from ...backends.toolface import tool_prefix

    prefix = tool_prefix()
    return tool_name[len(prefix) :] if tool_name.startswith(prefix) else tool_name


async def record_dispatch(
    *,
    call_id: str,
    action_name: str,
    arguments: dict[str, Any],
    risk: str,
    session_id: str | None,
    delivered: bool,
    batch_id: str = "",
) -> bool:
    """插入一行「动作已下发」；返回是否真的落库。

    ``session_id`` 为空时 ``session`` / ``user`` 留空：后台任务、未挂会话的直连调用
    都可能下发动作，这种行仍然有审计价值（谁在什么时候让 AI 干了什么）。

    ``batch_id`` 是批量下发注入的批次身份（单步动作传空串）：审核「这一批 5 步」时
    要有东西能把它们串起来，否则只能靠 ``created_at`` 相近去猜。

    **审批关联是 best-effort**：同会话、已批准、工具名以本动作名结尾、且决定时间在
    :data:`APPROVAL_WINDOW` 内的最近一条 ``AgentApproval``。找不到就留空而不是拒写——
    审批服务本身不做任何改动，这里只读。找到时同时写 ``approval`` 外键、
    ``decision="approved"`` 与 ``decided_at``：那三列是「谁批的」这条问题的正式答案，
    ``approved_by``/``approved_at`` 保留是因为历史行与列表接口还在用它们。

    Returns:
        本行是否写入成功。``False`` 有两种来源：``safe`` 档刻意不写，或写库失败。
        调用方（``publish_ui_action``）**不检查**返回值：审计不该有权力否决下发。
    """
    if risk not in AUDITED_RISKS:
        return False

    # 延迟 import：本模块要能在无 Django settings 的进程里被 import（见模块 docstring）。
    from django.db import DatabaseError
    from django.utils import timezone

    from ...models import AgentApproval, AgentSession, AgentUiAction
    from ..session_service import _as_uuid

    try:
        session = None
        normalized = _as_uuid(session_id) if session_id else None
        if normalized is not None:
            session = await AgentSession.objects.filter(session_id=normalized).afirst()
        approved_by_id: int | None = None
        approved_at: datetime | None = None
        approval = None
        if session is not None:
            approval = (
                await AgentApproval.objects.filter(
                    session=session,
                    status=AgentApproval.Status.APPROVED,
                    tool_name__endswith=action_name,
                    decided_at__gte=timezone.now() - APPROVAL_WINDOW,
                )
                .order_by("-decided_at")
                .afirst()
            )
            if approval is not None:
                approved_by_id = approval.decided_by_id
                approved_at = approval.decided_at
        await AgentUiAction.objects.acreate(
            call_id=call_id,
            session=session,
            user_id=session.user_id if session is not None else None,
            action=action_name,
            # 脱敏后的参数进库（与快照同口径），指纹按原始参数算（见 arguments_hash_of）。
            arguments=sanitize_arguments(arguments),
            arguments_hash=arguments_hash_of(arguments),
            risk=risk,
            approved_by_id=approved_by_id,
            approved_at=approved_at,
            approval=approval,
            decision=DECISION_APPROVED if approval is not None else "",
            decided_at=approved_at,
            expires_at=timezone.now() + RECEIPT_TTL,
            batch_id=(batch_id or "")[:64],
            delivered=delivered,
            outcome=OUTCOME_UNKNOWN,
        )
    except (DatabaseError, ValueError):
        logger.warning(
            "UI 动作审计落库失败（下发不受影响，只是少了这一行台账）: call_id=%s action=%s",
            call_id,
            action_name,
            exc_info=True,
        )
        return False
    return True


async def record_denial(
    *,
    tool_name: str,
    tool_args: dict[str, Any] | None,
    session_id: str | None,
    approval_id: str = "",
    reason: str = "",
    decision: str = DECISION_DENIED,
) -> bool:
    """审批**未通过**时落一行；返回本次是否新落了一行（重复拒绝返回 ``False``）。

    这个函数会被**所有**工具的拒绝路径调用（``mcp_server/tool_approval_gate.py`` 的
    ``if not approved:`` 分支，每个高危工具每次被拒都走一次），所以它必须又静默又便宜：

    - 工具名剥掉 ``mcp__fachuan__`` 前缀后去 :data:`~.manifest.UI_ACTIONS` 里查，
      **不在清单里 / 风险档不是 confirm/guarded → 直接返回 False**（不查库、不建行）。
      台账收的是「高危动作」，把每个被策略拒掉的普通工具都记进来只会让真事沉底。
    - 幂等靠 ``get_or_create(call_id=...)``：同一张卡重试（前端重发、后端重试）只会
      有一行。``call_id = "approval:{approval_id}"`` 把「哪张卡被拒」写进了主键；
      没有 approval_id（策略拒绝 / 多栏并答这类不建卡的路径）时退回随机 id。

    ``decision`` 默认 ``denied``，保留参数是为了让「超时未响应」这类系统判定也能
    复用同一条落行路径（值由调用方给，本函数不猜）。

    Returns:
        是否**新落**了一行。``False`` 有三种来源：不在清单/风险档不符、重复拒绝、
        写库失败。调用方不看返回值——审批判定与台账是两件事。
    """
    short_name = _short_action_name(tool_name)
    action = _ACTION_BY_NAME.get(short_name)
    if action is None or action.risk not in AUDITED_RISKS:
        return False

    # 延迟 import：本模块要能在无 Django settings 的进程里被 import（见模块 docstring）。
    from django.db import DatabaseError
    from django.utils import timezone

    from ...models import AgentApproval, AgentSession, AgentUiAction
    from ..session_service import _as_uuid

    args = tool_args or {}
    call_id = f"approval:{approval_id}" if approval_id else f"denial:{uuid.uuid4().hex[:24]}"
    try:
        session = None
        normalized = _as_uuid(session_id) if session_id else None
        if normalized is not None:
            session = await AgentSession.objects.filter(session_id=normalized).afirst()
        approval = None
        approval_uuid = _as_uuid(approval_id) if approval_id else None
        if approval_uuid is not None:
            approval = await AgentApproval.objects.filter(approval_id=approval_uuid).afirst()
        _, created = await AgentUiAction.objects.aget_or_create(
            # 主键长度上限 64：``approval:`` + 32 位 hex = 41，够用；截断只为兜住
            # 调用方传进来的异常 id，不让一个脏参数把整条落行搞没。
            call_id=call_id[:64],
            defaults={
                "session": session,
                "user_id": session.user_id if session is not None else None,
                "action": action.name,
                "arguments": sanitize_arguments(args),
                "arguments_hash": arguments_hash_of(args),
                "risk": action.risk,
                "approval": approval,
                "decision": decision,
                "decision_note": (reason or "")[:NOTE_MAX],
                "decided_at": timezone.now(),
                "batch_id": "",
                # 没执行过：页面没收到任何东西，回执自然也不会有。
                "delivered": False,
                # ``outcome`` 跟着 ``decision`` 走：两者都是「从未执行」，差别只在
                # 「谁判的」（人拒绝 / 系统超时）。不同步就会出现「决定说超时、结果说被拒」
                # 这种自相矛盾的行，读表的人只会以为数据坏了。
                "outcome": OUTCOME_DENIED if decision == DECISION_DENIED else OUTCOME_EXPIRED,
            },
        )
    except (DatabaseError, ValueError):
        logger.warning(
            "UI 动作拒绝留痕失败（审批判定不受影响，只是少了这一行台账）: tool=%s approval=%s",
            short_name,
            approval_id or "-",
            exc_info=True,
        )
        return False
    return created


async def apply_receipt(call_id: str, *, outcome: str, code: str, location: str) -> bool:
    """把前端回执写到对应那一行上；返回本次是否**真的**改写了那一行。

    **幂等与终态不可变都靠条件 UPDATE**：
    ``filter(call_id=..., outcome="unknown", expires_at 未过).aupdate(...)``。前端会重试
    （网络抖动 / 用户刷新），两次 POST 可能落在两个 worker 上；「先读后写」中间的窗口
    会让后到的重放覆盖第一份真实结果（第一次 ``ok``、重放 ``aborted``）——那等于让台账
    记下一次从未发生的执行。交给数据库做比较并写入，就不需要那把锁；顺带白送
    「已在终态的行永不改写」这条（条件里就带着 ``outcome="unknown"``）。

    **窗口外的回执**：那一行仍是 ``unknown`` 且 ``expires_at`` 已过 → 再执行一次条件
    UPDATE，把它落成 :data:`OUTCOME_EXPIRED`，并把这份回执的真实结局写进
    ``decision_note``（「页面后来说它成功了，但已经晚于窗口」本身就是审计要留的事实）。
    **绝不**据此把结局改写成 ``ok``：过期之后我们已在别处按「没成功」处理过。

    Returns:
        是否**真的改写了那一行**。迟到回执也返回 ``True``——它确实写进去了，
        只不过写进去的是 ``expired``，而不是回执声称的那个结局。

    ``error_code`` 只在 ``outcome="error"`` 时保留：别的结局带着 code，读表的人会把
    「中止」误读成路由故障。
    """
    # 延迟 import：理由见模块 docstring。
    from django.db import DatabaseError
    from django.db.models import Q
    from django.utils import timezone

    from ...models import AgentUiAction

    now = timezone.now()
    try:
        updated = (
            await AgentUiAction.objects.filter(call_id=call_id, outcome=OUTCOME_UNKNOWN)
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gte=now))
            .aupdate(
                delivered=True,
                outcome=outcome,
                error_code=(code or "")[:CODE_MAX] if outcome == "error" else "",
                observed_location=(location or "")[:LOCATION_MAX],
            )
        )
        if updated:
            return True
        # 没命中：要么已经在终态（永不改写），要么这一行还停在 unknown 但窗口过了。
        expired = await AgentUiAction.objects.filter(
            call_id=call_id,
            outcome=OUTCOME_UNKNOWN,
            expires_at__lt=now,
        ).aupdate(
            outcome=OUTCOME_EXPIRED,
            # 两句话都要在：前一句说「为什么没算数」，后一句说「页面到底回报了什么」。
            decision_note=f"晚于回执窗口到达；晚到回执：{outcome}"[:NOTE_MAX],
        )
    except (DatabaseError, ValueError):
        logger.warning(
            "UI 动作回执落库失败（回执通道不受影响，只是台账仍显示 unknown）: call_id=%s",
            call_id,
            exc_info=True,
        )
        return False
    return bool(expired)


async def apply_verification(call_id: str, *, verified: bool | None, note: str = "") -> bool:
    """写入服务端核实结论；返回是否真的改写了一行。

    只在 ``verified is None`` 时更新，理由与 :func:`apply_receipt` 同一条：核实结论一旦
    写下就是终态。页面回执可能重试、核实也可能被后来的调度再触发一次，让后到的
    「核不了」把先前的「核过了真成功」冲掉，等于把最有力的那条证据抹掉。

    ``verified=None``（无法核实）是一份**合法结论**而不是「没结论」：它同样要落
    ``verify_note``，否则事后只看到一个空值，分不清「没核实过」与「核了但核不了」。
    """
    # 延迟 import：理由见模块 docstring。
    from django.db import DatabaseError

    from ...models import AgentUiAction

    try:
        updated = await AgentUiAction.objects.filter(call_id=call_id, verified__isnull=True).aupdate(
            verified=verified,
            verify_note=(note or "")[:NOTE_MAX],
        )
    except (DatabaseError, ValueError):
        logger.warning("UI 动作核实结论落库失败（不影响下发结果）: call_id=%s", call_id, exc_info=True)
        return False
    return bool(updated)


async def list_recent_for_user(
    user: Any,
    *,
    limit: int = 50,
    action: str = "",
    outcome: str = "",
    risk: str = "",
) -> list[dict[str, Any]]:
    """当前用户自己的动作历史（新 → 旧）。

    **只按 ``user`` 过滤，不按会话共享**：同一会话被转交给同事后，新负责人也不该看见
    前任按过哪些高危按钮——动作历史是「谁让 AI 干了什么」，换成别人看就成了另一件事。

    Args:
        limit: 条数，clamp 到 1~:data:`LIST_MAX_LIMIT`（传 0 或负数按 1 处理）。
        action / outcome / risk: 精确匹配的过滤条件，**空串 = 不过滤**。三个都做成
            「空串即全部」而不是 ``None``：查询参数在 HTTP 层天然是字符串，让 None 与
            "" 表示同一件事只会在两端各写一个分支。

    Returns:
        每项 ``{session_id, action, risk, outcome, decision, decided_at, verified,
        verify_note, batch_id, approved_by_name, created_at, observed_location}``。
        时间字段是 ISO 8601 字符串（前端直接 ``new Date()``），为空时给空串；
        没有审批关联时 ``approved_by_name`` 为空串，``verified`` 保持 ``None``
        （「无法核实」与「没核实过」在列表里同形，细节看 ``verify_note``）。
    """
    # 延迟 import：理由见模块 docstring。
    from django.db import DatabaseError

    from ...models import AgentUiAction

    bounded = max(1, min(int(limit), LIST_MAX_LIMIT))
    filters: dict[str, str] = {}
    if action:
        filters["action"] = action
    if outcome:
        filters["outcome"] = outcome
    if risk:
        filters["risk"] = risk
    try:
        rows = [
            row
            async for row in AgentUiAction.objects.filter(user=user, **filters)
            .select_related("session", "approved_by")
            .order_by("-created_at")[:bounded]
        ]
    except (DatabaseError, ValueError):
        logger.warning("查询 UI 动作历史失败 user=%s", getattr(user, "pk", None), exc_info=True)
        return []
    return [
        {
            "session_id": str(row.session.session_id) if row.session is not None else "",
            "action": row.action,
            "risk": row.risk,
            "outcome": row.outcome,
            "decision": row.decision,
            "decided_at": row.decided_at.isoformat() if row.decided_at is not None else "",
            "verified": row.verified,
            "verify_note": row.verify_note,
            "batch_id": row.batch_id,
            # ``Lawyer.__str__`` = real_name or username，台账里要人能认出的名字。
            "approved_by_name": str(row.approved_by) if row.approved_by is not None else "",
            "created_at": row.created_at.isoformat(),
            "observed_location": row.observed_location,
        }
        for row in rows
    ]
