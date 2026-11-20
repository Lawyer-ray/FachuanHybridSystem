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
 * - {@link MentionSource} 是可插拔的数据源，同类对象一个源，按触发符注册
 *   （`@` 引用对象、`/` 命令走同一条管线）；
 * - 选中结果统一落成 {@link MentionInsert}，出站文本由 {@link mentionRefBlock}
 *   **一处**生成，沿用**已有**的 `[已引用文件：…]` 协议（`domain/transcript.ts`
 *   的 `SENT_REF_RE` 已能解析回来）。
 *
 * 这一点很关键：**引用的出站协议只有一份**。新增 `@` 只是多了一条通往它的输入
 * 路径，不是第二套引用格式——否则历史回放的 chip 与实时 chip 必然长得不一样。
 */

/** 可引用对象的种类（决定图标、分组标题与出站文本里的键名） */
export type MentionKind = 'case' | 'contract' | 'document' | 'folder' | 'lawyer' | 'tag'

/** 触发符：`@` 引用对象、`/` 命令（同一条管线，源按 trigger 注册） */
export type MentionTrigger = '@' | '/'

/** 引用归属的业务对象：出站块里的 id 键名（case_id / contract_id）由它决定 */
export interface MentionOwner {
  kind: 'case' | 'contract'
  /** 案件 id 或合同 id（= 绑定文件夹的 owner） */
  id: number
}

/** 一个候选（异步源返回，菜单渲染用） */
export interface MentionCandidate {
  kind: MentionKind
  /** 业务 id（文件夹/文书靠 owner+subpath 定位，故可选） */
  refId?: number
  /** 主显示名（也是模糊匹配的唯一字段——描述不参与匹配，见 filterMentionCandidates） */
  label: string
  /** 副标题（案由 / 客户名 / 上级目录），只显示不匹配 */
  sublabel?: string
  /** 绑定文件夹内的相对路径；整案/整份合同用 `'.'` 表示绑定根（后端把它归一成空串） */
  subpath?: string
  /** 归属对象。缺省 = 该类对象无法落进出站协议（源宁可不给候选，也不要给无归属的） */
  owner?: MentionOwner
}

/** 选中后进入草稿的原子引用 */
export interface MentionInsert extends MentionCandidate {
  /**
   * 出站文本投影（复制、持久化、发送都用它，是引用的**唯一**持久形态）。
   * 由 {@link mentionRefBlock} 生成——**不要**在别处手拼引用块。
   */
  clipboardText: string
  /**
   * 进草稿的**内联**文本（默认回落到 clipboardText）。
   *
   * 为什么要和内联文本分开：`[已引用文件：起诉状.pdf (attachment_id=…, contract_id=5,
   * subpath="1-一审/起诉状.pdf")]` 是一台机器读的协议，塞进「结合 … 第 3 段」中间
   * 就没法改字了（光标一动就跨过十几个不可读字符）。所以草稿里只留人能读的
   * `@起诉状.pdf `，协议块由 outgoing 在发送时整齐缀在正文后。
   */
  insertText?: string
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
  // 只要插入文本：`/` 技能补全只需要一个 insertText，不必伪造整个 MentionInsert
  insert: { clipboardText?: string; insertText?: string },
): { text: string; caret: number } {
  const piece = insert.insertText ?? insert.clipboardText ?? ''
  const next = text.slice(0, token.start) + piece + text.slice(token.end)
  return { text: next, caret: token.start + piece.length }
}

/** 目录类引用（块首用「已引用目录」）；case/contract 指向的是它的整棵绑定文件夹 */
const FOLDER_LIKE_KINDS = new Set<MentionKind>(['case', 'contract', 'folder'])

/**
 * **出站引用块的唯一构造点**。
 *
 * 四种引用（整案 / 整份合同 / 目录 / 文书）与拖拽进来的文件夹引用共用这一个
 * 函数，产出的行必须与 `domain/transcript.ts` 的 `SENT_REF_RE` 严格互逆——
 * 那边是历史回放 chip 的解析器。两处各拼一份的后果是：发出去是协议块，回放
 * 时认不出来，律师刷新页面就看到一坨 `[已引用文件：…]` 长文本。
 *
 * 形态（`attachment_id` 只在落了附件的场景出现，这里给拖拽/上传路径复用）：
 * `[已引用文件：name (attachment_id=…, contract_id=N, subpath="…")]`
 * `[已引用目录：name (case_id=N, subpath="…")]`
 *
 * @param input.kind  引用种类（决定用「文件」还是「目录」+ 字形）
 * @param input.owner 归属；缺失时返回空串（调用方须把空串当作「不可出站」）
 * @param attachmentId 附件回执 id（拖拽/上传路径专用）
 */
