/**
 * 入站引用（AI → 材料）的领域模型与解析。
 *
 * **我方原先只有出站引用**（律师框选/拖文件 → `[已引用文件：…]` 进 prompt），
 * 入站方向两端皆无：`ChatMessage` 没有来源字段、SSE 没有对应事件、正文里的角标
 * 一律当普通方括号渲染。结果是律师最需要的那句话——「这句结论出自哪一条」——
 * 只能靠人工全文搜关键词。
 *
 * **为什么编号必须带字母前缀**：正文里本来就有 `[1]`（列表序号、法条编号
 * `[2021]`、脚注）。只认后端分配过的 `[K n]`，其余一律当普通方括号——宁可少
 * 渲染一个角标，也不能把一个法条年份渲染成可点击的来源。
 *
 * 这里的类型是**契约的前端一半**：后端目前不发 knowledge/retrieval 事件，所以
 * `parseCiteMarkers` 现在只会命中「工具结果里的 `[page: N]`」这一类；等后端补上
 * 编号后，同一套渲染直接生效，不需要改 UI。
 */

/** 引用来源的种类（决定角标点开时显示哪套字段与跳转动作） */
export type CitationKind = 'case' | 'contract' | 'statute' | 'judgment' | 'file'

/**
 * 一条入站引用。
 *
 * 与正文里 `[Kn]` 的 `n` 一一对应：`citeNo` 必须由**后端**分配并持久化，
 * 前端不得自己按出现顺序重编号——历史回放时正文与来源表的对应关系必须还在。
 */
export interface CitationRef {
  /** 与正文 `[Kn]` 对应的编号（1 起） */
  citeNo: number
  kind: CitationKind
  /** 业务 id（能跳转到案件/合同/文书时才有） */
  refId?: number
  /** 显示名：文件名 / 法条名 / 案号 */
  name: string
  /** 定位：页（来自解析器分行，**不等于**打印页，见 pageSpanNote） */
  page?: number
  /** 定位：条款号（如「7.2」） */
  clause?: string
  /** 定位：切片 id（后端检索块的主键，用于精确回溯） */
  chunkId?: number
  /** 原文片段（角标点开时显示；缺失时角标仍可点，只是显示「原文未随本轮保存」） */
  text?: string
  /**
   * 本轮检索命中的关键词（可选）。
   *
   * **只影响角标卡片里的 `<mark>` 高亮，不参与定位**：后端目前不发检索词，
   * 缺失时不高亮即可——绝不能在前端自己按空格切词瞎猜，那会把「第」这类
   * 高频字涂满整段原文，反而看不出命中在哪。
   */
  keywords?: string[]
}

/** 后端认可的引用种类闭集（线上给别的值一律按 `file` 处理，见 narrowCitations） */
const CITATION_KINDS: readonly CitationKind[] = ['case', 'contract', 'statute', 'judgment', 'file']

/** 只认有限正整数：`cite_no` / id / 页 / 切片都是主键类字段，0、负数、小数、
 *  字符串只可能是脏数据（`"3"` 这种也不收——静默 Number() 会把 `null` 转成 0） */
function positiveIntOf(raw: unknown): number | undefined {
  return typeof raw === 'number' && Number.isInteger(raw) && raw > 0 ? raw : undefined
}

/** 只认非空字符串：空串等于没给，落 undefined 而不是让卡片显示一个空标签 */
function nonEmptyStringOf(raw: unknown): string | undefined {
  return typeof raw === 'string' && raw !== '' ? raw : undefined
}

/** 关键词只收「全字符串的数组」，其余（单串 / 混了数字）整体丢弃，不逐项强转 */
function stringListOf(raw: unknown): string[] | undefined {
  if (!Array.isArray(raw)) return undefined
  const words = raw.filter((word): word is string => typeof word === 'string' && word !== '')
  return words.length > 0 ? words : undefined
}

