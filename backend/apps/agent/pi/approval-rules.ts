/**
 * 审批分级的**纯规则层**：工具名 + 参数 + MCP annotations → 风险等级。
 *
 * ## 为什么单独一个模块
 *
 * 这些表与判定原先内联在 `approval-gate.ts` 里，而 `approval-gate.ts` 依赖 pi 的
 * `ExtensionAPI`——于是它们**从未被真正执行过**：此前的「跨语言一致性」检查只是
 * 用正则从 TS 源码里抠出数组字面量比文本（`tests/ci/unit/agent/
 * test_agent_risk_tiers.py` 的 `_ts_list`）。文本相等不等于判定相等，注解缺失与
 * 短名归一这两条语义就悄悄分叉过（见下面 `classifyByAnnotations` /
 * `shortName` 的注释）。
 *
 * 抽成**不 import 任何 pi 扩展 API** 的纯模块后，Node 能直接
 * `node --experimental-strip-types` 加载它，拿同一份向量
 * （`backend/tests/ci/fixtures/approval_vectors.json`）逐条对账两侧的判定结果
 * （`scripts/check-approval-parity.mjs`）。
 *
 * ## 权威源是服务端
 *
 * `apps/agent/services/approval/risk.py` 是权威（extension 可被绕过，服务端另有
 * 二次兜底判定），本文件的五张表与函数语义必须与它**逐字同义**；发现分叉时
 * 以 Python 为准改这里，改完补一条向量。
 *
 * 本模块**只放纯函数与常量**：读文件、算分级、发 HTTP 的部分留在
 * `approval-gate.ts`。
 */

export type RiskLevel = "low" | "medium" | "high" | "critical";

/**
 * 业务 MCP 工具全名前缀，与 `apps/agent/backends/toolface/constants.py` 的
 * `tool_prefix()` 同源（TS 无法 import Python 常量，一致性由
 * `tests/ci/unit/agent/test_toolface.py` 扫文本守）。
 *
 * 这里只用于 `shortName` 归一：`mcp__fachuan__` 之后的部分才是工具短名。
 */
const MCP_TOOL_PREFIX = "mcp__fachuan__";

/**
 * 高风险工具判定模式（对**完整工具名**做子串匹配）。
 *
 * 对应 Python 的 `DANGER_PATTERNS`（名字不同是因为历史：TS 侧先叫
 * `HIGH_RISK_PATTERNS`，`_ts_list` 按这个名字扫）。
 * 覆盖：一切删除 / 对外发出递交上传 / 归档确认 / 审批动作本身 / 批量清空重置。
 *
 * - `rewrite_`：`rewrite_folder_file` 是**唯一会在主路径上真正改律师文件**的工具，
 *   2026-11 审计与 Python 侧同步升级（此前它只命中 WRITE_PREFIXES → MEDIUM）。
 * - `approve_`：`approve_workflow_step` 是工作流 gate 的人工确认动作本身，模型
 *   低危直调 = 替人批准自己发起的工作流。
 * - `execute_` / `trigger_` / `batch_`：外部副作用与批量写（法院递交立案 / OA
 *   立案 / 外部担保接口 / 批量建档案），2026-10-25 审计补入。
 *
 * 刻意不拦 `create_` / `update_`（业务写、服务层归属兜底）与 `export_` /
 * `download_`（无破坏性）。`sync_` 不进高危但已列入 `WRITE_PREFIXES`（中级留痕）。
 */
export const HIGH_RISK_PATTERNS: readonly string[] = [
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
];

/**
 * 紧急级：批量清空 / 重置 / delete_all。前端弹窗要求二次确认。
 * 与 Python 的 `CRITICAL_PATTERNS` 逐项一致。
 */
export const CRITICAL_PATTERNS: readonly string[] = [
  "clear_all",
  "reset_and_",
  "delete_all",
  "bulk_delete",
];

/**
 * 不可覆盖的硬拒绝层：命中即 `block`，与任何策略/注解无关，也不进审批。
 *
 * 这一层存在的理由：`clear_all` / `delete_all` / `bulk_delete` 这类
 * 「一次抹掉整个库」的操作，风险不是「参数对不对」而是「它根本就不该由模型
 * 自主发起」。硬拒绝比「升级到紧急审批」更诚实——后者只是多问一句。
 *
 * 与 Python 的 `HARD_DENY_PATTERNS` 逐项一致（parity 测试守）。
 */
