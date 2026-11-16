import type { PageKey, PageSpan, PositionedBlock, Segment } from '../types'

/**
 * 按页锚点搬运段正文：切段 / 并段 / 块级编辑定位共用的一套纯函数。
 *
 * ## 为什么必须按页而不是按字符比例
 *
 * `seg.md` 是后端把整段各页正文拼起来的一份 Markdown（`# 段名` + 各页正文，
 * 页间 `\n\n`）。律师切段/并段时，页归属变了，正文必须跟着页走：头段留着已切出去
 * 那几页的文字就是污染，尾段不带正文就是丢失。md 里没有任何页标记，所以要么用
 * 后端给的 `page_spans`（精确），要么用 blocks 的页号在 md 里圈范围（近似）。
 *
 * ## 锚不到时不许静默漂移
 *
 * 所有函数在拿不到锚点时返回 null / -1，由调用方显式决定兜底并留下痕迹，
 * 而不是「悄悄按第一次匹配替换」——后者在印章核验语这类每页重复的文字上
 * 会改到别页去，比不改更糟。
 */

/** 一份正文 + 描述它的页锚点（偏移相对这份 md） */
interface MdSource {
  md: string
  spans: PageSpan[]
}

/** 搬运结果：新正文 + 重新计算过偏移的页锚点 */
export interface MdSlice {
  md: string
  pageSpans: PageSpan[]
}

/** 参与搬运的一段与它贡献的页（跨源合并时页号会重复，必须按段分开取） */
export interface MdPart {
  seg: Segment
  pages: PageKey[]
}

/** 收窄后端 `page_spans`：越界/非法偏移一律丢弃（按错偏移切正文比不切更糟） */
export function normalizePageSpans(raw: unknown, mdLength: number): PageSpan[] | null {
  if (!Array.isArray(raw)) return null
  const spans = raw.filter((item): item is PageSpan => {
    if (!item || typeof item !== 'object') return false
    const { page, start, end } = item as Record<string, unknown>
    return (
      typeof page === 'number' && Number.isInteger(page) && page >= 1 &&
      typeof start === 'number' && Number.isInteger(start) && start >= 0 &&
      typeof end === 'number' && Number.isInteger(end) && end > start && end <= mdLength
    )
  })
  if (!spans.length) return null
  return [...spans].sort((a, b) => a.start - b.start)
}

/** 块文字在 md 里的锚点串：整块匹配不上时退到首行（表格块的文字在 md 里被重排成 GFM） */
function anchorOf(md: string, text: string | undefined, cursor: number): { at: number; len: number } | null {
  const full = (text ?? '').trim()
  if (!full) return null
  const at = md.indexOf(full, cursor)
  if (at >= 0) return { at, len: full.length }
  const line = full.split('\n')[0]!.trim()
  // 首行太短就别拿它当锚：两三个字的碎片在整段里到处都能匹配上
  if (line.length < 4) return null
  const lineAt = md.indexOf(line, cursor)
  return lineAt >= 0 ? { at: lineAt, len: line.length } : null
}

/** 注入标题之后的正文起点：后端 md 恒以 `# 段名` 开头，页正文从第一个空行后开始 */
function contentStartOf(md: string): number {
  if (!md.startsWith('#')) return 0
  const at = md.indexOf('\n\n')
  return at >= 0 ? at + 2 : 0
}

/**
 * 旧任务兜底：用 blocks 的页号在 md 里近似圈出每页范围。
 *
 * 页区间取「本页首个锚得到的块」到「下一页首个锚得到的块」之间，而不是逐块
 * 精确匹配后拼接——表格块匹配不上是常态，按页界圈范围才能把整页正文都带上。
 * 首个锚点之前的正文归 blocks 的第一页（整页表格锚不到时，不能把它的文字
 * 算到后面某页头上）。
 */
function spansFromBlocks(md: string, blocks: PositionedBlock[]): PageSpan[] | null {
  const anchors: { page: number; start: number }[] = []
  let cursor = 0
  for (const b of blocks) {
    const hit = anchorOf(md, b.text, cursor)
    if (!hit) continue
    cursor = hit.at + hit.len
    // 同页只记首个锚点：页内后续块用来推进游标，不另起一页
    if (anchors[anchors.length - 1]?.page === b.page) continue
    anchors.push({ page: b.page, start: hit.at })
  }
  const first = anchors[0]
  if (!first) return null
  const spans: PageSpan[] = anchors.map((a, i) => ({
    page: a.page,
    start: a.start,
    end: anchors[i + 1]?.start ?? md.length,
  }))
  const leadPage = blocks[0]?.page
  const start = contentStartOf(md)
  if (leadPage !== undefined && start < first.start) {
    if (leadPage === first.page) spans[0] = { ...spans[0]!, start }
    else spans.unshift({ page: leadPage, start, end: first.start })
  }
  return spans
}

/** 段的页锚点：优先后端 `pageSpans`，缺失时用 blocks 页号近似；两者都没有返回 null */
export function pageSpansOf(seg: Segment): PageSpan[] | null {
  const md = seg.md
  if (!md) return null
  return normalizePageSpans(seg.pageSpans, md.length) ?? (seg.blocks?.length ? spansFromBlocks(md, seg.blocks) : null)
}

/** 某页正文在 md 里的区间；锚不到返回 null */
export function pageRegionOf(seg: Segment, page: number): { start: number; end: number } | null {
  const own = pageSpansOf(seg)?.filter((s) => s.page === page)
  if (!own?.length) return null
  return { start: own[0]!.start, end: own[own.length - 1]!.end }
}

