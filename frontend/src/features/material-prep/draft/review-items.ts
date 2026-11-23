/**
 * 复核清单的**信号归一**：把四类来源（引擎分歧 / 页级质量 / 跨页不一致 / 段级标记）
 * 提取成同一种 `ReviewItem[]`。
 *
 * 产出顺序是本模块的**信号源顺序**（分歧 → 证件页 → 图形 → 稀疏 → 不一致 → 段标记）；
 * 展示排序在 `review-sort.ts`，不在这里做——调用方有时要的是「按信号源分组」，
 * 排序是无损后处理。
 */
import type {
  EngineDisagreement,
  Inconsistency,
  PageQuality,
  Segment,
} from '../types'
import { docTypeLabel, qualityFlagLabel } from './quality'
import { reviewItemId } from './review-ids'
import type { ReviewItem } from './review-ids'

function isSeverity(v: unknown): v is ReviewItem['severity'] {
  return v === 'high' || v === 'medium' || v === 'low'
}

/**
 * 页号是否为有效页：后端偶有 page_no=0（未定位的块）与 `doc_missing` 里非数字的键，
 * 这类条目跳不过去、也算不出属于哪一段，留着只会在清单里制造一条点不动的行。
 */
function isPage(page: number): boolean {
  return Number.isFinite(page) && page > 0
}

/**
 * 一条分歧的定位原文（`needle`）。
 *
 * 排序所有非空变体文本：后端重跑时两个引擎的变体顺序可能互换，若按原顺序拼进 id，
 * 同一处分歧会算出两个 id，律师勾过的「已核对」就白勾了。
 * 有 `context`（分歧处的截断原文）时以它为主——正文批注要在 Markdown 里做包含匹配，
 * 它比孤立的两个字更可能匹配上。
 */
function disagreementNeedle(d: EngineDisagreement): string {
  const texts = [...disagreementTexts(d)].sort()
  return d.context.trim() || texts.join(' / ')
}

/** 某段覆盖的绝对页号集合（跨源合并段的 refs 页号会重复，去重即可） */
function pagesOfSegment(seg: Pick<Segment, 'refs'>): Set<number> {
  const out = new Set<number>()
  for (const ref of seg.refs) {
    if (isPage(ref.p)) out.add(ref.p)
  }
  return out
}

/** 引擎变体 → 「MinerU: 曾妙焮 / VL: 曾妙焱」的对照明细 */
function variantsDetail(d: EngineDisagreement): string {
  return d.variants
    .map((v) => `${v.engine}=${v.text || '（无此行）'}`)
    .join(' / ')
}

/**
 * 一条分歧的两个显著文本（取前两个非空变体），用于标题与 id 签名。
 *
 * `missing` 类里空串代表「该引擎没有这一行」，不参与签名——否则同一处分歧在
 * 后端补上另一个引擎的空变体后 id 就变了。
 */
function disagreementTexts(d: EngineDisagreement): string[] {
  return d.variants.map((v) => v.text.trim()).filter((t) => t.length > 0)
}

/**
 * 分歧标题：`引擎分歧：张三丰 / 張三丰`。
 *
 * 两个写法**排序后**再拼：标题同时参与 `reviewItemId` 的签名，而后端重跑时变体顺序
 * 可能互换——不排序就会让同一处分歧算出两个 id，律师勾过的「已核对」白勾。
 * 排序在这里不丢信息：本域的立场是「只摆出分歧、不投票」（见 `draft/engine.ts` 文件头），
 * 谁在前都没有「更正确」的含义，而乱序的代价是勾错条目。
 */
function disagreementTitle(d: EngineDisagreement, texts: string[]): string {
  if (texts.length > 0) return `引擎分歧：${[...texts].sort().join(' / ')}`
  // 两边都没给出文本（极端脏数据）也要能看出这是哪类问题
  return d.kind === 'missing' ? '引擎分歧：仅一侧有内容' : '引擎分歧'
}

/**
 * 分歧自带的块框里取第一个可用于画框的矩形。
 *
 * 取第一个而**不是合并全部**：一条分歧对应的是原图上**一处**文字，画出几个框会让
 * 律师以为有多处要核对。后端若有多个引擎的块框（同名文字各引擎各给一个），
 * 选第一个（MinerU，主引擎）最稳。
 */
