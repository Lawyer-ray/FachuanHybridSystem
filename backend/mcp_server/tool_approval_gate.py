"""服务端审批闸门（入口 B）—— MCP ``tools/call`` 在执行**之前**拦下高危工具。

## 为什么要在 MCP 服务端再拦一道

审批已有入口 A（pi 的 ``approval-gate.ts`` tool_call 钩子），但它只覆盖 pi：
dsh 与 openai-agents 直接连共享 MCP，**没有任何工具调用钩子**，高危工具在
这两个后端上等于完全无闸门。本中间件挂在 MCP 中间件链上，三种后端共用同一
套分级与同一张审批卡（去重键 = 会话 + 短工具名 + 参数，见
``apps/agent/services/approval/flow.py::_dedupe_key``）。

## 顺序：先判后调，绝不「先执行再问」

中间件是全请求级、可在 handler 前短路的官方扩展点（``mcp/server/runner.py``
的 ``_on_request``：``call_next`` 被短路时其返回值直通 JSON-RPC result）。
**命中拦截时绝不调用 ``call_next``**——``tool_tier_gate`` 是「先 ``call_next``
后过滤」（它只改返回值，天生如此），照抄那个顺序会把审批变成「工具已经执行、
再回一句『需要审批』」的假拦截。

## 开关（``FACHUAN_MCP_APPROVAL_GATE``）

| 值 | 行为 |
|:-|:-|
| 不设 / ``on`` | 正常拦截（默认） |
| ``dry`` | 只记日志不拦（灰度观察：先看会拦掉什么） |
| ``off`` | 完全透传（一键回滚） |

## 台账（grant）：批准后 10 分钟内「原样重试」直接放行

批准通过后写 ``agent:approval:grant:{身份}:{短工具名}:{sha256(参数)}``，
TTL 600s，**单次消费**（删掉才算命中）。原因：pi 的 MCP client timeout=200s，
而「审批等待 + 工具自身耗时」经常超过它——客户端超时后会重试同一调用；
没有台账就得让人再点一次同意（再弹一张卡、再等一轮），体验上等于不可用。

## fail-closed

分级、ORM、Redis 任何一步抛错都**不放行**：``logger.warning`` + 返回
``isError`` 的 ``CallToolResult``（仓规 ``mcp_server/README.md``：业务失败必须
走 ``isError``，禁止 ``return {"error": ...}`` 假装成功）。

## 已知边界

- 无 ``X-Fachuan-Session``（dsh / openai-agents / 手工 stdio）时 ``session_id``
  为 ``None``：审批单照建，但没有 SSE 通道可问，``request_approval`` 立即按
  拒绝返回。即「拦得住，但要等客户端补上会话头才能真批」——这是刻意的
  fail-closed，不能因为「批不了」就放行。
- 拿不到本地 ``user_id``（MCP 侧只有 Authorization 原文）：用户审批策略层不
  生效，按系统分级判定，严格性等同「该用户没有任何 allow 策略」。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from collections.abc import Mapping
from contextlib import suppress
from typing import Any

from asgiref.sync import sync_to_async
from django.db import close_old_connections
from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
from mcp.types import CallToolResult, TextContent

from apps.agent.services.approval import (
    RiskLevel,
    _annotation_table,
    classify_risk,
    prime_annotation_cache,
    request_approval,
)
from apps.agent.services.approval.flow import approval_dedupe_key
from apps.agent.services.approval.risk import short_tool_name

# 审批被拒也要留台账（``AgentUiAction``）：之前这条路库里零记录，「他明确拒绝过什么」
# 事后无法回答。audit 模块顶层只有 stdlib，导入它不会把 Django 拖进本文件。
from apps.agent.services.ui_action.audit import record_denial
from mcp_server.identity import current_session_id, request_authorization

logger = logging.getLogger(__name__)

#: 开关环境变量：``on``（默认）/ ``dry`` / ``off``。
GATE_ENV = "FACHUAN_MCP_APPROVAL_GATE"
MODE_ON = "on"
MODE_DRY = "dry"
MODE_OFF = "off"

#: 等待上限的环境变量与口径。
WAIT_ENV = "FACHUAN_TOOL_APPROVAL_WAIT"
DEFAULT_WAIT_SECONDS = 120.0
#: 上限 150s：pi 的 MCP client timeout 是 200s，超过就变成「客户端先超时、
#: 服务端还在等」，两头都拿不到结果。
MAX_WAIT_SECONDS = 150.0

#: 审批台账键前缀（与 ``agent:approval:decision:`` / ``:waiter:`` 同一命名空间）。
GRANT_KEY_PREFIX = "agent:approval:grant:"
#: 台账 TTL：批准后 10 分钟内的原样重试都算同一次调用。
GRANT_TTL = 600

#: 需要人工审批的等级（与 ``approval.flow.request_approval`` 的免审批口径一致：
#: LOW/MEDIUM 直接执行，MEDIUM 由服务端留审计标记）。
BLOCKING_LEVELS: frozenset[RiskLevel] = frozenset({RiskLevel.HIGH, RiskLevel.CRITICAL})

#: stdio 模式没有请求头可用，用进程常量区分（每进程一份 MCP，台账本就互不可见）。
_PROCESS_IDENT = f"stdio-{uuid.uuid4().hex[:12]}"

#: 启动时预生成的「短工具名 → MCP 注解」快照。
#: 为什么预生成：``classify_risk`` 不传 ``annotations`` 时会去懒加载整张注解表
#: （``approval/annotations.py``）；在事件循环里那次懒加载要起线程 + ``join(10)``，
#: 一旦卡住就把整个共享 MCP 的事件循环钉 10 秒。启动时（无事件循环）读一次，
#: 顺带把审批内核自己的注解缓存也预热掉——``request_approval`` 内部还会再
#: 调一次 ``classify_risk``，共用同一份缓存。
_TOOL_ANNOTATIONS: dict[str, dict[str, Any] | None] = {}


def gate_mode() -> str:
    """当前闸门模式（默认 ``on``；非法值按 ``on`` 处理——安全侧默认）。"""
    raw = (os.environ.get(GATE_ENV, MODE_ON) or "").strip().lower()
    if raw in (MODE_OFF, "0", "false", "no"):
        return MODE_OFF
    if raw == MODE_DRY:
        return MODE_DRY
    if raw in (MODE_ON, "1", "true", "yes", ""):
        return MODE_ON
    logger.warning("非法 %s=%r，按 %s 处理（安全侧默认）", GATE_ENV, raw, MODE_ON)
    return MODE_ON


def wait_seconds() -> float:
    """审批等待上限：``min(FACHUAN_TOOL_APPROVAL_WAIT 或 120, 150)``。

    非法/非正数回退默认值并 WARNING：等待上限被写成 ``abc`` 时静默取 0 会让
    每次都「秒超时按拒绝」，看起来像审批坏了。
    """
    raw = (os.environ.get(WAIT_ENV, "") or "").strip()
    if not raw:
        return DEFAULT_WAIT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        logger.warning("非法 %s=%r，按默认 %ss 等待", WAIT_ENV, raw, DEFAULT_WAIT_SECONDS)
        return DEFAULT_WAIT_SECONDS
    if value <= 0:
        logger.warning("%s=%r 不是正数，按默认 %ss 等待", WAIT_ENV, raw, DEFAULT_WAIT_SECONDS)
        return DEFAULT_WAIT_SECONDS
    return min(value, MAX_WAIT_SECONDS)


def _annotations_from_live_server(server: Any) -> dict[str, dict[str, Any] | None]:
    """从**活着的** ``MCPServer`` 同步读注解表（MCP 进程内唯一可靠的读法）。

    为什么不能走审批内核的 ``_annotation_table()``：它内部调
    ``mcp.list_tools()``（async，依赖请求上下文），在启动期调用会抛错并缓存
    空表——线上表现就是启动日志「注解 0 条」，分级退回纯名字判定。而
    ``server._tool_manager.list_tools()`` 是同步纯内存读取，实测 434 个工具
    全部带 annotations（2026-11-25 重测）。
    """
    manager = getattr(server, "_tool_manager", None)
    if manager is None or not hasattr(manager, "list_tools"):
        return {}
    table: dict[str, dict[str, Any] | None] = {}
    for tool in manager.list_tools():
        hints = getattr(tool, "annotations", None)
        name = getattr(tool, "name", "")
        if not name:
            continue
        table[name] = (
            None
            if hints is None
            else {
                "read_only_hint": getattr(hints, "read_only_hint", None),
                "destructive_hint": getattr(hints, "destructive_hint", None),
                "open_world_hint": getattr(hints, "open_world_hint", None),
            }
        )
    return table


def prime_tool_annotations(server: Any = None) -> int:
    """预生成 name→annotations 快照并**同时预热审批内核缓存**，返回工具数。

    优先从活 server 同步读（见 :func:`_annotations_from_live_server`）；拿不到时
    退回审批内核的老路径（Django 进程内 / 测试场景）。两条路径都失败时返回 0
    ——分级退回纯名字判定，仍然只更严不更松。
    """
    table: dict[str, dict[str, Any] | None] = {}
    if server is not None:
        try:
            table = _annotations_from_live_server(server)
        except Exception:
            logger.warning("从 MCP 工具表读注解失败，改用审批内核路径", exc_info=True)
    if not table:
        table = _annotation_table()
    _TOOL_ANNOTATIONS.clear()
    _TOOL_ANNOTATIONS.update(table)
    # 预热内核缓存：``request_approval`` 内部还会再调一次 ``classify_risk``，
    # 它也读注解；不预热的话它会在事件循环里再走一次会失败的懒加载。
    try:
        prime_annotation_cache(table)
    except Exception:
        logger.warning("预热审批内核注解缓存失败（分级将退回名字判定）", exc_info=True)
    return len(_TOOL_ANNOTATIONS)


def annotations_for(tool_name: str) -> dict[str, Any] | None:
    """取快照里的 MCP 注解（未声明/快照为空 → ``None``，退回纯名字判定）。"""
    return _TOOL_ANNOTATIONS.get(short_tool_name(tool_name))


def identity_fingerprint() -> str:
    """调用方身份指纹（台账按人隔离：A 批准过不能让 B 直接过）。

    HTTP 模式用 ``sha256(Authorization)``：``identity._is_valid_bearer`` 只校验
    ``Bearer `` 前缀，头原文才是真身份；拿前缀/长度当键会让全所律师共享台账。
    stdio 模式（无请求头）退回进程常量。
    """
    raw = request_authorization.get().strip()
    if not raw:
        return _PROCESS_IDENT
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def grant_key(tool_name: str, tool_args: dict[str, Any] | None = None) -> str:
    """审批台账键：``agent:approval:grant:{身份}:{短工具名}:{参数哈希}``。

    参数进键是必须的：只按工具名记台账等于「批准了删 A 案，B 案也能删」。
    """
    args_hash = hashlib.sha256(
        json.dumps(tool_args or {}, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:32]
    return f"{GRANT_KEY_PREFIX}{identity_fingerprint()}:{short_tool_name(tool_name)}:{args_hash}"


def _consume_grant(key: str) -> bool:
    """单次消费台账：只有**真的删掉了**键才算命中。

    用删除而不是「先 get 再 delete」：并发两个重试同时 get 都会命中，一次审批
    放行两次调用。Redis 的 ``DEL`` 是原子的，返回值即「键原本存在」，天然只放
    一个过去。
    """
    from django.core.cache import cache

    getdel = getattr(cache, "getdel", None)
    if callable(getdel):
        return bool(getdel(key))
    return bool(cache.delete(key))


def _store_grant(key: str, approval_id: str) -> None:
    """批准后写台账（值是 approval_id，出事时能对回审批单）。"""
    from django.core.cache import cache

    cache.set(key, approval_id, GRANT_TTL)


async def _recycle_db_connections() -> None:
    """进出各回收一次 DB 连接（同 ``mcp_server/server.py::_recycle_db_connections``）。

    ``request_approval`` 的 ORM（``afirst`` / ``acreate`` / ``asave``）经 asgiref 的
    thread_sensitive 单线程执行器跑，所以 ``close_old_connections`` 也必须投到
    **同一个**线程；直接在事件循环线程同步调用只会关掉循环线程自己的连接
    （通常 0 条），遮不住「PG 重启后共享 MCP 持续 OperationalError 直到重启」。
    """
    await sync_to_async(close_old_connections, thread_sensitive=True)()


def _parse_tool_call(params: Mapping[str, Any] | None) -> tuple[str, dict[str, Any]]:
    """从**未校验**的 wire params 里取 ``(name, arguments)``。

    中间件跑在 params 校验之前，所以这里必须是防御性解析：形状不对就返回空
    名字，交给 handler 自己报 INVALID_PARAMS（闸门不能把参数错误变成审批错误）。
    """
    if not isinstance(params, Mapping):
        return "", {}
    raw_name = params.get("name")
    tool_name = raw_name.strip() if isinstance(raw_name, str) else ""
    raw_args = params.get("arguments")
    return tool_name, dict(raw_args) if isinstance(raw_args, Mapping) else {}


def _error_result(text: str) -> CallToolResult:
    """业务失败的唯一返回形态（``isError`` + 文本，禁止 ``{"error": ...}``）。"""
    return CallToolResult(content=[TextContent(type="text", text=text)], is_error=True)


def _denied_text(short_name: str, level: RiskLevel, approval_id: str, reason: str) -> str:
    """拒绝/超时的给模型文案：三段——**谁挡的**、**为什么**、**下一步该干什么**。

    只说一句「未执行」的代价：模型把它当成一次普通失败，原样重发同一个写动作——律师
    刚拒绝过，弹窗又被问一遍。所以段三必须同时给出「别原样重试」与两条可走的路
    （先问律师 / 换一条不经审批的只读路径）。批准后那一次重试仍然是正规的（台账放行），
    两件事分开说：批准前重试只会再等一张批过的卡。

    纯字符串函数：本函数不做任何 IO（单测在 ``test_ui_action_denied_text.py``）。
    """
    if approval_id:
        pending = (
            f"已发起人工审批 approval_id={approval_id}：不要重复调用——律师批准后原样重试一次即可直接放行；"
            "批准前不要原样重试同一动作，重复提交只会再等同一张审批卡。"
        )
    else:
        pending = "未生成可重试的审批单：不要重复调用，也不要原样重试同一动作（重试只会被再挡一次）。"
    return (
        f"工具 {short_name} 未执行（风险等级：{level.label}）：审批闸门在它执行前拦下了这次调用。"
        f"审批结论：{reason or '未获批准（律师拒绝或等待超时）'}。"
        f"{pending}"
        "若确需执行，先向律师确认，或换一条不经审批的只读路径。"
    )


async def _consume_db_grant(dedupe_key: str, *, approval_id: str = "") -> bool:
    """兑付/t 消耗一条数据库里的「已批准且未消费」记录。

    为什么用数据库而不是 Redis 台账：入口 A（后端钩子，如 pi 扩展 /
    openai-agents 的 guardrail）批准后写的是 ``AgentApproval`` 行，它不
    知道 MCP 进程的 Authorization 指纹——两个入口只能用**同一个 dedupe_key**
    在数据库里对接。这也天然做到了跨 worker 与单次消费：
    ``UPDATE ... WHERE consumed_at IS NULL`` 的影响行数只能有一个赢家。

    Args:
        dedupe_key: ``flow.approval_dedupe_key(...)`` 算出的键。
        approval_id: 给了就按 id 兑付（本闸门自己刚批完那张），否则按 dedupe_key 找。
    """
    await _recycle_db_connections()
    try:
        from django.db.models import Q
        from django.utils import timezone

        from apps.agent.models import AgentApproval

        now = timezone.now()
        qs = AgentApproval.objects.filter(
            status=AgentApproval.Status.APPROVED,
            consumed_at__isnull=True,
        ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        if approval_id:
            qs = qs.filter(approval_id=uuid.UUID(approval_id.replace("-", "")))
        else:
            qs = qs.filter(dedupe_key=dedupe_key)
        return await qs.aupdate(consumed_at=now) > 0
    except Exception:
        logger.warning("兑付数据库审批台账失败（按未兑付处理）", exc_info=True)
        return False
    finally:
        with suppress(Exception):
            await _recycle_db_connections()


async def _await_approval(tool_name: str, tool_args: dict[str, Any]) -> tuple[bool, str, str]:
    """发起并等待人工审批，返回 ``(approved, approval_id, reason)``。"""
    await _recycle_db_connections()
    try:
        cap = wait_seconds()
        return await request_approval(
            tool_name=tool_name,
            tool_args=tool_args,
            # MCP 侧只有 Authorization 原文，解不出本地 user_id → 用户策略层不生效
            # （严格性等同「该用户没有任何 allow 策略」），不因此放行。
            user_id=None,
            session_id=current_session_id() or None,
            timeout=cap,
            # **离线等待也必须压到同一个上限**：没人开着 SSE 时
            # ``request_approval`` 会走离线挂起（默认 7200s），而客户端工具超时
            # 只有 200s——工具调用会整整挂两小时，律师看到的只是一次超时失败。
            # 压到 cap 之后：调用按时返回「已发起审批」，律师晚点批仍然有效
            # （``decide_approval`` 允许补批并重置有效期），模型原样重试即可。
            offline_timeout=cap,
        )
    finally:
        # 收尾失败不覆盖主异常：连接会在下一次进闸门时再回收一次。
        with suppress(Exception):
            await _recycle_db_connections()


class ToolApprovalGateMiddleware:
    """服务端审批闸门（``(ctx, call_next) -> result``）。

    只拦 ``tools/call``，且**先判后调**：命中拦截时绝不 ``call_next``。
    """

    async def __call__(
        self,
        ctx: ServerRequestContext[Any, Any],
        call_next: CallNext,
    ) -> HandlerResult:
        mode = gate_mode()
        if mode == MODE_OFF or ctx.method != "tools/call":
            return await call_next(ctx)
        try:
            return await self._guarded(ctx, call_next, mode)
        except Exception as exc:
            # fail-closed：不回滚成放行。审批链路自身坏了绝不能变成「无人闸门」。
            logger.warning(
                "审批闸门异常，按 fail-closed 拒绝（工具未执行）: method=%s err=%r",
                ctx.method,
                exc,
                exc_info=True,
            )
            tool_name, _ = _parse_tool_call(ctx.params)
            return _error_result(
                f"审批闸门异常（{exc.__class__.__name__}），工具 {short_tool_name(tool_name) or '?'} 未执行"
                "（fail-closed：审批服务不可用期间一律拒绝）。请勿重复调用同一工具同一参数，待服务恢复后重试。"
            )

    async def _guarded(
        self,
        ctx: ServerRequestContext[Any, Any],
        call_next: CallNext,
        mode: str,
    ) -> HandlerResult:
        """分级 → 台账 → 审批 → 放行（拦截路径不碰 ``call_next``）。"""
        tool_name, tool_args = _parse_tool_call(ctx.params)
        if not tool_name:
            return await call_next(ctx)
        # 注解显式传入：不能用 classify_risk 内部懒加载（事件循环里要起线程 join 10s）。
        level = classify_risk(tool_name, tool_args, annotations=annotations_for(tool_name))
        if level not in BLOCKING_LEVELS:
            return await call_next(ctx)
        short_name = short_tool_name(tool_name)
        if mode == MODE_DRY:
            logger.warning("[dry] 审批闸门只记录不拦截: tool=%s level=%s", short_name, level.value)
            return await call_next(ctx)
        # 第一优先：数据库台账（入口 A 批准的卡在这里兑付，两个入口共用一张）。
        dedupe = approval_dedupe_key(
            session_id=current_session_id() or None,
            tool_name=tool_name,
            tool_args=tool_args,
        )
        if await _consume_db_grant(dedupe):
            logger.info("审批台账（DB）命中，直接放行: tool=%s", short_name)
            return await call_next(ctx)
        # 第二优先：本闸门自己发过的同一轮重试（Redis，含身份指纹）。
        key = grant_key(tool_name, tool_args)
        if _consume_grant(key):
            logger.info("审批台账（本轮重试）命中，直接放行: tool=%s", short_name)
            return await call_next(ctx)
        approved, approval_id, reason = await _await_approval(tool_name, tool_args)
        if not approved:
            logger.info(
                "审批未通过，拒绝执行: tool=%s level=%s approval=%s reason=%s",
                short_name,
                level.value,
                approval_id or "-",
                reason,
            )
            # 多写一行台账，**不改审批判定**：record_denial 自己判「是不是清单里的
            # confirm/guarded 动作」（不是就直接返回 False，不查库），且内部只 catch
            # DatabaseError/ValueError，写不成也不影响下面这个拒绝结果。
            await record_denial(
                tool_name=tool_name,
                tool_args=tool_args,
                session_id=current_session_id() or None,
                approval_id=approval_id,
                reason=reason,
            )
            return _error_result(_denied_text(short_name, level, approval_id, reason))
        # 自己批下来的那张也要立即标消费：不然下一个人（或另一个 worker）
        # 会拿它当「已批准」重放。本轮的纯粹重试靠刚写的 Redis 台账。
        if approval_id:
            with suppress(Exception):
                await _consume_db_grant(dedupe, approval_id=approval_id)
        _store_grant(key, approval_id)
        logger.info("审批通过，放行: tool=%s approval=%s", short_name, approval_id or "-")
        return await call_next(ctx)


#: 进程级单例：幂等挂载的判据（与 ``tool_tier_gate`` 同一套做法）。
_TOOL_APPROVAL_GATE = ToolApprovalGateMiddleware()


def install_tool_approval_gate(server: Any) -> bool:
    """把本中间件 append 到 ``server.middleware``（幂等），并预生成注解快照。

    返回 ``True`` 表示本次真的挂上了，``False`` 表示已经在链上。必须在
    **事件循环启动之前**调用：注解快照读表是同步的，装到链上之后再读会去
    事件循环里做那件 10 秒 join 的事。
    """
    tool_count = prime_tool_annotations(server)
    chain = server.middleware
    if any(item is _TOOL_APPROVAL_GATE for item in chain):
        return False
    chain.append(_TOOL_APPROVAL_GATE)
    logger.info(
        "审批闸门已挂载: %s=%s（拦 %s 级；等待上限 %.0fs；注解 %d 条）",
        GATE_ENV,
        gate_mode(),
        "/".join(sorted(level.value for level in BLOCKING_LEVELS)),
        wait_seconds(),
        tool_count,
    )
    return True
