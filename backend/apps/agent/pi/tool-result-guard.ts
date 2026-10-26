/**
 * 法穿 SI Copilot — pi 工具结果守卫 extension
 *
 * 挂载点：pi 的 `tool_result` 钩子（工具返回后、进入模型上下文前）。
 *
 * ## 为什么需要它
 *
 * 三道防线都在这一层，且**只有这一层能一次覆盖 415 个工具**：
 *
 * 1. **剥离内部字段**：法穿后端返回体里常带 `_internal_id`、`sql`、
 *    审计时间戳这类模型不需要的东西。它们既费 token，也把内部结构泄给
 *    模型（进而可能被写进答复）。
 * 2. **不可见字符检测**：合同/法条正文里混入 U+200B（零宽空格）、
 *    U+200C/D（零宽连接符）、U+2060（词连接符）、U+00A0（不换行空格）、
 *    U+FEFF（BOM）是**真实事故**——律师肉眼不可能发现，复制进判决书
 *    或合同后会造成排版错乱甚至条款解释争议。命中原样保留内容，只在
 *    结果尾部附一行提示，让模型知道「这份正文有隐式字符，引用前先确认」。
 * 3. **敏感字段兜底脱敏**：工具入参侧已由审批网关按 `SENSITIVE_ARG_MARKERS`
 *    判定，但**出参侧没有任何闸门**。卷宗正文里出现身份证号/银行卡号/
 *    手机号时，它们在进入上下文后可能被模型复述进答复。这里做最后一层
 *    兜底（只对**已知模式**脱敏，宁可少脱不可多脱——法律文书里的案号、
 *    金额、日期一律不动）。
 *
 * ## 刻意不做的事
 *
 * - **不做截断**。pi 对 MCP 结果已有 20KB 以上的处理，且大结果压缩由
 *   MCP 侧（`mcp_server/tool_shaping.py`）按业务语义做投影更准确。
 *   在这里按字符数腰斩会切断 JSON 结构，反而害了模型。
 * - **不改 `structuredContent`**。本仓库的工具全部返回文本块，没有
 *   `outputSchema` → 没有 `structuredContent`，改它只会引入不一致。
 * - **不阻断**。`tool_result` 抛异常只会被 pi 报错后继续，宣传性拦阻
 *   没有意义；发现问题一律「保留原文 + 附提示」。
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

/** 只处理法穿自己的工具；内置工具已由 `--tools` 全部关闭，这里是双保险。 */
const TOOL_PREFIX = "mcp__fachuan__";

/**
 * 内部字段黑名单（精确名）。模型不需要、但后端为了 REST 契约带上的字段。
 * 只列**确定无害于删除**的：一旦误删业务字段，模型会以为数据缺失。
 */
const INTERNAL_FIELDS = new Set([
  "_internal_id",
  "_debug",
  "sql",
  "raw_sql",
  "query_plan",
  "request_id",
  "trace_id",
  "span_id",
]);

/**
 * 不可见 / 易混淆字符。每个都注明为什么危险——这张表会被后来人当文档读。
 */
const INVISIBLE_CHARS: ReadonlyArray<{ code: number; name: string }> = [
  { code: 0x200b, name: "零宽空格 U+200B" },
  { code: 0x200c, name: "零宽非连接符 U+200C" },
  { code: 0x200d, name: "零宽连接符 U+200D" },
  { code: 0x2060, name: "词连接符 U+2060" },
  { code: 0x00a0, name: "不换行空格 U+00A0" },
  { code: 0xfeff, name: "BOM U+FEFF" },
  { code: 0x2028, name: "行分隔符 U+2028" },
  { code: 0x2029, name: "段分隔符 U+2029" },
];

/**
 * 出参脱敏规则。**顺序敏感**：先长后短，避免身份证号被手机号规则先切碎。
 *
 * 刻意**不含**：案号、金额、日期、法条条号——这些是法律业务的信号，
 * 脱掉它们等于毁掉工具结果。只脱「能直接识别自然人」的那几类。
 */
const REDACT_RULES: ReadonlyArray<{ pattern: RegExp; label: string; keep: number }> = [
  // 身份证：18 位，末位可为 X。保留前 6 位（地区码）与后 4 位，中间打码。
  { pattern: /\b(\d{6})\d{8}(\d{3}[\dXx])\b/g, label: "身份证", keep: 6 },
  // 银行卡：16-19 位连续数字（前后不能是数字，避免吃掉更长的编号）
  { pattern: /(?<!\d)(\d{4})\d{8,11}(\d{4})(?!\d)/g, label: "银行卡", keep: 4 },
  // 手机号：中国大陆 1[3-9] 开头 11 位
  { pattern: /(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)/g, label: "手机号", keep: 3 },
];

