"""风险分级 —— 工具名 + 参数 + MCP 注解三层判定（审批的「要不要拦」权威表）。"""

from __future__ import annotations

from typing import Any

from django.db import models

from ...backends.toolface import tool_prefix
from .annotations import load_tool_annotations

#: 业务 MCP 工具的全名前缀（``mcp__fachuan__``）。审批链的匹配口径就建立在这个
#: 前缀上——改名会让工具照旧可调但**不再经过人工闸门**（静默失效），
#: 所以它不允许在各处手写。
MCP_TOOL_PREFIX = tool_prefix()

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
    # ``rewrite_``：2026-11 审计补入——``rewrite_folder_file`` 是**唯一会在主路径上
    # 真正改律师文件**的工具，原先因为它只命中 WRITE_PREFIXES 而被判 MEDIUM（免审批、
    # 不落 AgentApproval），等于最危险的那个反而无人闸门。
    "rewrite_",
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


def short_tool_name(tool_name: str) -> str:
    """去掉 MCP 前缀取短名（``mcp__fachuan__delete_case`` → ``delete_case``）。

    前缀取 :data:`MCP_TOOL_PREFIX`（= ``toolface.tool_prefix()``），不用硬编码
    字面量；未带前缀的短名（``delete_case``）退回按 ``"__"`` 切尾，
    与 ``approval-gate.ts`` 的 ``shortName`` 同义。没有容错分支的话，
    ``mcp__skill__xxx`` 这类别的 server 的工具会被当成 ``mcp__skill__xxx`` 全名，
    判定直接落空成「低风险」。
    """
    if tool_name.startswith(MCP_TOOL_PREFIX):
        return tool_name[len(MCP_TOOL_PREFIX) :]
    return tool_name.rsplit("__", 1)[-1]


def _classify_by_name(tool_name: str, tool_args: dict[str, Any] | None) -> RiskLevel:
    """纯名字 + 参数判定（兵底；extension 侧 ``classifyByName`` 与它同序）。"""
    if any(pattern in tool_name for pattern in HARD_DENY_PATTERNS):
        return RiskLevel.CRITICAL
    if any(pattern in tool_name for pattern in CRITICAL_PATTERNS):
        return RiskLevel.CRITICAL
    if any(pattern in tool_name for pattern in DANGER_PATTERNS):
        return RiskLevel.HIGH
    short_name = short_tool_name(tool_name)
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


def is_high_risk(tool_name: str, tool_args: dict[str, Any] | None = None) -> bool:
    """是否必须人工审批（高 + 紧急）。保留此函数作为「要不要拦」的单一入口。"""
    return classify_risk(tool_name, tool_args) in (RiskLevel.HIGH, RiskLevel.CRITICAL)


def needs_second_confirmation(level: RiskLevel) -> bool:
    """是否要求用户在审批弹窗里再确认一次（紧急级）。"""
    return level == RiskLevel.CRITICAL


def approval_timeout(level: RiskLevel) -> float:
    """按等级给等待上限：紧急级给更长时间让用户想清楚。"""
    return CRITICAL_TIMEOUT if level == RiskLevel.CRITICAL else DEFAULT_TIMEOUT
