/**
 * cline 桥：把 `@cline/core`（Node SDK，没有 CLI）包成一个 stdio 行分隔 JSON 的子进程，
 * 让 Python 侧的 `cline_backend.py` 像驱动其它 agent 一样驱动它。
 *
 * ## 为什么需要这一层
 *
 * cline 只发 npm SDK，不提供可执行文件；而我们的后端是 Python。桥的职责只有三件：
 * 1. 用 `CLINE_DIR` 隔离每个会话的数据目录（实测：该环境变量直接决定
 *    `cline_mcp_settings.json` 的路径，见 `resolveDefaultMcpSettingsPath()`）；
 * 2. 把共享 MCP 写进 cline 的 MCP 设置文件（`streamableHttp` + 三个请求头）；
 * 3. 把 `ClineCore` 的事件流翻译成我们契约里的那几种帧。
 *
 * ## 协议（行分隔 JSON）
 *
 * 入（stdin）：`{type:"prompt",text}` / `{type:"abort"}` / `{type:"approval_reply",id,approved}` / `{type:"shutdown"}`
 * 出（stdout）：`ready` / `delta` / `thinking` / `tool_call` / `tool_result` / `usage` /
 *              `done` / `error` / `approval_request`
 *
 * stderr 只写诊断，不参与协议（Python 侧不读它做判断）。
 */

import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

const env = process.env;
// 不写死 `@cline/core`：SDK 装在哪由调用方决定（`CLINE_SDK` 可以是包名，也可以是
// 具体 dist/index.js 的绝对路径）。写死的话桥只能从仓库目录解析，而仓库里没有
// node_modules（实测：ERR_MODULE_NOT_FOUND）。
const { ClineCore } = await import(env.CLINE_SDK || '@cline/core');
const cfg = {
  clineDir: env.CLINE_DIR || path.join(env.HOME || '.', '.cline'),
  modelId: env.CLINE_MODEL || 'kimi-2.6',
  providerId: env.CLINE_PROVIDER || 'openai-compatible',
  baseUrl: env.CLINE_BASE_URL || '',
  apiKey: env.CLINE_API_KEY || '',
  cwd: env.CLINE_CWD || process.cwd(),
  systemPrompt: env.CLINE_SYSTEM_PROMPT || '',
  mcpName: env.CLINE_MCP_NAME || 'fachuan',
  mcpUrl: env.CLINE_MCP_URL || '',
  mcpHeaders: env.CLINE_MCP_HEADERS ? JSON.parse(env.CLINE_MCP_HEADERS) : {},
};

const t0 = Date.now();
const send = (obj) => {
  process.stdout.write(JSON.stringify(obj) + '\n');
};
const diag = (...a) => {
  process.stderr.write(`[cline-bridge ${((Date.now() - t0) / 1000).toFixed(1)}s] ${a.join(' ')}\n`);
};

/** 写 cline 的 MCP 设置文件（`streamableHttp` + 自定义头）。 */
async function writeMcpSettings() {
  if (!cfg.mcpUrl) return;
  const file = path.join(cfg.clineDir, 'data', 'settings', 'cline_mcp_settings.json');
  await mkdir(path.dirname(file), { recursive: true });
  const payload = {
    mcpServers: {
      [cfg.mcpName]: { type: 'streamableHttp', url: cfg.mcpUrl, headers: cfg.mcpHeaders, disabled: false },
    },
  };
  await writeFile(file, JSON.stringify(payload, null, 2), { mode: 0o600 });
  diag('mcp settings written:', file, 'server=', cfg.mcpName);
}

/**
 * 把 cline 的 agent_event 翻成我们的帧。
 *
 * 实测形状（2026-11-25，cline core 0.2.1，一轮工具调用）：
 * - 文本增量：`content_start` + `contentType:"text"`，`text` 是**本次增量**
 *   （`accumulated` 才是累积）——所以直接发 `text`；
 * - 工具：`content_start` + `contentType:"tool"`（`toolName` / `toolCallId` / `input`），
 *   结果在 `content_end` + `contentType:"tool"` 的 `output.content[].text`；
 * - 用量：`usage` 每条带本轮 inputTokens/outputTokens/cacheReadTokens，另有 `total*` 累计；
 * - 收尾：`done`（`reason` / `text` / `iterations`）。
 * 未知类型只记 stderr（便于 SDK 升级后第一时间发现新事件）。
 */
