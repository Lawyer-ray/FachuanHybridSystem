/**
 * 工具返回原文 → 可读文本（纯文本，**绝不注入 HTML**）。
 *
 * 后端把 MCP 工具结果原样落进 `agent_agentmessage.content`，`<pre>` 直接渲染出来
 * 的是一整片转义噪声——律师点开「返回值」看到的是
 * `{'type': 'text', 'text': '{\n  "total": 1, …}'}`，这正是用户抱怨的「原文有些
 * html 换行」。只读查开发库 679 条 `role='tool'` 消息得到的真实形状（不是猜的）：
 *
 * - 257 条是 **MCP 信封的 Python dict repr**：单引号、`{'type': 'text', 'text': '…'}`；
 * - 133 条没有信封但仍是 JSON，换行是**字面 `\n` 两个字符**（`{\n  "id": 1, …}`），
 *   所以 `JSON.parse` 直接吃会失败；
 * - 其余是纯文本（`tool_search` 的「Loaded 8 tools…」用的是**真**换行）；
 * - `fetch_url` 的内层 JSON 还多一层转义（`\\n`），并带 `<br>` 与 `\u3000`；
 * - 长结果被后端截到 **8000 字符**，JSON 可能不完整 → parse 失败要退回原文，
 *   且 8000 字符必须一趟扫完（不许反复 replace 到 O(n²)）。
 *
 * 因此按「信封 → 解转义 → JSON 美化 → HTML 兜底 → 收尾」串成**一趟**：
 *
 * 1. {@link unwrapMcpEnvelope} 只认 `type`/`text` 这一种已知形状，手写扫描（不 `eval`）；
 * 2. {@link unescapeLiteralEscapes} 把字面 `\n \t \r \" \\` 还原成真字符。**先试原样
 *    `JSON.parse`**：合法 JSON 里的 `\\` 是转义过的反斜杠，先解转义会把
 *    `{"path":"C:\\new"}` 解成「C: + 换行」，把对的弄错；
 * 3. 解转义后是 JSON **对象/数组** → `JSON.stringify(v, null, 2)`（律师真读得懂的形状）；
 * 4. HTML 兜底：结构标签转换行、其余标签剥掉、实体解码（一律纯文本进 `<pre>`）；
 * 5. 3 个以上连续换行折成 2 个，首尾 trim。
 *
 * 纯文本（无信封、无 JSON、无 HTML）**原样返回**：普通中文正文不能被改写。
 * 空串 / null / undefined → 空串，调用方据此不渲染内容区。
 */

