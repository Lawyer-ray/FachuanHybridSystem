/**
 * 法穿 SI Copilot — pi 审批网关 extension
 *
 * 挂载点：pi 的 `tool_call` 钩子（官方支持 mutate input 或 block execution）。
 *
 * 机制：模型要执行工具前，钩子把「工具名 + 参数 + 用户」POST 给 Django，
 *       Django 落库并推 SSE 给前端弹窗，等用户点同意/拒绝后返回结果。
 *
 * 已验证的三条路径：
 *  - 返回 undefined          → 工具执行
 *  - 返回 { block: true }    → 工具不执行，模型收到 reason
 *  - Django 超时/不可达       → 按拒绝处理（fail-closed）
 *
 * 环境变量（由 Django 起进程时注入）：
 *  - FACHUAN_APPROVAL_URL     审批端点
 *  - FACHUAN_INTERNAL_TOKEN   服务间鉴权（与 Django settings 共享密钥）
 *  - FACHUAN_USER_ID          当前用户 id
 *  - FACHUAN_SESSION_ID       Agent 会话标识
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const APPROVAL_URL =
  process.env.FACHUAN_APPROVAL_URL ??
  "http://127.0.0.1:8002/api/v1/agent/approval/request";

const INTERNAL_TOKEN = process.env.FACHUAN_INTERNAL_TOKEN ?? "";
const USER_ID = Number(process.env.FACHUAN_USER_ID ?? "0");
const SESSION_ID = process.env.FACHUAN_SESSION_ID ?? "";

/**
 * 高风险工具判定模式：命中即必须人工审批。
 * 与 backend/apps/agent/services/approval.py 的 DANGER_PATTERNS 保持一致
 * （一致性由单测守护）；服务端另有二次兜底判定（防 extension 被绕过）。
 * 覆盖：一切删除 / 对外发出递交上传 / 归档确认 / 审批动作本身 / 批量清空重置。
 * approve_：approve_workflow_step 是工作流 gate 的人工确认动作本身，模型
 * 低危直调 = 替人批准自己发起的工作流，必须升级为人工审批（2026-10-25 审计）。
 * execute_/trigger_/batch_：外部副作用与批量写（法院递交立案 / OA 立案 /
 * 外部担保接口 / 批量建档案），2026-10-25 审计补入——此前全被判 LOW 直执行。
 * 刻意不拦 create_/update_（业务写、服务层归属兜底）与 export_/download_（无破坏性）。
 * sync_ 不进高危但已列入 WRITE_PREFIXES（中级留痕）。
 */