interface ScanResult {
  text: string;
  redactions: string[];
  invisibles: string[];
}

/** 出参脱敏：保留头尾，中间打码，并在汇总里报次数。 */
function redact(text: string): { text: string; hits: string[] } {
  const hits: string[] = [];
  let out = text;
  for (const rule of REDACT_RULES) {
    out = out.replace(rule.pattern, (match, head: string, tail: string) => {
      hits.push(rule.label);
      const masked = "*".repeat(Math.max(4, match.length - head.length - tail.length));
      return `${head}${masked}${tail}`;
    });
  }
  return { text: out, hits };
}

/** 不可见字符统计（只统计不改写——改写会破坏正文原貌，法律文书不能动）。 */
function scanInvisible(text: string): string[] {
  const found = new Set<string>();
  for (const ch of text) {
    const code = ch.codePointAt(0) ?? 0;
    const hit = INVISIBLE_CHARS.find((c) => c.code === code);
    if (hit) {
      found.add(hit.name);
    }
  }
  return [...found];
}

/** 递归剥离 JSON 里的内部字段（只处理对象/数组，其他原样）。 */
function stripInternalFields(value: unknown, depth = 0): unknown {
  if (depth > 8 || value === null || typeof value !== "object") {
    return value;
  }
  if (Array.isArray(value)) {
    return value.map((item) => stripInternalFields(item, depth + 1));
  }
  const out: Record<string, unknown> = {};
  for (const [key, val] of Object.entries(value as Record<string, unknown>)) {
    if (INTERNAL_FIELDS.has(key)) {
      continue;
    }
    out[key] = stripInternalFields(val, depth + 1);
  }
  return out;
}

/**
 * 尝试把文本块当 JSON 解析并剥离内部字段。
 * 解析失败原样返回——很多工具返回的是 Markdown / 自然语言，不是 JSON。
 */
function stripFieldsFromText(text: string): string {
  const trimmed = text.trimStart();
  if (!trimmed.startsWith("{") && !trimmed.startsWith("[")) {
    return text;
  }
  try {
    const parsed = JSON.parse(text) as unknown;
    const stripped = stripInternalFields(parsed);
    if (JSON.stringify(stripped) === JSON.stringify(parsed)) {
      return text;
    }
    return JSON.stringify(stripped, null, 2);
  } catch {
    return text;
  }
}

function scan(text: string): ScanResult {
  const stripped = stripFieldsFromText(text);
  const { text: redacted, hits } = redact(stripped);
  return {
    text: redacted,
    redactions: hits,
    invisibles: scanInvisible(redacted),
  };
}

export default function toolResultGuard(pi: ExtensionAPI) {
  pi.on("tool_result", async (event) => {
    if (!event.toolName.startsWith(TOOL_PREFIX)) {
      return undefined;
    }

    const redactionHits: string[] = [];
    const invisibleHits = new Set<string>();
    let changed = false;

    const nextContent = event.content.map((block) => {
      if (block.type !== "text" || typeof block.text !== "string") {
        return block;
      }
      const result = scan(block.text);
      redactionHits.push(...result.redactions);
      result.invisibles.forEach((name) => invisibleHits.add(name));
      if (result.text !== block.text) {
        changed = true;
        return { ...block, text: result.text };
      }
      return block;
    });

    // 提示统一附在**最后一段文本块**末尾，不新增块（新增块会被前端当成
    // 独立内容渲染）。提示必须说清「这是什么、要不要管、怎么处置」。
    const notices: string[] = [];
    if (redactionHits.length > 0) {
      const summary = [...new Set(redactionHits)].join("、");
      notices.push(
        `[法穿守卫] 结果中的 ${redactionHits.length} 处敏感号码（${summary}）已脱敏。` +
          `如需完整号码，请通过业务页面查看，不要在答复中还原。`,
      );
    }
    if (invisibleHits.size > 0) {
      notices.push(
        `[法穿守卫] 正文含不可见字符（${[...invisibleHits].join("、")}）。` +
          `直接引用可能导致排版错乱或条款歧义——写入文书前建议先清洗。`,
      );
    }
    if (notices.length === 0 && !changed) {
      return undefined;
    }

    if (notices.length > 0) {
      const lastIdx = nextContent.length - 1;
      const last = nextContent[lastIdx];
      if (last && last.type === "text" && typeof last.text === "string") {
        nextContent[lastIdx] = {
          ...last,
          text: `${last.text}\n\n${notices.join("\n")}`,
        };
      } else {
        nextContent.push({ type: "text", text: notices.join("\n") });
      }
    }

    return { content: nextContent };
  });
}