/**
 * 线上引用条目（**snake_case**、自由形状）→ 前端 `CitationRef`（camelCase）。
 *
 * SSE `citations` 事件与历史 `metadata.citations` 落库共用这个形状，两处**只走
 * 这一个判据**（历史回放与实时渲染若各写一份收窄，刷新前后就会出现「同一个
 * 会话里有的角标能点、有的不能」）。
 *
 * 规则（与 `parseCiteMarkers` 同一取向：**宁缺勿错**）
 * - 缺 `cite_no` 或 `name` → **整条丢弃**：没有编号永远对不上正文角标，没有显示名
 *   就只能在卡片里留个空壳，两种都只会让律师以为「来源丢了」；
 * - `kind` 不在闭集 → 落 `'file'`：种类只决定卡片展示哪套字段，不值得丢整条；
 * - 其余键**逐个显式映射**，不做泛型自动改键——那会把 raw 里前端不认识的字段
 *   （后端的调试字段、将来新增的键）一并带进渲染层，等于让线上数据定义前端类型。
 *
 * 同编号的条目后到为准、位置留在首次出现处（顺序稳定，见 mergeCitations）。
 */
export function narrowCitations(raw: unknown): CitationRef[] {
  if (!Array.isArray(raw)) return []
  const parsed: CitationRef[] = []
  for (const item of raw) {
    if (typeof item !== 'object' || item === null) continue
    const row = item as Record<string, unknown>
    const citeNo = positiveIntOf(row.cite_no)
    const name = nonEmptyStringOf(row.name)
    if (citeNo === undefined || name === undefined) continue
    const kind = row.kind as CitationKind
    const refId = positiveIntOf(row.ref_id)
    const page = positiveIntOf(row.page)
    const clause = nonEmptyStringOf(row.clause)
    const chunkId = positiveIntOf(row.chunk_id)
    const text = nonEmptyStringOf(row.text)
    const keywords = stringListOf(row.keywords)
    parsed.push({
      citeNo,
      kind: CITATION_KINDS.includes(kind) ? kind : 'file',
      name,
      ...(refId !== undefined ? { refId } : {}),
      ...(page !== undefined ? { page } : {}),
      ...(clause !== undefined ? { clause } : {}),
      ...(chunkId !== undefined ? { chunkId } : {}),
      ...(text !== undefined ? { text } : {}),
      ...(keywords !== undefined ? { keywords } : {}),
    })
  }
  return mergeCitations([], parsed)
}

/**
 * 把新到的一批引用并进已有引用表。
 *
 * `citations` 事件是**增量**的（一轮内可多次到达，后端可能先给名字、随后补齐
 * 页码/原文），所以合并规则只有一条：**同 `citeNo` 后到为准，位置留在首次出现处**。
 * 位置不能跟着新值跳：引用表是律师肉眼顺读的顺序，补一次数据就重新排序会让人
 * 以为自己看错了行。
 */
export function mergeCitations(
  existing: readonly CitationRef[] | undefined,
  incoming: readonly CitationRef[],
): CitationRef[] {
  const merged = [...(existing ?? [])]
  const at = new Map(merged.map((citation, index) => [citation.citeNo, index]))
  for (const citation of incoming) {
    const index = at.get(citation.citeNo)
    if (index === undefined) {
      at.set(citation.citeNo, merged.length)
      merged.push(citation)
    } else {
      merged[index] = citation
    }
  }
  return merged
}

/** 正文里一处 `[Kn]` 标记的位置 */
export interface CiteMarker {
  citeNo: number
  /** 在原始文本里的起止下标（含方括号） */
  start: number
  end: number
}

/**
 * 从正文里切出 `[Kn]` 标记。
 *
 * **只认 `[K<数字>]`**：`[1]`、`【1】`、`（1）`、`[K]`、`[K1,2]` 一律不认，
 * 减少误匹配比多认几种写法重要（把法条年份渲染成来源比不渲染更糟）。
 *
 * @param text 正文
 * @param known 后端分配过的编号集合；**给了就只收其中的**，超出范围的一律当
 *   普通文本——模型乱标 `[K9]` 时不能渲染出一个点了报错的角标。
 */
