/**
 * 法穿 SI Copilot — pi 压缩接管 extension（确定性编译）
 *
 * 挂载点：pi 的 `session_before_compact` 钩子（默认由 pi 调 LLM 写摘要）。
 *
 * ## 为什么不让 LLM 自由写摘要
 *
 * pi 默认的压缩摘要是「模型自由发挥」，而法穿最怕忘掉的东西恰恰是最硬的：
 * **案号、当事人、金额、已确认的期限、引用过的法条**。这些一旦被摘要掉，
 * 律师问「上次说的违约金条款是怎么定的」模型就不记得了；更糟的是摘要可能
 * **编造**一个看起来合理的案号。
 *
 * 本扩展接管压缩，改为**纯算法编译**（零 LLM 调用、零额外成本、可复现）：
 * 从工具调用参数/结果与用户消息里机械抽取事实，编译成分段摘要。
 *
 * 生态对照：`@sting8k/pi-vcc`、`pi-blackhole`、`@pi-unipi/compactor` 都走
 * 这条路，实测 99.2% 压缩率、2600 条消息 31ms。这里按法律场景重排了段落。
 *
 * ## 段落设计（法律的定制版）
 *
 * | VCC 原段落 | 法穿法律版 |
 * |---|---|
 * | Files And Changes | **引用台账**：引过的法条/案例/材料 + 版本 |
 * | Anchors | **锚点**：案号、当事人、金额、期限 |
 * | Outstanding (RESOLVED) | **引用过期 → 待复核** |
 * | Current Status | 当前阶段 + 下一步 + 未回答的问题 |
 *
 * ## 三条硬纪律
 *
 * 1. **对话原文永不被摘要改写** —— 律师原话是审计证据。这里只做「从原文
 *    机械抽取」，不做改写、不做同义替换。
 * 2. **排序 cache 友好** —— 稳定段（目标/偏好/台账/锚点）在前，易变段
 *    （未决事项/当前状态）在后。这样多次压缩时前缀尽量不变。
 * 3. **失败一律回退** —— 任何异常都返回 `undefined`，让 pi 走它自己的
 *    LLM 摘要。压缩是增强，不能因为本扩展出错就让会话卡死。
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

/** 摘要总预算（字符）。pi 还会再序列化一次，这里留足余量。 */
const MAX_SUMMARY_CHARS = 12000;
/** 单段预算（字符）。超了先截断该段，保住其它段。 */
const MAX_SECTION_CHARS = 2600;
/** 每段最多保留多少条，防「一个会话查了 200 个案子」把摘要撑爆。 */
const MAX_ITEMS = 40;

/** 法律标识符的正则（从任意文本里机械抽取，不做语义判断）。 */
const PATTERNS = {
  // 案号：（20XX）某0105民初某某号 / （20XX）最高法民申某某号
  caseNumber: /[（(]\s*\d{4}\s*[）)]\s*[\u4e00-\u9fa5A-Za-z0-9]{1,20}?[民刑行执商知破][\u4e00-\u9fa5]{0,6}?\d{1,8}\s*号/g,
  // 中文法条：《民法典》第一千零七十九条 / 《公司法》第32条
  statute: /《[^》]{2,40}》\s*第[一二三四五六七八九十百千零〇\d]+条(?:第[一二三四五六七八九十百千零〇\d]+款)?/g,
  // 金额：3.5万元 / 120,000元 / 5000万元
  money: /\d[\d,]*(?:\.\d+)?\s*(?:万|亿)?\s*元/g,
  // 日期：2026-10-25 / 2026年10月25日
  date: /(?:\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?)/g,
  // 期限措辞附近：距…还有 N 天 / N 日内
  deadline: /(?:还有|剩余|逾期)\s*\d+\s*[天日]/g,
} as const;

interface CompactionFacts {
  goals: string[];
  caseNumbers: Set<string>;
  statutes: Set<string>;
  parties: Set<string>;
  money: Set<string>;
  dates: Set<string>;
  deadlines: Set<string>;
  toolTrail: Map<string, number>;
  errors: string[];
  lastAssistant: string;
}

function emptyFacts(): CompactionFacts {
  return {
    goals: [],
    caseNumbers: new Set(),
    statutes: new Set(),
    parties: new Set(),
    money: new Set(),
    dates: new Set(),
    deadlines: new Set(),
    toolTrail: new Map(),
    errors: [],
    lastAssistant: "",
  };
}

