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
 * 高风险工具标记：命中即必须人工审批。
 * 与 backend/apps/agent/services/approval.py 的 HIGH_RISK_TOOLS 保持一致；
 * 服务端另有二次兜底判定（防 extension 被绕过）。
 */
const HIGH_RISK_TOOLS: readonly string[] = [
  "delete_case",
  "delete_client",
  "delete_contract",
  "send_document",
  "file_lawsuit",
  "submit_court_document",
];

function isHighRisk(toolName: string): boolean {
  return HIGH_RISK_TOOLS.some((name) => toolName.includes(name));
}

export default function (pi: ExtensionAPI) {
  pi.on("tool_call", async (event) => {
    if (!isHighRisk(event.toolName)) {
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
          args: event.input ?? {},
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