export function mentionRefBlock(
  input: Pick<MentionCandidate, 'kind' | 'label' | 'subpath' | 'owner'>,
  attachmentId?: string | number,
): string {
  const owner = input.owner
  if (!owner) return ''
  // 文件名里的换行会把「一行一个引用块」的行式解析切坏（splitRefBlocks 按 \n 切）
  const name = input.label.replace(/[\r\n]+/g, ' ').trim()
  if (!name) return ''
  // 引号会提前闭合 subpath="…"，让整条正则在半路匹配失败
  const subpath = (input.subpath ?? '').replace(/"/g, "'")
  const idKey = owner.kind === 'case' ? 'case_id' : 'contract_id'
  const head = attachmentId === undefined ? '' : `attachment_id=${attachmentId}, `
  const unit = FOLDER_LIKE_KINDS.has(input.kind) ? '已引用目录' : '已引用文件'
  return `[${unit}：${name} (${head}${idKey}=${owner.id}, subpath="${subpath}")]`
}

/**
 * 候选 → 草稿原子（源在 `toInsert` 里统一调它）。
 *
 * `clipboardText` 由 {@link mentionRefBlock} 生成、`insertText` 是内联的
 * `@名字 `；无归属的候选会得到空 `clipboardText`，`outgoing` 据此跳过它。
 */
export function makeMentionInsert(
  input: Pick<MentionCandidate, 'kind' | 'label' | 'refId' | 'sublabel' | 'subpath' | 'owner'>,
): MentionInsert {
  return {
    ...input,
    clipboardText: mentionRefBlock(input),
    insertText: `@${input.label.trim()} `,
  }
}

/** 可插拔的候选数据源：一类对象一个源，按 {@link MentionTrigger} 挂到触发符上 */
export interface MentionSource {
  /** 分组键（同一 trigger 下唯一；失败时按它静默掉这一组） */
  key: string
  trigger: MentionTrigger
  /** 分组标题（菜单里的小标题） */
  title: string
  /** 拉候选。查询词过滤口径由源自己负责（服务端搜的字段与本地搜的字段不一定相同） */
  load: (req: { query: string; signal: AbortSignal }) => Promise<MentionCandidate[]>
  /** 候选 → 草稿原子；不能出站的候选返回空 clipboardText */
  toInsert: (candidate: MentionCandidate) => MentionInsert
}

/** 菜单里的一行（已摊平的分组视图，供键盘共享高亮使用） */
export interface MentionOption {
  /** 分组键 */
  key: string
  /** 组内下标 */
  index: number
  candidate: MentionCandidate
}

/** 高亮位置：指向某个组的某一行（不能只用扁平下标——分组会随异步返回增减） */
export interface MentionHighlight {
  key: string
  index: number
}

/** 组的最小形状（供纯函数使用，不绑定 hook 的 state 类型） */
export interface MentionGroupLike {
  key: string
  status: 'pending' | 'ready'
  items: readonly MentionCandidate[]
}

/**
 * 菜单行的 DOM id（`aria-activedescendant` 指向它）。
 *
 * 用「分组键 + 组内下标」而不是扁平下标：扁平下标会随异步返回的组增减而错位，
 * 活动后代指向另一行，读屏会念错对象。
 */
export function mentionOptionId(key: string, index: number): string {
  return `mention-opt-${key}-${index}`
}

/** 摊平所有**已就绪**组的行：pending 组没有行，键盘永远碰不到陈旧数据 */
export function flattenMentionOptions(groups: readonly MentionGroupLike[]): MentionOption[] {
  const out: MentionOption[] = []
  for (const group of groups) {
    if (group.status !== 'ready') continue
    group.items.forEach((candidate, index) => out.push({ key: group.key, index, candidate }))
  }
  return out
}

/**
 * 在已就绪的行之间环形移动高亮。
 *
 * 环形而不是夹在两端：律师会用 ↓ 一路滑到底又滑回来，卡住会以为菜单死了。
 * 结果变化后高亮失效（原位置不存在了）时回到第一行。
 */
export function moveMentionHighlight(
  options: readonly MentionOption[],
  current: MentionHighlight | null,
  delta: number,
): MentionHighlight | null {
  if (options.length === 0) return null
  const at = current === null ? -1 : options.findIndex((o) => o.key === current.key && o.index === current.index)
  if (at < 0) return { key: options[0]!.key, index: options[0]!.index }
  const next = options[(at + delta + options.length) % options.length]
  return next ? { key: next.key, index: next.index } : null
}