/**
 * 块原文在 md 里的**精确**位置：先圈到该页区间，再取「同页同文的第 n 次出现」。
 *
 * 为什么不能只用 `md.indexOf(oldText)`：印章核验语（「已核对与原件相符…」）
 * 一页里就可能出现多次、整段里出现几十次，首次匹配会改到别处去。
 * 块序即阅读序，所以同页同文的第几个块就该改第几个匹配。
 *
 * 返回 -1 = 锚不到，调用方必须显式标记不同步。
 */
export function blockTextIndexOf(seg: Segment, blockIndex: number, oldText: string): number {
  const md = seg.md
  const block = seg.blocks?.[blockIndex]
  if (!md || !oldText || !block) return -1
  const region = pageRegionOf(seg, block.page)
  const limit = region?.end ?? md.length
  const ordinal = (seg.blocks ?? [])
    .slice(0, blockIndex)
    .filter((b) => b.page === block.page && (b.text ?? '') === oldText).length
  let at = (region?.start ?? 0) - 1
  for (let n = 0; n <= ordinal; n += 1) {
    at = md.indexOf(oldText, at + 1)
    if (at < 0 || at + oldText.length > limit) return -1
  }
  return at
}

/** md 被局部替换后平移页锚点：改动点之前的不动，之后的整体挪 delta，含改动点的那页只改 end */
export function shiftPageSpans(spans: PageSpan[], at: number, oldLen: number, newLen: number): PageSpan[] {
  const delta = newLen - oldLen
  const cut = at + oldLen
  return spans.map((s) => {
    if (s.end <= at) return s
    if (s.start >= cut) return { ...s, start: s.start + delta, end: s.end + delta }
    return { ...s, end: Math.max(s.start + 1, s.end + delta) }
  })
}

/**
 * 按页序拼接各段贡献的正文，并重算页锚点偏移。
 *
 * `keepPrefix` 时带上第一段首页正文之前的前缀（后端注入的 `# 段名`；后端认定标题
 * 与正文首行重复时不注入，前缀就是空串）：切段的头段沿用原段身份所以留着；
 * 并段/切出的新段是新身份，旧段名不跟过去（文不对题）。
 *
 * 页间分隔符**沿用源 md**：后端把跨页续表合并时用的是 `\n` 而不是 `\n\n`，
 * 硬塞空行会把一张表拆成两张（续表行丢掉表头）。
 *
 * 任一段拿不到锚点就整体返回 null——半精确拼接会静默丢字，不如让调用方走兜底。
 */
export function joinMdByPages(parts: MdPart[], keepPrefix = false): MdSlice | null {
  const sources: { src: MdSource; pages: PageKey[] }[] = []
  for (const part of parts) {
    const spans = pageSpansOf(part.seg)
    if (!spans || !part.seg.md) return null
    sources.push({ src: { md: part.seg.md, spans }, pages: part.pages })
  }
  let md = ''
  const pageSpans: PageSpan[] = []
  const push = (text: string, page?: number, sep = '\n\n') => {
    const body = text.trim()
    if (!body) return
    if (md) md += sep
    const start = md.length
    md += body
    if (page !== undefined) pageSpans.push({ page, start, end: md.length })
  }
  const first = sources[0]
  if (keepPrefix && first) push(first.src.md.slice(0, first.src.spans[0]!.start))
  for (const { src, pages } of sources) {
    const seen = new Set<number>()
    let prevEnd = -1
    for (const { p } of pages) {
      if (seen.has(p)) continue
      seen.add(p)
      const own = src.spans.filter((s) => s.page === p)
      if (!own.length) continue
      const start = own[0]!.start
      const end = own[own.length - 1]!.end
      // 只有「同源、顺序相邻、间隔纯空白」才沿用原分隔符；跨源/倒序一律按段间空行
      const gap = prevEnd >= 0 && start >= prevEnd ? src.md.slice(prevEnd, start) : ''
      push(src.md.slice(start, end), p, /^\s+$/.test(gap) ? gap : '\n\n')
      prevEnd = end
    }
  }
  return { md, pageSpans }
}

/**
 * 按页号把定位块分给新段。
 *
 * `blocks[].page` 与 `refs[].p` 同口径（文档内绝对页号，见 Flow.tsx 的解引用），
 * 所以按页号匹配而不是「页号 - 段起始页」当下标——删页/切出后 refs 会跳号。
 */
export function blocksForPages(
  blocks: PositionedBlock[] | undefined,
  pages: PageKey[],
): PositionedBlock[] | undefined {
  if (!blocks?.length) return undefined
  const own = new Set(pages.map((r) => r.p))
  const next = blocks.filter((b) => own.has(b.page))
  return next.length ? next : undefined
}

/** 整份正文按段序拼接（页锚点缺失时的并段兜底：不丢字，但偏移未知） */
export function joinWholeMd(segs: Segment[]): string | undefined {
  return segs.map((sg) => sg.md).filter(Boolean).join('\n\n') || undefined
}

/** 定位块按段序合并（页号即文档内绝对页号，拼接后天然是页序） */
export function concatBlocks(
  a: PositionedBlock[] | undefined,
  b: PositionedBlock[] | undefined,
): PositionedBlock[] | undefined {
  const next = [...(a ?? []), ...(b ?? [])]
  return next.length ? next : undefined
}