export function parseCiteMarkers(text: string, known?: ReadonlySet<number>): CiteMarker[] {
  const marks: CiteMarker[] = []
  const pattern = /\[K(\d{1,3})\]/g
  let match = pattern.exec(text)
  while (match !== null) {
    const citeNo = Number(match[1])
    if (Number.isInteger(citeNo) && citeNo > 0 && (known === undefined || known.has(citeNo))) {
      marks.push({ citeNo, start: match.index, end: match.index + match[0].length })
    }
    match = pattern.exec(text)
  }
  return marks
}

/**
 * 把正文与引用表对齐：正文里出现但引用表没有的编号一律剔除（同上，宁缺勿错）。
 *
 * @returns `marks` 已按 `known` 过滤；`citations` 只保留正文真的引用到的那几条
 */
export function reconcileCitations(
  text: string,
  citations: readonly CitationRef[],
): { marks: CiteMarker[]; citations: CitationRef[] } {
  const byNo = new Map(citations.map((citation) => [citation.citeNo, citation]))
  const marks = parseCiteMarkers(text, new Set(byNo.keys()))
  const used = new Set(marks.map((mark) => mark.citeNo))
  return { marks, citations: citations.filter((citation) => used.has(citation.citeNo)) }
}

/**
 * 「第 N 页」的措辞必须诚实。
 *
 * 解析器给的页号对 PDF 是物理页，但对 docx/txt 是**分段批次**——直接写「第 3 页」
 * 会让律师去翻纸质卷第 3 页而翻不到，这是合规风险而不只是体验问题。
 */
export function pageSpanNote(page: number, kind: CitationKind): string {
  if (kind === 'statute' || kind === 'judgment') return `第 ${page} 页`
  return `第 ${page} 段（按解析分段）`
}

/**
 * 正文片段：要么是普通文字，要么是一处角标。
 *
 * 单独给出「片段」而不是让渲染层自己切字符串，是为了让「哪些方括号算引用」
 * 只有 `parseCiteMarkers` 一个判据——渲染层（react-markdown 的 components 映射）
 * 拿到的文本节点可能被行内标记拆成好几段，切分规则一旦分叉就会出现
 * 「同一句话里有的 `[K1]` 是角标、有的是文本」。
 */
export type CiteSegment =
  | { kind: 'text'; text: string }
  | { kind: 'cite'; citeNo: number }

/**
 * 把一段正文按 `[Kn]` 切成「文字 / 角标」片段，供渲染层逐段还原。
 *
 * `known` 语义与 `parseCiteMarkers` 一致（给了就只认其中的编号）。
 * 没有标记时返回**单段原文**，调用方据此跳过整个替换动作（保持原字符串）。
 */
export function splitCiteSegments(
  text: string,
  known?: ReadonlySet<number>,
): CiteSegment[] {
  const marks = parseCiteMarkers(text, known)
  if (marks.length === 0) return text.length > 0 ? [{ kind: 'text', text }] : []

  const segments: CiteSegment[] = []
  let cursor = 0
  for (const mark of marks) {
    if (mark.start > cursor) segments.push({ kind: 'text', text: text.slice(cursor, mark.start) })
    segments.push({ kind: 'cite', citeNo: mark.citeNo })
    cursor = mark.end
  }
  if (cursor < text.length) segments.push({ kind: 'text', text: text.slice(cursor) })
  return segments
}

/**
 * 文本末尾是不是一个**还没写完**的角标（`[K` / `[K1`）。
 *
 * 流式输出时用：模型正一个字一个字吐 `[K12]`，若在 `[K1` 这一帧就渲染角标，
 * 用户会看到角标先亮起、随后编号从 1 跳成 12（甚至点开的是另一条来源）。
 * 判断「这一段还有半截标记」后整段先按纯文本渲染，闭合的下一帧再一次性包角标——
 * 宁可晚半秒出现，也不要闪现一个错的来源。
 *
 * 只认末尾：标记内部不可能有换行，所以一段文本里只可能**最后**那个标记没写完。
 */
export function hasPendingCiteMarker(text: string): boolean {
  return /\[K\d{0,3}$/.test(text)
}