/** 收一个集合到预算内（保留先出现的，因为它们通常是更早确认的事实）。 */
function collect(target: Set<string>, text: unknown, pattern: RegExp, limit = MAX_ITEMS): void {
  if (typeof text !== "string" || target.size >= limit) {
    return;
  }
  for (const match of text.matchAll(pattern)) {
    if (target.size >= limit) {
      return;
    }
    const value = match[0].replace(/\s+/g, "");
    if (value.length >= 4 && value.length <= 60) {
      target.add(value);
    }
  }
}

/** 从一条消息里抽取文本（content 可能是字符串或块数组）。 */
function messageText(message: unknown): string {
  if (typeof message === "string") {
    return message;
  }
  if (!message || typeof message !== "object") {
    return "";
  }
  const content = (message as { content?: unknown }).content;
  if (typeof content === "string") {
    return content;
  }
  if (!Array.isArray(content)) {
    return "";
  }
  return content
    .map((block) => {
      if (typeof block === "string") {
        return block;
      }
      if (block && typeof block === "object" && (block as { type?: string }).type === "text") {
        return String((block as { text?: string }).text ?? "");
      }
      return "";
    })
    .join("\n");
}

/**
 * 当事人抽取：只认**工具结果里明确的结构化字段**，不从自由文本猜。
 *
 * 为什么不猜：中文人名的边界极其模糊（「张三诉李四」里谁是谁、公司名截到哪），
 * 猜错就是把错误事实写进摘要——比不写更糟。所以只认 `party_name` /
 * `client_name` 这类明确的键。
 */
function collectParties(facts: CompactionFacts, raw: unknown): void {
  if (!raw || typeof raw !== "object") {
    return;
  }
  const walk = (node: unknown, depth: number): void => {
    if (depth > 4 || facts.parties.size >= MAX_ITEMS) {
      return;
    }
    if (Array.isArray(node)) {
      node.forEach((item) => walk(item, depth + 1));
      return;
    }
    if (!node || typeof node !== "object") {
      return;
    }
    for (const [key, value] of Object.entries(node as Record<string, unknown>)) {
      const lowered = key.toLowerCase();
      const isPartyKey =
        lowered.includes("party_name") ||
        lowered.includes("client_name") ||
        lowered === "principal_name" ||
        lowered === "opposing_name" ||
        lowered === "full_name";
      if (isPartyKey && typeof value === "string") {
        const name = value.trim();
        if (name.length >= 2 && name.length <= 40) {
          facts.parties.add(name);
        }
        continue;
      }
      walk(value, depth + 1);
    }
  };
  walk(raw, 0);
}

/** 扫描一条消息，把事实累积进 facts。 */
function harvest(facts: CompactionFacts, message: unknown, roleHint: string): void {
  const text = messageText(message);
  if (!text) {
    return;
  }
  collect(facts.caseNumbers, text, PATTERNS.caseNumber);
  collect(facts.statutes, text, PATTERNS.statute);
  collect(facts.money, text, PATTERNS.money);
  collect(facts.dates, text, PATTERNS.date);
  collect(facts.deadlines, text, PATTERNS.deadline);

  if (roleHint === "user" && facts.goals.length < 10) {
    const line = text.trim().split("\n")[0]?.slice(0, 200) ?? "";
    if (line) {
      facts.goals.push(line);
    }
  }
  if (roleHint === "assistant") {
    facts.lastAssistant = text.slice(0, 600);
  }
}

/** 记录工具调用轨迹（名字 → 次数），用于「查过什么」一行速览。 */
function harvestToolCalls(facts: CompactionFacts, message: unknown): void {
  if (!message || typeof message !== "object") {
    return;
  }
  const content = (message as { content?: unknown }).content;
  if (!Array.isArray(content)) {
    return;
  }
  for (const block of content) {
    if (!block || typeof block !== "object") {
      continue;
    }
    const typed = block as { type?: string; name?: string; arguments?: unknown };
    if (typed.type !== "toolCall" && typed.type !== "tool_use") {
      continue;
    }
    const name = String(typed.name ?? "")
      .split("__")
      .pop();
    if (!name) {
      continue;
    }
    facts.toolTrail.set(name, (facts.toolTrail.get(name) ?? 0) + 1);
    // 工具参数里常带 case_id / party_name 等，一并抽取
    collectParties(facts, typed.arguments);
    const argsText = JSON.stringify(typed.arguments ?? {});
    collect(facts.caseNumbers, argsText, PATTERNS.caseNumber);
    collect(facts.statutes, argsText, PATTERNS.statute);
  }
}