export const HARD_DENY_PATTERNS: readonly string[] = [
  "clear_all",
  "reset_and_",
  "delete_all",
  "bulk_delete",
];

/**
 * 中级：常规写入，但参数里带金额/期限/状态字段时升级为需审批。
 * 只按工具名判高危会漏掉 `update_contract(amount=...)` 这类改金额的写操作。
 * 与 Python 的 `SENSITIVE_ARG_MARKERS` 逐项一致。
 */
export const SENSITIVE_ARG_MARKERS: readonly string[] = [
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
];

/**
 * 「业务写」前缀：本身不算高危（中级 = 静默放行 + 审计留痕），但参数带敏感
 * 字段时升高危。匹配对象是**短名**的开头。
 *
 * 与 Python 的 `WRITE_PREFIXES` 逐项一致，含三类历史补丁：
 * 2026-10-25 一轮（`generate_`/`save_`/`move_`/`sync_`/`start_`/`retry_`/
 * `assign_`/`learn_`）、二轮（改名/重排/绑定/开关/取消/产出文件类 18 个）、
 * 晨间审计十九轮（`convert_`/`analyze_`/`parse_document`——它们 POST 但真写）
 * 与记忆写入（`remember`/`restore_memory`，删除侧走 `forget_` 已入 DANGER）。
 */
export const WRITE_PREFIXES: readonly string[] = [
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
  "ensure_",
  "bind_",
  "rename_",
  "reorder_",
  "toggle_",
  "merge_",
  "complete_",
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
  "convert_",
  "analyze_",
  "parse_document",
  "remember",
  "restore_memory",
  // 扫描件归档（archive_pdf_split_to_case_folder）：落盘到律师案卷目录，幂等且不覆盖，
  // 与 generate_/export_/bind_ 同档（MEDIUM）；不补就只能判 LOW = 无留痕。
  "archive_",
  // 回传件核对（verify_returned_document 落一条核对运行，POST /doc-verify/runs）：
  // 不碰律师文件且幂等（同基线+同字节返回同一行），与 generate_/archive_ 同档；
  // 不补只能判 LOW = 连留痕都没有（verify_citations 一并升到 MEDIUM，无审批摩擦）。
  "verify_",
  // 一句话起草（与 Python WRITE_PREFIXES 同步）：`draft_document` 会落盘并触发模型调用，
  // 但同名不覆盖、可随手删稿，属 generate_ 那一档；不补只能判 LOW = 连留痕都没有。
  "draft_",
];

/**
 * 短名归一（`mcp__fachuan__delete_case` → `delete_case`）。
 *
 * 口径与 Python `risk.short_tool_name` 一致：
 * 1. 带 `mcp__fachuan__` 前缀 → 只剥这一个前缀（`mcp__fachuan__<a>__<b>` → `a__b`）；
 * 2. 不带前缀 → 按最后一个 `__` 切尾（`mcp__<server>__delete_x` → `delete_x`，
 *    未带任何前缀的 `delete_case` 原样返回）。
 *
 * 曾经实现为「无条件按 `__` 切尾取最后一段」，于是 `mcp__fachuan__<a>__<b>` 在
 * TS 侧是 `b`、在 Python 侧是 `a__b`——短名不同，`WRITE_PREFIXES` 的匹配结果就
 * 可能不同（`mcp__fachuan__<子域>__update_case`：TS 判中级、Python 判低）。
 * 线上命名空间里没有这种形状，但**两套判定给出两套答案**本身就是缺陷，
 * 已按 Python 口径对齐（向量 `mcp__fachuan__<子域>__update_case` 钉住）。
 */
export function shortName(toolName: string): string {
  if (toolName.startsWith(MCP_TOOL_PREFIX)) {
    return toolName.slice(MCP_TOOL_PREFIX.length);
  }
  const separator = toolName.lastIndexOf("__");
  return separator === -1 ? toolName : toolName.slice(separator + 2);
}

