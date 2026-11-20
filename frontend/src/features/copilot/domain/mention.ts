/**
 * `@` 引用（输入框里直接引用案件 / 合同 / 文书 / 文件夹）。
 *
 * **为什么值得单独做一条管线**：律师起草时最高频的动作是「结合 @某案 的诉状第 3 段」。
 * 现在的路径是：打开文件夹抽屉 → 找到文件 → 拖进输入框。三步，
 * 且每次都从头找。而「在输入框里打 `@` + 两个字」是一步。
 *
 * **为什么不给每类对象写一套下拉框**：四套键盘导航 + 四套异步竞态 + 四套「选完
 * 清空输入框」的 bug。这里把「识别 token」与「候选从哪来」分开：
 * - {@link detectMentionToken} 是纯函数（node 可测），只管「光标前是不是一个
 *   `@`/`/` token、查询词是什么」；
 * - {@link MentionSource} 是可插拔的数据源，同类对象一个源；
 * - 选中结果统一落成 {@link MentionInsert}，出站文本沿用**已有**的
 *   `[已引用文件：…]` 协议（`domain/transcript.ts` 的 `SENT_REF_RE` 已能解析回来）。
 *
 * 这一点很关键：**引用的出站协议只有一份**。新增 `@` 只是多了一条通往它的输入
 * 路径，不是第二套引用格式——否则历史回放的 chip 与实时 chip 必然长得不一样。
 */

/** 可引用对象的种类（决定图标、分组标题与出站文本里的键名） */
export type MentionKind = 'case' | 'contract' | 'document' | 'folder' | 'lawyer' | 'tag'

/** 一个候选（异步源返回，菜单渲染用） */
export interface MentionCandidate {
  kind: MentionKind
  /** 业务 id（文件夹用 ownerId+subpath 组合，故可选） */
  refId?: number
  /** 主显示名（也是模糊匹配的唯一字段——描述不参与匹配，见 filterMentionCandidates） */
  label: string
  /** 副标题（案由 / 客户名 / 上级目录），只显示不匹配 */
  sublabel?: string
}

/** 选中后进入草稿的原子引用 */
export interface MentionInsert extends MentionCandidate {
  /** 出站文本投影（复制、持久化、发送都用它，是引用的**唯一**持久形态） */
  clipboardText: string
}

/** 光标前识别出的触发 token */
export interface MentionToken {
  trigger: '@' | '/'
  /** 触发字符之后的查询词（不含触发字符本身） */
  query: string
  /** token 在文本里的起止下标（替换时要连触发字符一起换掉） */
  start: number
  end: number
}

/** `@` 只在词首开火：草稿开头、空白后、标点后。邮箱地址与网址里的 `@`/`/` 不该弹菜单。 */
const BOUNDARY_BEFORE = new Set(['', ' ', '\t', '\n', '，', '。', '、', '；', '：', '（', '(', '"', "'", '/'])

/**
 * 识别光标前的触发 token。
 *
 * @param text 草稿全文
 * @param caret 光标位置（0..text.length）
 * @returns 命中时返回 token（`end` 恒等于 caret），否则 null
 */
export function detectMentionToken(text: string, caret: number): MentionToken | null {
  if (caret < 0 || caret > text.length) return null
  // 从光标往回找最近的触发字符，遇到空白就放弃（token 不跨空白）
  for (let i = caret - 1; i >= 0; i -= 1) {
    const ch = text.charAt(i)
    if (ch === ' ' || ch === '\t' || ch === '\n') return null
    if (ch !== '@' && ch !== '/') continue
    const before = i === 0 ? '' : text.charAt(i - 1)
    if (!BOUNDARY_BEFORE.has(before)) return null
    // `/` 允许出现在草稿任意位置就是命令语义；这里只拒绝把 `//` 与 `https:/` 当命令
    if (ch === '/' && (before === '/' || before === ':')) return null
    return { trigger: ch, query: text.slice(i + 1, caret), start: i, end: caret }
  }
  return null
}

/**
 * 候选排序 + 过滤。
 *
 * **只在 label 上做匹配，sublabel 不参与**：菜单只有一个共享高亮，副标题命中会
 * 把「看起来不相关的一行」顶到最前，律师按 Enter 就选错了对象。
 *
 * @param candidates 源返回的候选
 * @param query 查询词（空串 = 原序全量）
 * @param limit 最多返回几条（菜单一屏）
 */
export function filterMentionCandidates(
  candidates: readonly MentionCandidate[],
  query: string,
  limit = 20,
): MentionCandidate[] {
  const needle = query.trim().toLowerCase()
  if (!needle) return candidates.slice(0, limit)
  const prefix: MentionCandidate[] = []
  const contains: MentionCandidate[] = []
  for (const candidate of candidates) {
    const hay = candidate.label.toLowerCase()
    if (hay.startsWith(needle)) prefix.push(candidate)
    else if (hay.includes(needle)) contains.push(candidate)
  }
  return [...prefix, ...contains].slice(0, limit)
}

/**
 * 把 token 替换成引用文本，并给出新的光标位置。
 *
 * 纯函数：不碰 DOM、不碰 store。`insert` 里的 `clipboardText` 就是最终进草稿的
 * 文本（同时也是出站协议里的那一份），**不做二次格式化**。
 */
export function applyMention(
  text: string,
  token: MentionToken,
  insert: MentionInsert,
): { text: string; caret: number } {
  const next = text.slice(0, token.start) + insert.clipboardText + text.slice(token.end)
  return { text: next, caret: token.start + insert.clipboardText.length }
}