function translate(event) {
  const type = event?.type;
  if (type === 'content_start' && (event.contentType || 'text') === 'text') {
    const text = event.text || '';
    return text ? { type: 'delta', content: text } : null;
  }
  if (type === 'content_end' && (event.contentType || 'text') === 'text') {
    return null; // 正文已经按增量发过，收尾不再重复
  }
  if (type === 'usage') {
    // 用**本轮**字段（非 total*）：total* 是整会话累计，拿来记账会翻倍。
    return {
      type: 'usage',
      input_tokens: Math.max(0, Number(event.inputTokens || 0) - Number(event.cacheReadTokens || 0)),
      output_tokens: Number(event.outputTokens || 0),
      cache_read_tokens: Number(event.cacheReadTokens || 0),
      cache_write_tokens: Number(event.cacheWriteTokens || 0),
    };
  }
  if (type === 'done') {
    return { type: 'done', reason: event.reason || 'completed' };
  }
  if (type === 'error') {
    return { type: 'error', message: String(event.error?.message || event.message || 'cline error') };
  }
  return null;
}

/** 工具事件：`contentType:"tool"` 的 content_start / content_end。 */
function translateTool(event) {
  if (event?.contentType !== 'tool') return null;
  const callId = String(event.toolCallId || '');
  const name = String(event.toolName || '');
  if (event.type === 'content_start') {
    return { type: 'tool_call', tool_call_id: callId, name, arguments: event.input ?? {} };
  }
  if (event.type === 'content_end') {
    const parts = (event.output?.content || [])
      .map((b) => (typeof b?.text === 'string' ? b.text : ''))
      .filter(Boolean);
    return {
      type: 'tool_result',
      tool_call_id: callId,
      name,
      result: parts.length ? parts.join('\n') : JSON.stringify(event.output ?? '').slice(0, 4000),
      is_error: Boolean(event.error),
    };
  }
  return null;
}

async function main() {
  await writeMcpSettings();
  const cline = await ClineCore.create({ clientName: 'fachuan', backendMode: 'local' });
  diag('ClineCore.create OK, clineDir=', cfg.clineDir);

  const pending = new Map();
  let sessionId = null;
  let sawDone = false;

  cline.subscribe((outer) => {
    const payload = outer?.payload || {};
    if (outer?.type !== 'agent_event') {
      if (outer?.type === 'ended') {
        diag('session ended:', payload.reason);
      }
      return;
    }
    const ev = payload.event || {};
    if (process.env.CLINE_DEBUG === '1') diag('RAW', JSON.stringify(ev).slice(0, 500));
    const toolFrame = translateTool(ev);
    if (toolFrame) {
      send({ ...toolFrame, sessionId: payload.sessionId || sessionId });
      return;
    }
    const frame = translate(ev);
    if (!frame) {
      diag('unmapped agent_event:', ev.type);
      return;
    }
    if (frame.type === 'done') sawDone = true;
    send({ ...frame, sessionId: payload.sessionId || sessionId });
  });

  send({ type: 'ready', clineDir: cfg.clineDir });

  const rl = (await import('node:readline')).createInterface({ input: process.stdin });
  for await (const line of rl) {
    let msg;
    try {
      msg = JSON.parse(line);
    } catch {
      send({ type: 'error', message: 'bridge: bad json' });
      continue;
    }
    if (msg.type === 'shutdown') break;
    if (msg.type === 'abort' && sessionId) {
      await cline.abort(sessionId).catch((e) => diag('abort failed', String(e)));
      continue;
    }
    if (msg.type === 'approval_reply') {
      const resolver = pending.get(msg.id);
      if (resolver) {
        pending.delete(msg.id);
        resolver(Boolean(msg.approved));
      }
      continue;
    }
    if (msg.type === 'prompt') {
      sawDone = false;
      try {
        const res = await cline.start({
          source: 'cli',
          prompt: msg.text,
          config: {
            providerId: cfg.providerId,
            modelId: msg.model || cfg.modelId,
            apiKey: cfg.apiKey,
            baseUrl: cfg.baseUrl,
            systemPrompt: cfg.systemPrompt || '你是法穿的业务助手。',
            cwd: cfg.cwd,
            workspaceRoot: cfg.cwd,
            enableTools: true,
            enableSpawnAgent: false,
            enableAgentTeams: false,
            yolo: false,
          },
        });
        sessionId = res?.sessionId || sessionId;
        if (!sawDone) send({ type: 'done', reason: 'completed' });
      } catch (e) {
        send({ type: 'error', message: String(e?.message || e).slice(0, 400) });
        send({ type: 'done', reason: 'error' });
      }
    }
  }
  diag('bridge exiting');
  process.exit(0);
}

main().catch((e) => {
  send({ type: 'error', message: `bridge boot failed: ${String(e?.message || e).slice(0, 400)}` });
  process.exit(1);
});