/** 参数里是否带敏感字段（键名不区分大小写；与 Python `_has_sensitive_arg` 同义）。 */
function hasSensitiveArg(input?: Record<string, unknown>): boolean {
  if (!input) {
    return false;
  }
  return Object.keys(input).some((key) => {
    const lowered = key.toLowerCase();
    return SENSITIVE_ARG_MARKERS.some((marker) => lowered.includes(marker));
  });
}

/**
 * 纯名字 + 参数判定，判定顺序与 Python `_classify_by_name` 逐条同序：
 * 硬拒绝 → 紧急 → 高 → 写类+敏感参数 → 写类 → 低。
 *
 * 这是**兵底**：靠名字枚举工具不可维护，新增工具忘了登记就漏网，所以它只是
 * 第一层，annotations 才是补漏层（两层取较大者）。
 */
export function classifyByName(toolName: string, input?: Record<string, unknown>): RiskLevel {
  if (HARD_DENY_PATTERNS.some((pattern) => toolName.includes(pattern))) {
    return "critical";
  }
  if (CRITICAL_PATTERNS.some((pattern) => toolName.includes(pattern))) {
    return "critical";
  }
  if (HIGH_RISK_PATTERNS.some((pattern) => toolName.includes(pattern))) {
    return "high";
  }
  if (WRITE_PREFIXES.some((prefix) => shortName(toolName).startsWith(prefix))) {
    return hasSensitiveArg(input) ? "high" : "medium";
  }
  return "low";
}

/** 风险等级的序（取较大者的唯一依据）。 */
const RISK_ORDER: Record<RiskLevel, number> = {
  low: 0,
  medium: 1,
  high: 2,
  critical: 3,
};

/** 取两个风险等级中较高者（与 Python `_worse` 同义）。 */
export function worse(a: RiskLevel, b: RiskLevel): RiskLevel {
  return RISK_ORDER[a] >= RISK_ORDER[b] ? a : b;
}

/**
 * 从 MCP annotations 推导风险下限（与名字判定**取较大者**）。
 *
 * 为什么需要这层：法穿 415 个工具**全部**带 MCP annotations（实测 225 只读 /
 * 119 写 / 71 破坏性），但名字黑名单只覆盖其中一部分——`mortgage_default_calculate`、
 * `analyze_template` 这类不含常规写前缀的工具，光看名字会被判 LOW。
 *
 * 映射口径（保守，宁可多问不可少问）：
 * - `readOnlyHint === true`                          → 不动（名字黑名单若判高，仍取较大者）
 * - `destructiveHint === true` 或 `openWorldHint === true` → 至少 high
 * - 其余（非只读）                                     → 至少 medium（留痕，不打扰）
 * - **没有 annotations**（工具未声明 / 取不到 hints）  → **返回名字判定，不抬高**
 *
 * 最后一条是 2026-11 与 Python 对齐的修正：这里曾经是「没有 hints → 至少
 * medium」，于是同一个工具在 extension 侧是中级留痕、在服务端是低风险，两侧
 * 各说一套。注解是「补漏」而不是「兵底」，兵底是名字黑名单本身；保守升级只会
 * 把 158 个读类工具全变成「中级留痕」，把真实风险淹没在审计噪声里。
 */
export function classifyByAnnotations(
  annotations: Record<string, unknown> | undefined,
  byName: RiskLevel,
): RiskLevel {
  if (!annotations) {
    return byName;
  }
  if (annotations.readOnlyHint === true) {
    return byName;
  }
  if (annotations.destructiveHint === true || annotations.openWorldHint === true) {
    return worse(byName, "high");
  }
  return worse(byName, "medium");
}

/**
 * 硬拒绝判定：命中返回给模型看的原因，未命中返回 `null`。
 *
 * 与 Python `HARD_DENY_PATTERNS` 同表；`classify_risk` 侧命中同样是 critical，
 * 但那边会继续走审批（「问两遍」），这里直接 block（「根本不问」）。
 */
export function isHardDenied(toolName: string): string | null {
  const hit = HARD_DENY_PATTERNS.find((pattern) => toolName.includes(pattern));
  return hit ? `命中硬拒绝规则「${hit}」：批量清空类操作不允许由模型自主发起` : null;
}
