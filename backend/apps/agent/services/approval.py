"""审批服务 —— 高风险工具调用的人机确认。

## 链路

    pi tool_call 钩子
      → POST /api/v1/agent/approval/request   （extension 发问，同步阻塞）
      → 建 AgentApproval(pending) + 推 SSE approval_request 给前端
      → 用户点同意/拒绝 → POST /api/v1/agent/approval/{id}/decide
      → 返回 {"approved": bool} 给 extension
      → extension 放行或 block

## fail-closed

只有 ``approved`` 是放行。超时 / 用户离开 / 服务异常 / SSE 通道不可用，
一律按拒绝处理：

- 内存等待器超时 → 落库 ``timeout``，返回 False
- 无 SSE 通道（例如后台任务触发）→ 直接拒绝，不静默放行
- 工具名不在清单内 → 放行（非高危）

## 两层防护

1. extension 侧 ``HIGH_RISK_PATTERNS`` 命中即回调
2. 服务端 ``DANGER_PATTERNS`` 二次判定，即便 extension 被绕过也拦得住

两侧模式清单的一致性、以及清单对 ``mcp_server`` 实际工具注册表的覆盖，
由 ``tests/ci/unit/agent/test_agent_runtime.py`` 守护。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any

from asgiref.sync import sync_to_async
from django.db import models
from django.utils import timezone

from ..models import AgentApproval, AgentSession
from .event_bus import redis_cache_enabled

logger = logging.getLogger(__name__)

#: 高危工具判定模式（对完整工具名做子串匹配；pi 侧形如 ``mcp__fachuan__delete_lawyer``）。
#: 模式从 mcp_server 实际注册表校准——旧清单 6 个名字里有 3 个（send_document /
#: file_lawsuit / submit_court_document）在 378 个工具中根本不存在，而 39 个
#: ``delete_*`` 只拦住 8 个：
#: - ``delete`` / ``remove_`` / ``destroy``：一切删除操作
#: - ``send_`` / ``submit_`` / ``upload_`` / ``file_``：对外发出、递交、上传（不可撤回）
#: - ``confirm_``：如 confirm_archive（OA 归档确认）
#: - ``approve_``：如 approve_workflow_step——工作流 gate 的**人工确认动作本身**。
#:   模型低危直调它 = 模型替人批准自己发起的工作流,gate 的 HUMAN-in-the-loop
#:   语义被绕空。定为高危后:模型发起 → 律师看到审批卡 → 人点同意 → 信号才发出,
#:   正好还原「等 human signal」的设计本意(2026-10-25 审计)。
#: - ``execute_`` / ``trigger_`` / ``batch_``：外部副作用与批量写(2026-10-25 审计
#:   补入)。此前 ``execute_court_filing``(向法院递交立案)、``trigger_oa_filing``
#:   (OA 立案提交)、``execute_guarantee``/``execute_preservation_quote``(外部担保
#:   接口)、``batch_create_cases``/``batch_create_clients``(批量建档案)全被判 LOW
#:   直接执行——「递交法院」本是本清单的立项目标场景。``trigger_case_import``/
#:   ``trigger_client_import`` 虽只是上传解析,但与 ``upload_`` 同级语义(文件已
#:   离开本系统控制),一并拦。
#: - ``clear_all`` / ``reset_and_``：批量清空 / 重置
#: 刻意**不**拦 ``create_`` / ``update_``（常规业务写由各域服务层归属校验兜底,
#: 逐笔审批会让 agent 不可用）与 ``export_`` / ``download_``（拉取导出,无破坏性）。
#: ``sync_`` 不进高危但已列入 WRITE_PREFIXES（中级留痕,见下）。
DANGER_PATTERNS: tuple[str, ...] = (
    "delete",
    "remove_",
    "destroy",
    "forget_",
    "send_",
    "submit_",
    "upload_",
    "file_",
    "confirm_",
    "approve_",
    "clear_all",
    "reset_and_",
    "execute_",
    "trigger_",
    "batch_",
)

#: 已知无需审批的例外（按工具名后缀登记；新增例外必须写明理由）。
APPROVAL_EXEMPT_SUFFIXES: frozenset[str] = frozenset()

#: 紧急级：批量清空 / 重置 / 跨范围破坏。审批时必须二次确认（读一遍工具名再点）。
CRITICAL_PATTERNS: tuple[str, ...] = (
    "clear_all",
    "reset_and_",
    "delete_all",
    "bulk_delete",
)

#: 硬拒绝级：不允许由模型自主发起，extension 侧直接 ``block``（不进审批、
#: 不挂离线 pending）。与 ``CRITICAL_PATTERNS`` 的差别是——紧急级是"问两遍"，
#: 硬拒绝是"根本不问，直接不允许"。两者当前取值相同，但语义与后续策略
#: 演进方向不同（以后可能放宽紧急级阈值，但硬拒绝永不放宽）。
#: 与 ``approval-gate.ts`` 的 ``HARD_DENY_PATTERNS`` 逐项同步（parity 测试守）。
HARD_DENY_PATTERNS: tuple[str, ...] = (
    "clear_all",
    "reset_and_",
    "delete_all",
    "bulk_delete",
)

#: 中级：常规写入，但一旦参数里带了这些字段就升级为需审批。
#: 只按工具名判高危的漏洞：``update_contract`` 免审批，但它能改金额——
#: 律师有权改自己案件的金额，误改就是事故。参数级判定补上这个洞。
SENSITIVE_ARG_MARKERS: tuple[str, ...] = (
    "amount",
    "price",
    "fee",
    "money",
    "balance",
    "cost",
    "salary",
    "principal",
    "interest",
    "total",
    "deadline",
    "due_at",
    "due_date",
    "specified_date",
    "status",
    "stage",
    "state",
)

#: 「业务写」前缀：本身不算高危，但要拿参数做进一步判定（中级 = 静默放行 +
#: logger 留痕，无审批摩擦；带敏感参数则升高危）。
#: 2026-10-25 审计补入 8 个前缀——它们此前被判 LOW（连留痕都没有）：
#: ``generate_``（文书/归档产物落库）、``save_``（配置/排序/写盘）、``move_``、
#: ``sync_``（拉取入库）、``start_``（扫描/工作流启动）、``retry_``、
#: ``assign_``（案件指派）、``learn_``（规则学习）。读类（get_/list_ 等）不受影响。
WRITE_PREFIXES: tuple[str, ...] = (
    "create_",
    "update_",
    "set_",
    "patch_",
    "add_",
    "generate_",
    "save_",
    "move_",
    "sync_",
    "start_",
    "retry_",
    "assign_",
    "learn_",
    # 2026-10-25 二轮：AST 全扫 195 个实际发写请求的工具,50 个连中级留痕
    # 都没有（改名/重排/绑定/开关/取消/产出文件类）。中级=静默放行+审计
    # 日志,零摩擦,只补「不留痕」这个洞;纯计算类（calculate_/mortgage_/
    # check_/chat_/validate_/detect_/parse_/suggest_ 等）刻意保持 LOW。
    "ensure_",
    "bind_",
    "rename_",
    "reorder_",
    "toggle_",
    "merge_",
    "complete_",
    # 改写字：框选一段→按指令重新措辞，写回原文件（以修订痕迹）。
    # 不带写前缀就会被判 LOW=只读，模型改文件不经任何留痕，
    # 而它实际会改律师的合同文件——必须按写工具对待。
    "rewrite_",
    "cancel_",
    "export_",
    "extract_",
    "process_",
    "normalize_",
    "fill_",
    "scale_",
    "clear_",
    "reset_",
    "cleanup_",
    "unified_",
    # 2026-10-25 晨间审计(十九轮)：readOnlyHint↔写方法对账,三个 POST 但真写的
    # 工具此前判 LOW(零留痕+readOnlyHint):convert_document(每次转换落
    # DocConvertRecord+产物文件)、analyze_template(改模板状态/指纹+建
    # FieldMapping)、parse_document(存上传文件+建 DocumentParsingTask+派后台)。
    # parse_ 其余两员(parse_client_text/parse_reminders_from_text)纯内存解析,
    # 故用完整名精确圈定而非 parse_ 前缀。
    "convert_",
    "analyze_",
    "parse_document",
    # 2026-10-25 记忆：``remember`` / ``restore_memory`` 是写入但工具名不含
    # 常规写前缀，此前被判 LOW（连留痕都没有）。记忆会直接影响后续所有
    # 会话的输出，写入必须有审计痕迹。删除侧走 ``forget_``（已入 DANGER，
    # 需人工审批）——模型不能静默抹掉律师的记忆。
    "remember",
    "restore_memory",
)

DEFAULT_TIMEOUT = 300.0
#: 紧急级审批的等待上限（比常规长：这种操作值得让用户想清楚）。
CRITICAL_TIMEOUT = 900.0
#: 离线审批的等待上限：用户不在线时挂起等多久。默认 2 小时——
#: 律师常见的节奏是「挂个任务去开庭/开会，回来再处理」。
OFFLINE_TIMEOUT = 7200.0
#: 离线审批开关（``FACHUAN_APPROVAL_OFFLINE=0`` 可关闭，回到纯 fail-closed）。
OFFLINE_ENV = "FACHUAN_APPROVAL_OFFLINE"


def allow_offline_approval() -> bool:
    """无人在线时是否允许挂起等离线审批。

    默认**允许**：否则任务式入口（后台跑）永远用不了任何高危工具——
    这条路是无 SSE 连接的，fail-closed 直接把它判死。

    关闭后回到「无人可问即拒绝」，适合对安全性要求极端保守的部署。
    """
    import os

    raw = os.environ.get(OFFLINE_ENV, "").strip()
    if not raw:
        return True
    return raw not in ("0", "false", "False", "no")


class RiskLevel(models.TextChoices):
    """工具调用的风险等级。

    从「布尔」升级为分级的原因：``delete_case(case_id=1)`` 与
    ``clear_all_xxx()`` 走同一档审批，用户无法区分「删一条草稿」和
    「清空全库」，久了他就闭眼点同意——审批形同虚设。
    """

    LOW = "low", "低（直接执行）"
    MEDIUM = "medium", "中（静默执行并标记审计）"
    HIGH = "high", "高（需人工确认）"
    CRITICAL = "critical", "紧急（需二次确认）"


def _has_sensitive_arg(tool_args: dict[str, Any] | None) -> str:
    """参数里是否带敏感字段；返回命中的字段名（空串表示没有）。"""
    if not tool_args:
        return ""
    for key in tool_args:
        lowered = str(key).lower()
        if any(marker in lowered for marker in SENSITIVE_ARG_MARKERS):
            return str(key)
    return ""


def classify_risk(
    tool_name: str,
    tool_args: dict[str, Any] | None = None,
    annotations: dict[str, Any] | None = None,
) -> RiskLevel:
    """判定一次工具调用的风险等级。

    判定顺序（先命中的赢）：

    0. 豁免后缀 → 低（工具名以 ``_preview`` 这类结尾，永不需要审批）
    1. ``HARD_DENY_PATTERNS``（批量清空 / delete_all）→ 紧急（extension 侧硬拒）
    2. ``CRITICAL_PATTERNS``（批量清空 / 重置 / delete_all）→ 紧急
    3. ``DANGER_PATTERNS``（删除 / 外发 / 递交 / 上传 / 归档确认）→ 高
    4. 写类工具且参数带敏感字段（金额 / 期限 / 状态）→ 高
    5. 其他写类工具 → 中（静默执行，留审计标记）
    6. 其余（读类）→ 低
    7. **与 MCP ``annotations`` 取较大者**（声明优先，补名字黑名单的漏）

    Args:
        tool_name: 工具全名（``mcp__fachuan__delete_case``）或短名。
        tool_args: 工具入参，用于参数级敏感字段判定。
        annotations: MCP 工具注解（``read_only_hint`` / ``destructive_hint`` /
            ``open_world_hint``）。服务端从 ``mcp_server`` 注册表懒加载；
            显式传入时以传入值为准（测试用）。

    为什么需要 annotations 这层：法穿 415 个工具全部带注解
    （实测 225 只读 / 119 写 / 71 破坏性），但名字黑名单只覆盖其中一部分
    —— ``mortgage_default_calculate``、``analyze_template`` 这类不含常规写
    前缀的工具，光看名字会被判低。名字黑名单保留作兵底（它还能捕获
    注解写错的工具），两层取较大者。
    """
    if any(tool_name.endswith(suffix) for suffix in APPROVAL_EXEMPT_SUFFIXES):
        return RiskLevel.LOW
    by_name = _classify_by_name(tool_name, tool_args)
    hints = annotations if annotations is not None else load_tool_annotations(tool_name)
    if hints is None:
        # 取不到注解（未声明 / 注解表加载失败）→ **退回纯名字判定**。
        # 不能在这里保守升级：那会让 158 个读类工具全变成「中级留痕」，
        # 直接把 agent 的日常读操作淹没在审计噪声里（parity 测试会红灯）。
        # 注解是「补漏」而不是「兵底」，兵底是名字黑名单本身。
        return by_name
    return _worse(by_name, _classify_by_annotations(hints, by_name))


def _classify_by_name(tool_name: str, tool_args: dict[str, Any] | None) -> RiskLevel:
    """纯名字 + 参数判定（兵底；extension 侧 ``classifyByName`` 与它同序）。"""
    if any(pattern in tool_name for pattern in HARD_DENY_PATTERNS):
        return RiskLevel.CRITICAL
    if any(pattern in tool_name for pattern in CRITICAL_PATTERNS):
        return RiskLevel.CRITICAL
    if any(pattern in tool_name for pattern in DANGER_PATTERNS):
        return RiskLevel.HIGH
    short_name = tool_name.rsplit("__", 1)[-1]
    if short_name.startswith(WRITE_PREFIXES):
        if _has_sensitive_arg(tool_args):
            return RiskLevel.HIGH
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


_RISK_ORDER: dict[str, int] = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}


def _worse(a: RiskLevel, b: RiskLevel) -> RiskLevel:
    """取两个风险等级中较高者（extension 侧 ``worse`` 与它同义）。"""
    return a if _RISK_ORDER[a] >= _RISK_ORDER[b] else b


def _classify_by_annotations(
    annotations: dict[str, Any],
    by_name: RiskLevel,
) -> RiskLevel:
    """从 MCP 注解推导风险下限（与名字判定取较大者）。

    映射口径（保守，宁可多问不可少问）：

    - ``read_only_hint`` 为真 → 不动（读类就是读类）
    - ``destructive_hint`` 为真 → 至少高
    - 非只读且 ``open_world_hint`` 为真 → 至少高（会外发到公网/第三方）
    - 非只读（其余）→ 至少中（留痕，不打扰）

    调用方已保证 ``annotations`` 非空；显式声明为只读但名字命中黑名单时
    仍取名字判定（两层取较大者，防注解写错）。
    """
    if annotations.get("read_only_hint") is True or annotations.get("readOnlyHint") is True:
        return by_name
    destructive = annotations.get("destructive_hint") is True or annotations.get("destructiveHint") is True
    open_world = annotations.get("open_world_hint") is True or annotations.get("openWorldHint") is True
    if destructive or open_world:
        return _worse(by_name, RiskLevel.HIGH)
    return _worse(by_name, RiskLevel.MEDIUM)


def _list_mcp_tools(mcp: Any) -> list[Any]:
    """调 ``mcp.list_tools()``，兼容「已在事件循环内」与「循环外」两种上下文。

    为什么不自接 ``asyncio.run``：审批有可能在 async 路径下被调（
    ``request_approval`` 本身是 async），那时 ``asyncio.run`` 会抛
    ``RuntimeError: asyncio.run() cannot be called from a running event loop``。
    早期版本把这个异常当「注解读不到」静默降级，导致 158 个读类工具全被
    判成「中级留痕」——静默失败比报错难查得多。这里分三种情况处理。
    为什么只在无循环时用单独线程：``list_tools`` 是同步完成的内存读取
    （读已注册的工具表），不碰网络，开线程只是为了避免嵌套循环。
    """
    coro_factory = mcp.list_tools
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro_factory())
    # 已在事件循环内：交给独立线程跑一个新循环，避免嵌套。
    import threading

    result: list[Any] = []
    error: list[BaseException] = []

    def _runner() -> None:
        try:
            result.extend(asyncio.run(coro_factory()))
        except BaseException as exc:
            error.append(exc)

    thread = threading.Thread(target=_runner, name="mcp-annotation-loader", daemon=True)
    thread.start()
    thread.join(timeout=10)
    if thread.is_alive():
        raise TimeoutError("读取 MCP 工具表超时（10s）")
    if error:
        # 有意捕获 BaseException：_runner 跑在独立线程里，asyncio 取消（
        # CancelledError 自 Python 3.8 起继承 BaseException）与 KeyboardInterrupt
        # 若不在这里接住，异常会死在子线程中丢失，join 后的调用方就分不清
        # 「子线程正常返回」与「子线程被中断」——前者会让审批静默退回名字判定，
        # 后者应原样上抛。故此处保留宽捕获，只负责把异常透传给主线程。
        raise error[0]
    return result


#: 注解表缓存（模块级懒加载一次）。
#: 注意：这里**不用 ``lru_cache``**——它会在并发首次调用时把「加载中/失败的
#: 空表」一起记下来，导致同进程内先后调用拿到不一致结果（实测：第一个工具
#: 拿到注解、后续全 ``None``）。审批是安全路径，宁可多读一次也不能读出两套答案。
#: 本模块的读写在函数内经 ``global`` 完成，CodeQL 会误报「未使用」，不可删除。
_ANNOTATION_TABLE: dict[str, dict[str, Any] | None] | None = None


def _reset_annotation_cache() -> None:
    """清缓存（供测试与热加载用）。

    为什么需要公开一个重置口：``mcp_server`` 的工具注册表在某些测试场景下会
    被重新导入/重建，旧快照就陈旧了。生产路径不会调它。
    """
    global _ANNOTATION_TABLE
    _ANNOTATION_TABLE = None


def _annotation_table() -> dict[str, dict[str, Any] | None]:
    """工具短名 → MCP 注解字典（进程内懒加载一次，失败时返回空表）。

    ``mcp_server`` 是共享常驻进程，本进程（Django）导入它会多加载一份注册表。
    只在**首次需要时**读一次；加载失败不抛错——服务端二次判定退回纯名字
    黑名单，与改造前行为一致（不会因为注解表读不到就放行）。

    返回 ``None`` 表示该工具**没有声明**注解；空表（加载失败）与「全部未声明」
    由 ``load_tool_annotations`` 区分（空表时直接回 ``None``）。
    """
    global _ANNOTATION_TABLE
    if _ANNOTATION_TABLE is not None:
        return _ANNOTATION_TABLE
    try:
        from mcp_server.server import mcp

        tools = _list_mcp_tools(mcp)
    except Exception as exc:
        logger.warning("读取 MCP 工具注解失败，审批退回纯名字判定: %s", exc)
        _ANNOTATION_TABLE = {}
        return _ANNOTATION_TABLE
    table: dict[str, dict[str, Any] | None] = {}
    for tool in tools:
        hints = getattr(tool, "annotations", None)
        if hints is None:
            table[tool.name] = None
            continue
        table[tool.name] = {
            "read_only_hint": getattr(hints, "read_only_hint", None),
            "destructive_hint": getattr(hints, "destructive_hint", None),
            "open_world_hint": getattr(hints, "open_world_hint", None),
        }
    _ANNOTATION_TABLE = table
    return table


def load_tool_annotations(tool_name: str) -> dict[str, Any] | None:
    """按工具全名/短名取 MCP 注解（取不到返回 ``None``）。"""
    table = _annotation_table()
    if not table:
        return None
    short_name = tool_name.rsplit("__", 1)[-1]
    return table.get(short_name)


def is_high_risk(tool_name: str, tool_args: dict[str, Any] | None = None) -> bool:
    """是否必须人工审批（高 + 紧急）。保留此函数作为「要不要拦」的单一入口。"""
    return classify_risk(tool_name, tool_args) in (RiskLevel.HIGH, RiskLevel.CRITICAL)


def lookup_approval_policy(*, user_id: int | None, tool_name: str) -> str | None:
    """查用户对某工具的审批策略（P2-5）。

    Returns:
        "allow" / "deny" / None（无策略或 ask——走系统默认分级）。

    查询优先级：精确匹配 > 前缀匹配；同步函数（request_approval 内
    经 sync_to_async 调用）。
    """
    if user_id is None:
        return None
    from ..models import AgentApprovalPolicy

    # 精确匹配：全名（mcp__fachuan__delete_case）或短名（delete_case）都行
    short_name = tool_name.rsplit("__", 1)[-1]
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


def needs_second_confirmation(level: RiskLevel) -> bool:
    """是否要求用户在审批弹窗里再确认一次（紧急级）。"""
    return level == RiskLevel.CRITICAL


def approval_timeout(level: RiskLevel) -> float:
    """按等级给等待上限：紧急级给更长时间让用户想清楚。"""
    return CRITICAL_TIMEOUT if level == RiskLevel.CRITICAL else DEFAULT_TIMEOUT


DECISION_KEY_PREFIX = "agent:approval:decision:"
#: P2-4 waiter 心跳键前缀——存在 = 有 worker 在等；过期 = 等待者已死
WAITER_KEY_PREFIX = "agent:approval:waiter:"
DECISION_TTL = 600
DECISION_POLL_INTERVAL = 0.2


def _write_decision(approval_id: str, approved: bool) -> None:
    """把决定写入 Redis，供**其他 worker** 上的等待者读取。

    等待审批的 HTTP 请求和「用户点同意」的 HTTP 请求可能落在不同 worker，
    而 ``_ApprovalWaiter`` 是进程内的。没有这一步，跨 worker 时等待方永远
    等不到结果，只能超时走 fail-closed（表现为「审批了但工具没执行」）。
    """
    if not redis_cache_enabled():
        return
    from django.core.cache import cache

    try:
        cache.set(f"{DECISION_KEY_PREFIX}{approval_id}", "1" if approved else "0", DECISION_TTL)
    except Exception:
        # CLAUDE.md 标准:失败会让用户看到「审批了但工具没执行」的无法解释结果,
        # 必须高于 debug——跨 worker 决定丢失正是这一步要防的事故。
        logger.warning("写入审批决定失败(跨 worker 等待者将读不到结果): %s", approval_id, exc_info=True)


def _write_waiter_heartbeat(approval_id: str, timeout_seconds: float) -> None:
    """P2-4：写 waiter 心跳键（TTL = 等待超时 × 1.5，下限 60s）。键在 = 有人在等。"""
    if not redis_cache_enabled():
        return
    from django.core.cache import cache

    try:
        cache.set(
            f"{WAITER_KEY_PREFIX}{approval_id}",
            "alive",
            max(int(timeout_seconds * 1.5), 60),
        )
    except Exception:
        # 心跳写失败会让「无人在线挂起等离线审批」的判定失真,同上不低于 warning。
        logger.warning("写 waiter 心跳失败(离线审批挂起判定将失真): %s", approval_id, exc_info=True)


def _waiter_is_alive(approval_id: str) -> bool:
    """P2-4：waiter 心跳键是否存在（不存在 = 等待进程已死）。

    查不到/查失败时返回 True（保守认为活着）——宁可让前端少报一个
    「可能已失效」，也不要误报把仍然有效的审批标成失效。代价是 Redis 故障时
    waiter_dead 恒为 False，因此必须留日志（根 CLAUDE.md：用户可见的
    无法解释结果至少 warning）。
    """
    if not redis_cache_enabled():
        return True  # 无 Redis 时无法判定，保守认为活着
    from django.core.cache import cache

    try:
        return cache.get(f"{WAITER_KEY_PREFIX}{approval_id}") is not None
    except Exception:
        # Redis 抖动期间 waiter_dead 会恒为 False（审批卡片不提示失效），留痕便于对账。
        logger.warning("读取 waiter 心跳失败(waiter_dead 判定失真): %s", approval_id, exc_info=True)
        return True


def _clear_waiter_heartbeat(approval_id: str) -> None:
    """P2-4：等待结束（决定/超时），清除心跳键。"""
    if not redis_cache_enabled():
        return
    from django.core.cache import cache

    try:
        cache.delete(f"{WAITER_KEY_PREFIX}{approval_id}")
    except Exception:
        # 审批链路不得 debug 吞错（见 tests/ci/unit/agent/test_approval_log_levels.py）：
        # 心跳键残留会让离线挂起判定失真，属用户可见的无法解释结果。
        logger.warning("清除审批心跳键失败 approval_id=%s", approval_id, exc_info=True)


def _read_decision(approval_id: str) -> bool | None:
    """读取其他 worker 写入的决定；无则返回 ``None``。"""
    if not redis_cache_enabled():
        return None
    from django.core.cache import cache

    try:
        raw = cache.get(f"{DECISION_KEY_PREFIX}{approval_id}")
    except Exception:
        return None
    if raw is None:
        return None
    return str(raw) == "1"


def _clear_decision(approval_id: str) -> None:
    if not redis_cache_enabled():
        return
    from django.core.cache import cache

    try:
        cache.delete(f"{DECISION_KEY_PREFIX}{approval_id}")
    except Exception:
        logger.warning("清理审批决定键失败（键会按 TTL 自然过期）: %s", approval_id, exc_info=True)


class _ApprovalWaiter:
    """进程内等待器：把「前端点了什么」交回给阻塞的 HTTP 请求。

    只做进程内协调，**状态真相在数据库**。这样即便进程重启，
    历史审批仍可审计；只是进行中的等待会随进程消失（客户端得到超时 → 拒绝）。
    """

    def __init__(self) -> None:
        self._events: dict[str, asyncio.Event] = {}
        self._results: dict[str, bool] = {}
        self._lock = asyncio.Lock()

    async def register(self, approval_id: str) -> asyncio.Event:
        async with self._lock:
            event = asyncio.Event()
            self._events[approval_id] = event
            self._results[approval_id] = False
            return event

    async def resolve(self, approval_id: str, approved: bool) -> bool:
        """前端决定后调用；返回是否找到等待者。"""
        async with self._lock:
            event = self._events.get(approval_id)
            if event is None:
                return False
            self._results[approval_id] = approved
            event.set()
            return True

    async def take_result(self, approval_id: str) -> bool:
        async with self._lock:
            return self._results.get(approval_id, False)

    async def discard(self, approval_id: str) -> None:
        async with self._lock:
            self._events.pop(approval_id, None)
            self._results.pop(approval_id, None)


_waiter = _ApprovalWaiter()


@asynccontextmanager
async def _sse_channel(
    session_id: str | None,
) -> AsyncIterator[asyncio.Queue[dict[str, Any]] | None]:
    """登记 SSE 通道；无会话上下文时给出 ``None``（调用方按拒绝处理）。"""
    from .event_bus import get_bus

    if not session_id:
        yield None
        return
    queue = await get_bus().register(session_id)
    try:
        yield queue
    finally:
        await get_bus().unregister(session_id, queue)


def _approval_message(tool_name: str, level: RiskLevel) -> str:
    """给前端弹窗用的提示语（按等级区分措辞，避免一律「高风险」而失去区分度）。"""
    short = tool_name.rsplit("__", 1)[-1]
    if level == RiskLevel.CRITICAL:
        return f"即将执行批量破坏性操作：{short}。这会影响多条数据且不可撤回，请再次确认。"
    return f"即将执行不可撤回操作：{short}，请确认是否继续。"


async def request_approval(
    *,
    tool_name: str,
    tool_args: dict[str, Any] | None = None,
    user_id: int | None = None,
    session_id: str | None = None,
    reason: str = "",
    timeout: float | None = None,
    offline_timeout: float = OFFLINE_TIMEOUT,
) -> tuple[bool, str, str]:
    """发起一次审批并阻塞等待。

    分级判定取代原来的布尔判定：中级（常规写）静默放行但记审计标记，
    紧急级（批量清空）要求前端二次确认并给更长的等待时间。

    Args:
        timeout: 显式指定等待上限；``None`` 时按风险等级取（紧急级更长）。
        offline_timeout: 无人在线时挂起等离线决定的上限。

    Returns:
        ``(approved, approval_id)``。``approved`` 为 ``True`` 才放行。
    """
    approval_id = uuid.uuid4().hex

    level = classify_risk(tool_name, tool_args)
    if level in (RiskLevel.LOW, RiskLevel.MEDIUM):
        # 中级放行但要留痕：出事时能查到「agent 自己改过金额」
        if level == RiskLevel.MEDIUM:
            logger.info(
                "中级风险工具静默执行 tool=%s args=%s",
                tool_name,
                sorted((tool_args or {}).keys()),
            )
        return True, approval_id, "低/中风险，免审批放行"

    # ── P2-5 审批策略覆盖（用户偏好层）──
    # critical 不可被 allow 覆盖（硬红线）；high 可被 allow/deny 覆盖；
    # medium 可被 deny 覆盖（更严）；low 本来就不审批
    policy = await sync_to_async(
        lambda: lookup_approval_policy(user_id=user_id, tool_name=tool_name),
        thread_sensitive=True,
    )()
    if policy == "allow" and level == RiskLevel.HIGH:
        logger.info("策略允许（high→allow）tool=%s user=%s", tool_name, user_id)
        return True, "", "策略允许（用户配置 high 级免审批）"
    if policy == "deny" and level in (RiskLevel.HIGH, RiskLevel.MEDIUM):
        logger.info("策略拒绝 tool=%s user=%s", tool_name, user_id)
        return False, "", f"策略拒绝（用户配置 {level.value} 级禁止）"

    effective_timeout = timeout if timeout is not None else approval_timeout(level)

    session = None
    if session_id:
        try:
            session = await AgentSession.objects.filter(session_id=session_id).afirst()
        except Exception:
            # 审批记录将丢失会话关联(审计断链),不是可无感降级的失败。
            logger.warning("按 session_id 查会话失败(审批记录将缺会话关联): %s", session_id, exc_info=True)

    record = await AgentApproval.objects.acreate(
        approval_id=uuid.UUID(approval_id),
        session=session,
        tool_name=tool_name,
        tool_args=tool_args or {},
        reason=reason,
        risk_level=level.value,
    )

    # 先登记等待者、再 publish。反过来的话，若「用户决定」先于 register 到达
    # （自动审批 / 前端重试），resolve 找不到等待者只能落库 approved，等待方
    # 却等不到事件，最终超时分支会把已 approved 的记录覆盖成 timeout——
    # 用户点了同意、工具却被拒。
    delivered = 0
    has_remote = False
    event: asyncio.Event | None = None
    if session_id:
        event = await _waiter.register(approval_id)
        # P2-4 waiter 心跳：Redis 键带 TTL，键过期 = 等待进程已死
        _write_waiter_heartbeat(approval_id, effective_timeout)
        from .event_bus import get_bus

        bus = get_bus()
        # 订阅者可能在**别的 worker**（SSE 连接在 A，审批回调落在 B）。
        # 多 worker 下 publish 到 Redis 即可送达，此时本地 delivered 为 0
        # 但仍有远端订阅者，不能据此判为「无人可问」。
        has_remote = bool(await bus.has_subscribers(session_id)) or redis_cache_enabled()
        delivered = await bus.publish(
            session_id,
            {
                "type": "approval_request",
                "approval_id": approval_id,
                "tool_name": tool_name,
                "tool_args": tool_args or {},
                "risk_level": level.value,
                "needs_second_confirmation": needs_second_confirmation(level),
                "message": reason or _approval_message(tool_name, level),
            },
        )

    if event is not None and (delivered or has_remote):
        try:
            approved = await _wait_decision(approval_id, event, effective_timeout)
            record.status = AgentApproval.Status.APPROVED if approved else AgentApproval.Status.REJECTED
        except TimeoutError:
            record.status = AgentApproval.Status.TIMEOUT
            logger.info("审批超时，按拒绝处理: tool=%s approval=%s", tool_name, approval_id)
        finally:
            await _waiter.discard(approval_id)
            _clear_waiter_heartbeat(approval_id)
            _clear_decision(approval_id)
            record.decided_at = timezone.now()
            await record.asave(update_fields=["status", "decided_at"])
        reason_out = record.reason or ("用户同意" if record.is_granted else "用户拒绝或超时")
        return record.is_granted, approval_id, reason_out

    # 没有订阅者：无人可问。
    #
    # 原实现直接 rejected（fail-closed）。对「用户开着页面但断线」是对的，
    # 但它把「任务式后台运行」这条路彻底堵死了——后台跑本来就没有 SSE 连接，
    # 那意味着任务式入口永远用不了任何高危工具。
    #
    # 现在按「有没有人在线」分流：
    # - 有人在别的 worker 上连着（has_remote）却还是没送达 → 链路异常，仍拒绝；
    # - 完全没人在线且允许离线审批 → 保持 pending 挂起，等用户回来在会话里
    #   看到待审批卡片再决定（离线审批）。工具调用方仍在阻塞等待，
    #   所以等待上限用 offline_timeout。
    # - 完全没人在线且不允许离线审批 → 维持原 fail-closed 行为。
    offline_ok = allow_offline_approval() and not has_remote
    if event is not None and offline_ok:
        logger.info(
            "无人订阅，审批挂起等待离线决定 tool=%s approval=%s timeout=%s",
            tool_name,
            approval_id,
            offline_timeout,
        )
        try:
            approved = await _wait_decision(approval_id, event, offline_timeout)
            record.status = AgentApproval.Status.APPROVED if approved else AgentApproval.Status.REJECTED
        except TimeoutError:
            record.status = AgentApproval.Status.TIMEOUT
            logger.info("离线审批超时，按拒绝处理 tool=%s approval=%s", tool_name, approval_id)
        finally:
            await _waiter.discard(approval_id)
            _clear_waiter_heartbeat(approval_id)
            _clear_decision(approval_id)
            record.decided_at = timezone.now()
            await record.asave(update_fields=["status", "decided_at"])
        reason_out = record.reason or ("用户同意" if record.is_granted else "用户拒绝或超时")
        return record.is_granted, approval_id, reason_out

    if event is not None:
        await _waiter.discard(approval_id)
        _clear_waiter_heartbeat(approval_id)
    logger.warning("无 SSE 订阅者且不允许离线审批，按拒绝处理: tool=%s", tool_name)
    record.status = AgentApproval.Status.REJECTED
    record.decided_at = timezone.now()
    await record.asave(update_fields=["status", "decided_at"])
    return False, approval_id, record.reason or "无人在线且不允许离线审批，按拒绝处理"


async def _wait_decision(approval_id: str, event: asyncio.Event, timeout: float) -> bool:
    """等审批结果：本进程有人点就立即醒，否则轮询 Redis（跨 worker）。

    Returns:
        是否放行。

    Raises:
        TimeoutError: 超时未决。
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout

    while True:
        if event.is_set():
            return await _waiter.take_result(approval_id)

        remote = _read_decision(approval_id)
        if remote is not None:
            return remote

        remaining = deadline - loop.time()
        if remaining <= 0:
            raise TimeoutError

        try:
            await asyncio.wait_for(event.wait(), timeout=min(DECISION_POLL_INTERVAL, remaining))
        except TimeoutError:
            continue


