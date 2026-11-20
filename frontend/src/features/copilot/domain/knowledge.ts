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