function firstRectOf(d: EngineDisagreement): ReviewItem['rect'] {
  const block = (d.blocks ?? []).find((b) => b.rect.w > 0 && b.rect.h > 0)
  if (!block) return undefined
  const { x, y, w, h } = block.rect
  return { x, y, w, h }
}

/** 构造一条复核项：id 一律经 `reviewItemId`，调用方不许自己拼 id（拼法要唯一一致） */
function makeItem(item: Omit<ReviewItem, 'id'>): ReviewItem {
  return { ...item, id: reviewItemId(item) }
}

/** 引擎分歧：只收属于本段的页（段边界之外的页跳到邻段页卡上，等于误导航） */
function disagreementItems(
  list: EngineDisagreement[],
  pages: Set<number>,
): ReviewItem[] {
  const out: ReviewItem[] = []
  for (const d of list) {
    if (!isPage(d.page_no) || !pages.has(d.page_no)) continue
    const texts = disagreementTexts(d)
    out.push(
      makeItem({
        kind: 'disagreement',
        page: d.page_no,
        severity: isSeverity(d.severity) ? d.severity : 'low',
        title: disagreementTitle(d, texts.slice(0, 2)),
        detail: variantsDetail(d),
        // 正文批注靠这段原文在 Markdown 里做包含匹配，所以优先用命中处的截断原文；
        // 它为空时才退到排序后的识别文本（见 `disagreementNeedle` 的 id 稳定性说明）
        needle: disagreementNeedle(d),
        rect: firstRectOf(d),
        anchor: d.anchor_hit,
      }),
    )
  }
  return out
}

/** 证件页缺字段：`doc_missing` 的键即页号；`missing: []` 也是信号（字段都在但整页可疑） */
function docMissingItems(
  quality: PageQuality | undefined,
  pages: Set<number>,
): ReviewItem[] {
  const out: ReviewItem[] = []
  const hints = quality?.doc_hints ?? {}
  for (const [key, entry] of Object.entries(quality?.doc_missing ?? {})) {
    const page = Number(key)
    if (!isPage(page) || !pages.has(page)) continue
    const doc = entry.doc || hints[key] || ''
    const label = doc ? docTypeLabel(doc) : ''
    const missing = (entry.missing ?? []).filter((m) => !!m)
    // 空 missing 不能当成「没问题」：后端用它表示「类型认出来了、字段也在，但整页内容
    // 可疑（如满是乱码）」，律师需要看一眼原页。文案要说清是「整页可疑」而不是「缺 0 个字段」
    const missingText = missing.length > 0 ? missing.join('、') : '整页内容可疑'
    out.push(
      makeItem({
        kind: 'doc_missing',
        page,
        severity: 'high',
        title: label ? `${label}缺字段：${missingText}` : `证件页待核对：${missingText}`,
        detail: label ? `第${page}页 ${label}` : undefined,
        needle: missing.length > 0 ? missing[0] : undefined,
      }),
    )
  }
  return out
}

/** 图形页 / 稀疏页：数组元素就是页号，按段范围过滤 */
function pageListItems(
  kind: 'graphic' | 'sparse',
  list: number[] | undefined,
  pages: Set<number>,
  quality: PageQuality | undefined,
): ReviewItem[] {
  const out: ReviewItem[] = []
  const isGraphic = kind === 'graphic'
  // 同一页可能在 graphic_pages 里出现两次（跨源合并段的脏数据），按页去重，
  // 避免同一页列两条一模一样的项——页头徽标会因此多算一项
  const seen = new Set<number>()
  for (const page of list ?? []) {
    if (!isPage(page) || !pages.has(page) || seen.has(page)) continue
    seen.add(page)
    // 后端常给逐页说明（"疑似图形页（图纸/印章/照片），请核对原图"），有就用作标题，
    // 它比前端硬编码的文案更具体（可能指出是哪类图）
    const hint = quality?.details?.[String(page)]
    out.push(
      makeItem({
        kind,
        page,
        severity: isGraphic ? 'medium' : 'low',
        title: hint || (isGraphic ? '图形页：请核对原图' : '文字稀疏：请核对原图'),
      }),
    )
  }
  return out
}