/** MCP 信封开头：`{'type': 'text', 'text': '`（Python repr 的单引号，容忍空格） */
const ENVELOPE_HEAD = /^\{\s*'type'\s*:\s*'text'\s*,\s*'text'\s*:\s*'/

/** HTML 结构标签 → 换行：`<br>` 与块级元素的闭合标签（分不清首尾的其余标签一律剥掉） */
const HTML_BREAK = /<br\b[^>]*>|<\/(?:p|div|li|tr|h[1-6])\s*>/gi

/** 其余标签：剥掉标签本身，保留里面的文字 */
const HTML_TAG = /<[^>]+>/g

/** 实体：命名实体 + 十进制/十六进制数字实体，**一趟**解一层（不递归解 `&amp;lt;`） */
const HTML_ENTITY = /&(nbsp|amp|lt|gt|quot|#39|#x[0-9a-f]+|#[0-9]+);/gi

const NAMED_ENTITIES: Record<string, string> = {
  nbsp: ' ',
  amp: '&',
  lt: '<',
  gt: '>',
  quot: '"',
  '#39': "'",
}

/** 字面转义（`\n` 两个字符）→ 真字符。只认这些，`\uXXXX` 留给 `JSON.parse`。 */
const SIMPLE_ESCAPES: Record<string, string> = {
  n: '\n',
  t: '\t',
  r: '\r',
  '"': '"',
  '\\': '\\',
  "'": "'",
  '/': '/',
}

type JsonProbe = { readonly ok: true; readonly value: unknown } | { readonly ok: false }

/**
 * 拆 MCP 信封：`{'type': 'text', 'text': '…'}` → `…`；不是这种形状返回 `undefined`。
 *
 * 手写扫描而不是正则一把梭：值里含 `\'` 转义的单引号（律师姓名、法条引文里很常见），
 * 正则会被第一个 `'` 骗停。`\'` 直接还原（这是 repr 的记账，不是报文内容）；其余
 * `\n` `\\` `\uXXXX` 原样留着交给 {@link unescapeLiteralEscapes} 与 `JSON.parse`——
 * 各管一层，不会把 `\\n` 解成换行。
 *
 * 值**没有收尾引号**时按「被 8000 字上限截断」处理，取到末尾：这类长结果（实测
 * `list_reminders_by_target` / `list_inbox_messages` 恰好 8000 字）正是最不该再顶着
 * `{'type': 'text', 'text': '{` 这层噪声给人看的那批。
 */
function unwrapMcpEnvelope(source: string): string | undefined {
  const head = ENVELOPE_HEAD.exec(source)
  if (head === null) return undefined
  let text = ''
  let index = head[0].length
  while (index < source.length) {
    const char = source.charAt(index)
    if (char === '\\') {
      const next = source.charAt(index + 1)
      if (next === '') return undefined
      text += next === "'" ? "'" : char + next
      index += 2
      continue
    }
    if (char === "'") {
      // 值到此结束：后面必须只剩 `}`，否则不是信封（别把普通文本吃掉）
      return /^\s*\}\s*$/.test(source.slice(index + 1)) ? text : undefined
    }
    text += char
    index += 1
  }
  return text
}

/** 字面转义 → 真字符。单趟扫描；未知转义（`\u3000`、`C:\x`）原样保留，宁可留着不吞字 */
function unescapeLiteralEscapes(text: string): string {
  if (!text.includes('\\')) return text
  let out = ''
  let index = 0
  while (index < text.length) {
    const char = text.charAt(index)
    if (char !== '\\') {
      out += char
      index += 1
      continue
    }
    const decoded = SIMPLE_ESCAPES[text.charAt(index + 1)]
    out += decoded ?? char
    index += decoded === undefined ? 1 : 2
  }
  return out
}

function tryParseJson(text: string): JsonProbe {
  try {
    return { ok: true, value: JSON.parse(text) as unknown }
  } catch {
    return { ok: false }
  }
}

/**
 * 内层报文 → 可读文本。
 *
 * 先按**原样** parse（合法 JSON 不必解转义）；parse 不通再按后端的落库形状解一层
 * 转义重试。解析出来是**字符串**（整段是 JSON 字符串体 `"…"`）就继续往下读一层：
 * 正文在那层引号里面。对象/数组缩进两格；其余（纯文本、截断的 JSON）原样返回。
 */
function readablePayload(payload: string): string {
  const direct = tryParseJson(payload)
  const parsed = direct.ok ? direct : tryParseJson(unescapeLiteralEscapes(payload))
  if (parsed.ok) {
    const value = parsed.value
    if (typeof value === 'string') return readablePayload(value)
    if (typeof value === 'object' && value !== null) return JSON.stringify(value, null, 2)
  }
  return unescapeLiteralEscapes(payload)
}

function decodeEntity(body: string): string {
  const named = NAMED_ENTITIES[body.toLowerCase()]
  if (named !== undefined) return named
  const hex = /^#x([0-9a-f]+)$/i.exec(body)
  const dec = /^#([0-9]+)$/.exec(body)
  const code =
    hex !== null
      ? Number.parseInt(hex[1] ?? '', 16)
      : dec !== null
        ? Number.parseInt(dec[1] ?? '', 10)
        : Number.NaN
  if (!Number.isFinite(code) || code < 0 || code > 0x10ffff) return `&${body};`
  return String.fromCodePoint(code)
}

/**
 * HTML 兜底：结构标签换行、其余标签剥掉、实体解码。
 *
 * 实体必须**在剥标签之后**解：`&lt;b&gt;` 是文字「<b>」而不是标签。
 */
function htmlToText(text: string): string {
  if (!text.includes('<') && !text.includes('&')) return text
  return text
    .replace(HTML_BREAK, '\n')
    .replace(HTML_TAG, '')
    .replace(HTML_ENTITY, (_match, body: string) => decodeEntity(body))
}

/** 工具返回原文 → 可读文本（安全纯文本，不注入 HTML）。 */
export function formatToolContent(raw: string | undefined | null): string {
  const source = raw?.trim() ?? ''
  if (source === '') return ''
  const payload = unwrapMcpEnvelope(source) ?? source
  return htmlToText(readablePayload(payload))
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}