async def decide_approval(
    approval_id: str,
    approved: bool,
    *,
    user_id: int | None = None,
    reason: str = "",
) -> bool:
    """前端提交决定。返回是否成功（找不到等待者时仍更新数据库）。

    ``reason`` 为拒绝理由（可空）：落库到 ``AgentApproval.reason``，并由
    ``request_approval`` 的等待方回传给 pi extension——模型据此换更安全的
    路径，而不是只收到一句干巴巴的「用户拒绝」。
    """
    normalized = approval_id.replace("-", "")
    found = await _waiter.resolve(approval_id, approved) or await _waiter.resolve(normalized, approved)
    # 唤醒可能在其他 worker 上的等待者
    _write_decision(approval_id, approved)
    _write_decision(normalized, approved)

    try:
        record = await AgentApproval.objects.filter(approval_id=uuid.UUID(normalized)).afirst()
    except (ValueError, AttributeError):
        record = None

    if record is not None and record.status == AgentApproval.Status.PENDING:
        record.status = AgentApproval.Status.APPROVED if approved else AgentApproval.Status.REJECTED
        record.decided_at = timezone.now()
        if user_id is not None:
            record.decided_by_id = user_id
        if reason.strip():
            record.reason = reason.strip()[:2000]
            await record.asave(update_fields=["status", "decided_at", "decided_by", "reason"])
        else:
            await record.asave(update_fields=["status", "decided_at", "decided_by"])

    return found or record is not None