/**
 * 跨页不一致：一条不一致可能横跨多页，**每页各出一条**。
 *
 * 为什么拆开而不是只在第一页挂一条：页头徽标是按页计数的，若只在 pages[0] 挂，
 * 律师翻到第 3 页时那页看起来毫无问题，而实际上那页上的章就是错字。
 * 拆开后每页各自能核对、各自能跳转。
 */
function inconsistencyItems(
  list: Inconsistency[],
  pages: Set<number>,
): ReviewItem[] {
  const out: ReviewItem[] = []
  for (const inc of list) {
    const seen = new Set<number>()
    for (const page of inc.pages) {
      if (!isPage(page) || !pages.has(page) || seen.has(page)) continue
      seen.add(page)
      out.push(
        makeItem({
          kind: 'inconsistency',
          page,
          severity: 'high',
          title: `写法不一致：${inc.canonical} / ${inc.variant}`,
          detail: `「${inc.canonical}」${inc.canonical_count} 次 / 「${inc.variant}」${inc.variant_count} 次`,
          // 疑似错字那个写法才是要在正文里找的东西
          needle: inc.variant,
        }),
      )
    }
  }
  return out
}

/**
 * 段级质量标记：挂在**段首页**。
 *
 * 后端只给到段粒度（`quality_flags` 是整段的），没有页号可依，所以归到首页——
 * 律师点「跳转」至少能落在这段的开头，而不是无页可跳。已在页级清单里出现过的
 * 同类问题（某页既在 `graphic_pages` 里、段又被标了 `graphic`）仍然各出一条：
 * 前者说「这页是图」，后者说「整段识别质量存疑」，是两件事。
 */
function qualityFlagItems(seg: Segment): ReviewItem[] {
  const flags = (seg.qualityFlags ?? []).filter((f) => typeof f === 'string' && !!f)
  const page = seg.refs[0]?.p
  // 没有页可挂的段（refs 全坏）不产出条项：无处跳转的复核项只会让律师白点
  if (page === undefined || !isPage(page)) return []
  const seen = new Set<string>()
  const out: ReviewItem[] = []
  for (const flag of flags) {
    if (seen.has(flag)) continue
    seen.add(flag)
    out.push(
      makeItem({
        kind: 'quality',
        page,
        severity: 'medium',
        title: `识别质量标记：${qualityFlagLabel(flag)}`,
        detail: `第${page}–${seg.refs[seg.refs.length - 1]?.p ?? page}页所在段`,
      }),
    )
  }
  return out
}

/**
 * 把一段的所有待复核信号归一成清单。
 *
 * 四个信号源全部可选：旧任务的 summary 里没有 page_quality / inconsistencies，
 * 单引擎路径没有 engine_disagreements，人工拆分的段没有 quality_flags。
 * 任何一个缺失都只是少一类项，不能让整张清单消失。
 *
 * 返回顺序是本函数的**产出顺序**（分歧 → 证件页 → 图形 → 稀疏 → 不一致 → 段标记）；
 * 要按严重度展示请再过一遍 `sortReviewItems`——不在这里排，是因为调用方有时要的是
 * 「按信号源分组」，排序是无损后处理。
 */
export function reviewItemsOf(
  seg: Segment,
  pageQuality?: PageQuality,
  engineDisagreements?: EngineDisagreement[],
  inconsistencies?: Inconsistency[],
): ReviewItem[] {
  const pages = pagesOfSegment(seg)
  if (pages.size === 0) return []
  return [
    ...disagreementItems(engineDisagreements ?? [], pages),
    ...docMissingItems(pageQuality, pages),
    ...pageListItems('graphic', pageQuality?.graphic_pages, pages, pageQuality),
    ...pageListItems('sparse', pageQuality?.sparse_pages, pages, pageQuality),
    ...inconsistencyItems(inconsistencies ?? [], pages),
    ...qualityFlagItems(seg),
  ]
}
