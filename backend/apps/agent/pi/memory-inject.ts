/**
 * 法穿 SI Copilot — pi 记忆注入 extension
 *
 * 挂载点：pi 的 `before_agent_start`（每轮模型请求前改 system prompt）。
 *
 * ## 为什么记忆要通过本扩展注入，而不是写进 AGENTS.md
 *
 * `AGENTS.md` 是每轮全量注入的固定文件，由 `pi/shared_mcp._write_agents_md`
 * 直接 copyfile。把记忆写进那里有三个问题：随会话数膨胀、含用户隐私数据
 * 落盘、以及无法按律师/团队/律所过滤（文件是全局的）。
 *
 * 所以记忆存 Django，本扩展在 `session_start` 拉一次快照，后续轮次复用
 * 同一份字节——这是刻意为之：system prompt 前缀若每轮变化，prompt cache
 * 全废（`backend/apps/agent/README.md` 有实测论证）。对应 pi-memory 的
 * "KV cache-stable snapshot" 模式。
 *
 * ## 快照刷新时机（与 pi-memory 对齐）
 *
 * - `session_start`             — 会话开始
 * - `session_before_compact`    — 压缩前（压缩会改变上下文，一次有意的边界）
 * - 跨天                        — 快照记录的日期与今天不符
 *
 * 不刷新的情况：模型刚 `remember` 了一条。那会让快照变化、破坏 cache。
 * 新记忆在**下一次会话**必然可见，本次会话内模型自己知道刚写了什么。
 *
 * ## 失败策略
 *
 * 拉快照失败一律**降级为不注入**（而不是抛错）：记忆是增强能力，不能因为
 * 记忆端点不可用就让整个对话失败。同时把原因打到 stderr，便于排查。
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

/** 记忆快照端点（Django 侧 /api/v1/agent/memory/snapshot） */
const API_BASE =
  process.env.FACHUAN_API_BASE ?? "http://127.0.0.1:8002/api/v1";
const USER_TOKEN = process.env.FACHUAN_USER_TOKEN ?? "";

/** 快照上限（字符）。服务端已按层限额渲染，这里只做最后一道防线。 */
const MAX_SNAPSHOT_CHARS = 4000;

/** 拉取超时。快照端点是纯 DB 查询 + 缓存，正常 <100ms；3s 足够且不拖慢首响应。 */
const FETCH_TIMEOUT_MS = 3000;

interface SnapshotState {
  content: string;
  takenOnDate: string;
  loaded: boolean;
}

const state: SnapshotState = { content: "", takenOnDate: "", loaded: false };

function todayStr(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

async function fetchSnapshot(): Promise<string> {
  if (!USER_TOKEN) {
    // stdio / 手工场景没有令牌——服务端会回退服务账号，但记忆注入必须
    // 严格按人，宁可注入空也不能串人。
    return "";
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const resp = await fetch(`${API_BASE}/agent/memory/snapshot`, {
      headers: { Authorization: `Bearer ${USER_TOKEN}` },
      signal: controller.signal,
    });
    if (!resp.ok) {
      console.error(`[memory] snapshot HTTP ${resp.status}`);
      return "";
    }
    const data = (await resp.json()) as { content?: string };
    const content = typeof data?.content === "string" ? data.content : "";
    return content.length > MAX_SNAPSHOT_CHARS
      ? content.slice(0, MAX_SNAPSHOT_CHARS)
      : content;
  } catch (error) {
    console.error(`[memory] snapshot fetch failed: ${String(error)}`);
    return "";
  } finally {
    clearTimeout(timer);
  }
}

async function refresh(reason: string): Promise<void> {
  state.content = await fetchSnapshot();
  state.takenOnDate = todayStr();
  state.loaded = true;
  if (state.content) {
    console.error(`[memory] snapshot loaded (${reason}, ${state.content.length} chars)`);
  }
}

export default function memoryInjection(pi: ExtensionAPI) {
  pi.on("session_start", async () => {
    await refresh("session_start");
  });

  pi.on("session_before_compact", async () => {
    // 压缩会重写上下文，此时刷新快照是一次「有意的 cache 边界」，
    // 后续所有轮次又回到字节稳定状态。
    await refresh("session_before_compact");
  });

  pi.on("before_agent_start", async (event) => {
    if (!state.loaded) {
      // session_start 未触发（如 --resume 的某些路径）时兜底拉一次
      await refresh("before_agent_start");
    } else if (state.takenOnDate !== todayStr()) {
      // 跨天：今日/昨日日志语义变了，快照必须重建
      await refresh("day_rollover");
    }

    if (!state.content) {
      return;
    }

    // 用 systemPromptOptions.sections 增量改一段，而不是整段替换 systemPrompt：
    // 整段替换会让 pi 记录的结构化 sections 与实际 prompt 漂移，且与审批
    // extension 这类同挂 before_agent_start 的扩展容易互相覆盖。
    event.systemPromptOptions.sections.memory = state.content;
  });
}