async def get_approval_for_decision(approval_id: str) -> AgentApproval | None:
    """取审批记录（含会话预取）供归属判定；无效 id 返回 None。"""
    try:
        normalized = approval_id.replace("-", "")
        return await AgentApproval.objects.select_related("session").filter(approval_id=uuid.UUID(normalized)).afirst()
    except (ValueError, AttributeError):
        return None


async def list_approvals(*, user: Any, limit: int) -> list[AgentApproval]:
    """审批记录列表（审计用；非超级用户仅见自己会话的记录）。"""
    queryset = AgentApproval.objects.all()
    if user is not None and not getattr(user, "is_superuser", False):
        queryset = queryset.filter(session__user_id=user.pk)
    return [record async for record in queryset[: max(1, min(limit, 200))]]


async def list_pending_for_user(*, user_id: int | None) -> list[AgentApproval]:
    """某人所有**仍待处理**的审批（离线审批用：用户回来看到待审批卡片）。

    只查 pending：已决/超时的不需要再打扰用户。按创建时间正序，
    先来的先处理（避免用户在处理一堆旧请求时又漏掉更急的）。

    **懒清理僵尸 pending**：等待审批的进程内 waiter 死亡时（worker 重启 /
    崩溃），记录会永远停在 pending——没人把它转成 timeout（差距分析 B2-4）。
    这里在列表时把超过最长可能等待窗口（OFFLINE_TIMEOUT，挂起等离线
    审批的上限）的 pending 批量转成 timeout：

    - 不会误杀活等待：任何在等的 waiter（在线 300/900s 或离线 7200s）
      最长也就等到 OFFLINE_TIMEOUT，超过它必是僵尸；
    - fail-closed 语义不变：被转 timeout 的记录等同拒绝，工具未执行。
    """
    if user_id is None:
        return []
    zombie_deadline = timezone.now() - timedelta(seconds=OFFLINE_TIMEOUT)
    await AgentApproval.objects.filter(
        status=AgentApproval.Status.PENDING,
        session__user_id=user_id,
        created_at__lt=zombie_deadline,
    ).aupdate(status=AgentApproval.Status.TIMEOUT, decided_at=timezone.now())
    queryset = AgentApproval.objects.filter(
        status=AgentApproval.Status.PENDING,
        session__user_id=user_id,
    ).select_related("session")
    results = []
    async for record in queryset.order_by("created_at")[:100]:
        results.append(record)
    return results
