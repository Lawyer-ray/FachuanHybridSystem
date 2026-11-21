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
 *  - FACHUAN_RUN_ID           本次运行的二级寻址键（{session_id}:{agent_kind}:{seq}）
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

// 判定规则与表只有一份：`approval-rules.ts`（纯函数、可被 node 直接执行，
// 由 scripts/check-approval-parity.mjs 与 Python 权威表逐条对账）。
// 本文件只留「读环境 → 算分级 → 发 HTTP → 决定放行」这部分。
import {
  classifyByAnnotations,
  classifyByName,
  isHardDenied,
  worse,
} from "./approval-rules.ts";

const APPROVAL_URL =
  process.env.FACHUAN_APPROVAL_URL ??
  "http://127.0.0.1:8002/api/v1/agent/approval/request";

const INTERNAL_TOKEN = process.env.FACHUAN_INTERNAL_TOKEN ?? "";
const USER_ID = Number(process.env.FACHUAN_USER_ID ?? "0");
const SESSION_ID = process.env.FACHUAN_SESSION_ID ?? "";
/**
 * 二级寻址键：同一会话可能并行跑多个 agent（pi / 后续其他后端），
 * 只报 session_id 的话前端收到两条 approval_request 分不清是谁的。
 * 一起送上去，前端靠它把审批卡片挂到正确的栏。
 * 为空串表示旧行为（只有 session 级寻址），后端有稳定字段可读。
 */
const RUN_ID = process.env.FACHUAN_RUN_ID ?? "";


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
          run_id: RUN_ID,
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