const HIGH_RISK_PATTERNS: readonly string[] = [
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
 * 与服务端 CRITICAL_PATTERNS 保持一致（一致性由单测守护）。
 */
const CRITICAL_PATTERNS: readonly string[] = [
  "clear_all",
  "reset_and_",
  "delete_all",
  "bulk_delete",
];

/**
 * 中级：常规写入，但参数里带金额/期限/状态字段时升级为需审批。
 * 只按工具名判高危会漏掉 `update_contract(fixed_amount=...)` 这类改金额的写操作。
 * 2026-10-25 审计补入 8 个前缀（generate_/save_/move_/sync_/start_/retry_/
 * assign_/learn_）——它们此前被判 LOW，连留痕都没有。
 * 与服务端 SENSITIVE_ARG_MARKERS / WRITE_PREFIXES 保持一致。
 */
const SENSITIVE_ARG_MARKERS: readonly string[] = [
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

const WRITE_PREFIXES: readonly string[] = [
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
  // 2026-10-25 二轮：与服务端同步补 18 前缀（改名/重排/绑定/开关/取消/产出文件类）
  "ensure_",
  "bind_",
  "rename_",
  "reorder_",
  "toggle_",
  "merge_",
  "complete_",
  // 改写合同：框选一段后按指令重新措辞并写回原文件。不带写前缀会被判
  // LOW=只读，而它实际会改律师的合同文件（与后端同步，单测守护）。
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
  // 2026-10-25 晨间审计（十九轮）：与服务端同步——convert_document（落转换
  // 记录+产物文件）/analyze_template（改模板状态+建 FieldMapping）/
  // parse_document（存上传文件+建解析任务）POST 但真写，此前误判 LOW。
  // parse_ 其余纯内存解析，用完整名精确圈定。
  "convert_",
  "analyze_",
  "parse_document",
  // 2026-10-25 记忆：remember / restore_memory 是写入但工具名不含常规写前缀，
  // 此前被判 LOW（连留痕都没有）。删除侧 forget_ 已入 DANGER（需人工审批）。
  "remember",
  "restore_memory",
];

type RiskLevel = "low" | "medium" | "high" | "critical";

/** 短名（去掉 mcp__fachuan__ 前缀），与服务端判定口径一致。 */
function shortName(toolName: string): string {
  const parts = toolName.split("__");
  return parts[parts.length - 1] ?? toolName;
}

function hasSensitiveArg(input: Record<string, unknown> | undefined): boolean {
  if (!input) {
    return false;
  }
  return Object.keys(input).some((key) => {
    const lowered = key.toLowerCase();
    return SENSITIVE_ARG_MARKERS.some((marker) => lowered.includes(marker));
  });
}

/**
 * 与后端 approval.py 的 classify_risk 同序判定：
 * 紧急 → 高 → 写类+敏感参数 → 写类 → 低
 *
 * 这是**纯名字匹配**的判定，保留作为兜底���它的问题在文件头注释里已经
 * 记了三次补丁：靠名字枚举 415 个工具不可维护，新增工具忘了登记就漏网。
 */
function classifyByName(toolName: string, input: Record<string, unknown> | undefined): RiskLevel {
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

function worse(a: RiskLevel, b: RiskLevel): RiskLevel {
  return RISK_ORDER[a] >= RISK_ORDER[b] ? a : b;
}

/**
 * 从 MCP annotations 推导风险下限（与名字黑名单**取较大者**）。
 *
 * 为什么需要这层：法穿 415 个工具**全部**带 MCP annotations
 * （实测 225 只读 / 119 写 / 71 破坏性），但名字黑名单只覆盖了其中一部分
 * ——例如 `mortgage_default_calculate`、`analyze_template` 这类不含
 * 常规写前缀的工具，光看名字会被判 LOW。
 *
 * 映射口径（保守，宁可多问不可少问）：
 * - `destructiveHint === true`        → 至少 high（破坏性写，必须人工）
 * - 非只读 且 `openWorldHint === true` → 至少 high（会外发到公网/第三方）
 * - 非只读 且 `destructiveHint === null/false` → 至少 medium（留痕，不打扰）
 * - `readOnlyHint === true`            → 不动（名字黑名单若判高，仍取较大者）
 *
 * 缺失 hints 时**不假设只读**：`readOnlyHint` 不为 true 就按「非只读」处理，
 * 这正是 MCP 规范的默认语义（未声明 = 可能破坏、可能开放世界）。
 */
function classifyByAnnotations(
  annotations: Record<string, unknown> | undefined,
  byName: RiskLevel,
): RiskLevel {
  if (!annotations) {
    // 没有 hints：不敢当只读，至少 medium 留痕
    return worse(byName, "medium");
  }
  const readOnly = annotations.readOnlyHint === true;
  if (readOnly) {
    return byName;
  }
  if (annotations.destructiveHint === true || annotations.openWorldHint === true) {
    return worse(byName, "high");
  }
  return worse(byName, "medium");
}

/**
 * 不可覆盖的硬拒绝层：命中即 critical，与任何策略/注解无关。
 *
 * 这一层存在的理由：`clear_all` / `delete_all` / `bulk_delete` 这类
 * "一次抹掉整个库"的操作，风险不是"参数对不对"而是"它根本就不该由模型
 * 自主发起"。硬拒绝比"升级到紧急审批"更诚实——后者只是多问一句。
 */
const HARD_DENY_PATTERNS: readonly string[] = [
  "clear_all",
  "delete_all",
  "bulk_delete",
  "reset_and_",
];

function isHardDenied(toolName: string): string | null {
  const hit = HARD_DENY_PATTERNS.find((pattern) => toolName.includes(pattern));
  return hit ? `命中硬拒绝规则「${hit}」：批量清空类操作不允许由模型自主发起` : null;
}

export default function (pi: ExtensionAPI) {
  pi.on("tool_call", async (event) => {
    const input = (event.input ?? {}) as Record<string, unknown>;

    // ---- 0. 硬拒绝层：命中即拒，不进审批（无人可问时不挂起）----
    const hardDeny = isHardDenied(event.toolName);
    if (hardDeny) {
      return { block: true, reason: hardDeny };
    }

    // ---- 1. 名字黑名单（兵底）----
    const byName = classifyByName(event.toolName, input);

    // ---- 2. MCP annotations（声明优先，与名字**取较大者**）----
    // `pi.getAllTools()` 是官方提供的 hints 读取口；拿不到就退回名字判定。
    const annotations = pi
      .getAllTools()
      .find((tool) => tool.name === event.toolName)?.annotations as
      | Record<string, unknown>
      | undefined;
    let level = classifyByAnnotations(annotations, byName);

    // ---- 3. 嵌套调用（聚合工具 / ctx.executeTool）：父子上取大 ----
    // pi 1.4.0 的嵌套调用**会**过 tool_call，但事件带的是父调用的 toolName
    // 和 parentToolCallId。若不处理，一个“帮模型跑 5 个查询”的聚合工具
    // 就会成为审批绕过通道（钩子只看到聚合工具本身）。
    const parentId = (event as { parentToolCallId?: string }).parentToolCallId;
    if (parentId) {
      level = worse(level, "medium");
    }

    // 低/中直接放行；中级由服务端记审计标记，不需要打断用户
    if (level === "low" || level === "medium") {
      return undefined;
    }

    try {
      const response = await fetch(APPROVAL_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(INTERNAL_TOKEN ? { "X-Internal-Token": INTERNAL_TOKEN } : {}),
        },
        body: JSON.stringify({
          tool: event.toolName,
          args: input,
          risk_level: level,
          user_id: USER_ID,
          session_id: SESSION_ID,
          // 附上判定依据，便于审计"为什么这条要高危"与事后调阈值
          risk_basis: {
            by_name: byName,
            annotations: annotations ?? null,
            nested: Boolean(parentId),
          },
        }),
      });
      if (!response.ok) {
        return {
          block: true,
          reason: `审批服务返回 ${response.status}，已拒绝执行 ${event.toolName}`,
        };
      }
      const payload = (await response.json()) as { approved?: boolean };
      if (payload.approved === true) {
        return undefined;
      }
      return { block: true, reason: `用户拒绝了 ${event.toolName}` };
    } catch (error) {
      // 网络失败：fail-closed
      return {
        block: true,
        reason: `审批服务不可用，已拒绝执行 ${event.toolName}: ${String(error)}`,
      };
    }
  });
}