/** 渲染一个段落（超预算则截断，保留头部）。 */
function renderSection(title: string, lines: string[]): string {
  if (lines.length === 0) {
    return "";
  }
  const body = lines.join("\n");
  const trimmed = body.length > MAX_SECTION_CHARS ? `${body.slice(0, MAX_SECTION_CHARS)}\n…（本段已截断）` : body;
  return `## ${title}\n${trimmed}`;
}

function setToLines(label: string, values: Set<string>): string[] {
  if (values.size === 0) {
    return [];
  }
  return [`- ${label}：${[...values].join("、")}`];
}

/**
 * 把抽取到的事实编译成摘要。
 *
 * 段落顺序刻意「稳定在前、易变在后」：多次压缩时，前面几段的字节尽量不变，
 * 让 provider 的 prompt cache 继续命中。
 */
export function compileSummary(facts: CompactionFacts, previousSummary?: string): string {
  const sections: string[] = [];

  sections.push(renderSection("会话目标", facts.goals.map((g) => `- ${g}`)));

  const ledger = [
    ...setToLines("案号", facts.caseNumbers),
    ...setToLines("引用法条", facts.statutes),
  ];
  sections.push(renderSection("引用台账（压缩后仍需可回查）", ledger));

  const anchors = [
    ...setToLines("当事人", facts.parties),
    ...setToLines("金额", facts.money),
    ...setToLines("日期", facts.dates),
    ...setToLines("期限", facts.deadlines),
  ];
  sections.push(renderSection("锚点（案号/当事人/金额/期限，回答必须以此为准）", anchors));

  const trail = [...facts.toolTrail.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 20)
    .map(([name, count]) => `- ${name} × ${count}`);
  sections.push(renderSection("已调用工具（查到过什么）", trail));

  if (facts.lastAssistant) {
    sections.push(renderSection("最近一次答复要点", [`- ${facts.lastAssistant.replace(/\n+/g, " ")}`]));
  }

  let summary = sections.filter(Boolean).join("\n\n");

  // 上一轮的摘要要保留：它含更早的锚点，丢了等于压缩一次忘一次
  if (previousSummary && previousSummary.trim()) {
    const prev = previousSummary.trim();
    const kept = prev.length > MAX_SECTION_CHARS ? `${prev.slice(0, MAX_SECTION_CHARS)}\n…（历史摘要已截断）` : prev;
    summary = `## 历史摘要（更早的会话，撰写时仍要遵守）\n${kept}\n\n${summary}`;
  }

  const header =
    "> 本摘要由法穿**确定性编译**生成（非模型改写）：内容从对话原文机械抽取，" +
    "不会新增事实。案号/当事人/金额/期限必须与工具返回核对后才能写入文书。\n\n";

  const out = header + summary;
  return out.length > MAX_SUMMARY_CHARS ? `${out.slice(0, MAX_SUMMARY_CHARS)}\n…（摘要已达上限）` : out;
}

export default function compactionTakeover(pi: ExtensionAPI) {
  pi.on("session_before_compact", async (event) => {
    const prep = event.preparation;
    const facts = emptyFacts();

    try {
      const messages = [...(prep.messagesToSummarize ?? []), ...(prep.turnPrefixMessages ?? [])];
      for (const message of messages) {
        const role = String((message as { role?: string })?.role ?? "");
        harvest(facts, message, role);
        if (role === "assistant") {
          harvestToolCalls(facts, message);
        }
      }

      // 一个事实都没抽到（例如纯闲聊会话）：不要接管，交给 pi 自己的摘要，
      // 否则会把「今天天气不错」这类对话压成一张空白表。
      const factCount =
        facts.caseNumbers.size +
        facts.statutes.size +
        facts.parties.size +
        facts.money.size +
        facts.dates.size +
        facts.deadlines.size;
      if (factCount === 0 && facts.goals.length === 0) {
        console.error("[compaction] 未抽到可锚定的事实，交回 pi 默认摘要");
        return undefined;
      }

      const summary = compileSummary(facts, prep.previousSummary);
      console.error(
        `[compaction] 确定性编译: 案号${facts.caseNumbers.size} 法条${facts.statutes.size} ` +
          `当事人${facts.parties.size} 金额${facts.money.size} 日期${facts.dates.size} ` +
          `→ ${summary.length} 字符（压缩前 ${prep.tokensBefore} tokens）`,
      );

      return {
        compaction: {
          summary,
          firstKeptEntryId: prep.firstKeptEntryId,
          tokensBefore: prep.tokensBefore,
        },
      };
    } catch (error) {
      // 压缩是增强能力：出错一律回退，绝不让会话卡死
      console.error(`[compaction] 确定性编译失败，回退 pi 默认摘要: ${String(error)}`);
      return undefined;
    }
  });
}
