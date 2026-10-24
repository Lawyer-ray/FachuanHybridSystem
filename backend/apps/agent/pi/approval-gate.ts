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
 */
function classifyRisk(toolName: string, input: Record<string, unknown> | undefined): RiskLevel {
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

export default function (pi: ExtensionAPI) {
  pi.on("tool_call", async (event) => {
    const input = (event.input ?? {}) as Record<string, unknown>;
    const level = classifyRisk(event.toolName, input);
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
