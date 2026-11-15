import type {
  EngineDisagreement,
  Inconsistency,
  PageQuality,
  Segment,
} from '../types'
import { docTypeLabel, qualityFlagLabel } from './quality'

/**
 * 复核清单的数据层：把分散在四个字段里的待复核信号归一成同一种 `ReviewItem[]`。
 *
 * ═══ 为什么必须归一 ═══
 * 律师打开材料包看到的是「第31页」「第23页」这些页卡，而「这页要复核什么」散在
 * `engineDisagreements`（双引擎分歧）、`pageQuality.doc_missing` / `graphic_pages` /
 * `sparse_pages`（识别质量）、`inconsistencies`（跨页不一致）、`seg.qualityFlags`
 * （段级标记）四处。UI 若是逐处各取各的，就会出现「页头徽标说 3 项、抽屉里只列出
 * 2 项」这种自相矛盾——律师只会认为这个功能不可信。所以先在这里合成一张表，
 * 页头徽标、抽屉、正文批注、页面框全部只读这一张表，数字天然一致。
 *
 * ═══ 幂等与稳定 id ═══
 * 「已核对」状态要跨刷新持久化（`DraftState.reviewChecked`），所以 id 只能由**内容**
 * 决定：用数组下标的话，后端重跑一次识别、顺序一换，勾就挂到别的条目上了——
 * 律师会以为自己核对过，而这恰恰是复核清单唯一不能出的错。
 */

/** 复核项的类型，决定颜色与图标 */
export type ReviewItemKind =
  | 'disagreement'
  | 'doc_missing'
  | 'graphic'
  | 'sparse'
  | 'inconsistency'
  | 'quality'

/** 一条待复核项。所有信号源最终都归一成这个形状。 */
export interface ReviewItem {
  /** 稳定 key，用于「已核对」持久化。见 `reviewItemId` */
  id: string
  kind: ReviewItemKind
  /** 绝对页号 */
  page: number
  /** 严重度：决定排序与颜色 */
  severity: 'high' | 'medium' | 'low'
  /** 一句话标题，如「引擎分歧：曾妙焮 / 曾妙焱」 */
  title: string
  /** 明细（可空），如两个引擎的原文对照 */
  detail?: string
  /** 原文片段，用于在 Markdown 正文里定位 */
  needle?: string
  /** 原图上的位置（归一化 0-1），用于画框；没有就不画 */
  rect?: { x: number; y: number; w: number; h: number }
  /** 是否含身份证号等锚点，优先展示 */
  anchor?: boolean
}

const SEVERITY_RANK: Record<ReviewItem['severity'], number> = { high: 0, medium: 1, low: 2 }
const KIND_RANK: Record<ReviewItemKind, number> = {
  disagreement: 0,
  doc_missing: 1,
  inconsistency: 2,
  quality: 3,
  graphic: 4,
  sparse: 5,
}

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
 * 多段文本拼成 id 签名。
 *
 * 只在段间加分隔符、去掉空白与空段：**不做排序**——同一处文字的原文/明细谁在前
 * 是有语义的（原文定位优先），而顺序本身是稳定的。会随重跑漂移的东西（引擎变体的
 * 给出顺序）在调用处就**先排序**再传进来，见 `disagreementNeedle`。
 */
function signatureOf(parts: string[]): string {
  return parts
    .map((p) => p.trim())
    .filter((p) => p.length > 0)
    .join('|')
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

/**
 * kind → id 短码。
 *
 * 写死成短串而不是直接拼 kind 全名：这些键会进草稿的 `reviewChecked`，要能一眼读懂；
 * 也正因为它进了持久化数据，**改动任一短码就等于让已存的「已核对」全部失效**，
 * 所以这份映射是持久化契约，不是随手可调的文案。
 */
const ID_PREFIX: Record<ReviewItemKind, string> = {
  disagreement: 'dis',
  doc_missing: 'docmiss',
  graphic: 'graphic',
  sparse: 'sparse',
  inconsistency: 'incon',
  quality: 'quality',
}

/**
 * 生成一条复核项的稳定 id：`<kind 短码>:<页号>:<内容签名>`。
 *
 * 签名取自**内容**（原文片段 → 明细 → 标题，取第一个非空的），不用数组下标：
 * 后端重跑一次识别、顺序一换，按下标存的勾就挂到别的条目上了——律师会以为
 * 自己核对过，而这恰恰是复核清单唯一不能出的错。
 *
 * 为什么不用哈希：id 会进草稿 JSON，可读的键在排查「勾错了哪条」时能直接看懂，
 * 而 `<页号>:<原文>` 本身已经足够唯一。
 */
export function reviewItemId(item: Omit<ReviewItem, 'id'>): string {
  const short = ID_PREFIX[item.kind] ?? item.kind
  // 只取「原文片段」与「标题」：`detail` 是对照文案（"mineru=X / paddleocr_vl=Y"），
  // 引擎给出顺序一变它就变，拿它做 id 会让同一处分歧重跑后算成两条。
  const sig = signatureOf([item.needle ?? '', item.title])
  return sig ? `${short}:${item.page}:${sig}` : `${short}:${item.page}`
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

/**
 * 排序：severity 降序，同 severity 按页升序。
 *
 * 同严重度同页时再按 kind 与 id 兜底：排序必须是**全序**，否则相同输入的两次调用
 * 可能给出不同顺序（后端数组顺序变了就变），列表会在律师眼皮底下跳动。
 */
export function sortReviewItems(items: ReviewItem[]): ReviewItem[] {
  return [...items].sort((a, b) => {
    const ra = SEVERITY_RANK[a.severity] ?? SEVERITY_RANK.low
    const rb = SEVERITY_RANK[b.severity] ?? SEVERITY_RANK.low
    if (ra !== rb) return ra - rb
    if (a.page !== b.page) return a.page - b.page
    const ka = KIND_RANK[a.kind] ?? 99
    const kb = KIND_RANK[b.kind] ?? 99
    if (ka !== kb) return ka - kb
    return a.id < b.id ? -1 : a.id > b.id ? 1 : 0
  })
}

/**
 * 按页分组（页号升序），页内沿用 `sortReviewItems` 的顺序。
 *
 * 抽屉与页头徽标共用这个分组：徽标上的数字就是 `items.length`，
 * 点开抽屉看到的第一组就是这一页——两边数字对上，律师才信这个计数。
 */
export function groupByPage(items: ReviewItem[]): { page: number; items: ReviewItem[] }[] {
  const sorted = sortReviewItems(items)
  const groups = new Map<number, ReviewItem[]>()
  for (const item of sorted) {
    const list = groups.get(item.page)
    if (list) list.push(item)
    else groups.set(item.page, [item])
  }
  // Map 保持插入顺序，而 sorted 已按页升序，所以这里天然是升序
  return [...groups.entries()].map(([page, list]) => ({ page, items: list }))
}
