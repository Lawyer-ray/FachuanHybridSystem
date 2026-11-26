import { AlertTriangle } from 'lucide-react'

import { docTypeLabel, qualityFlagLabel, type SegmentReviewHint } from '../../draft'
import type { ColumnAnomaly } from '../../types'

/** 提示条的统一外壳：淡灰底 + 灰图标。复核用的是琥珀壳（它要的是动作，不是陈述） */
const HINT_CLS =
  'flex items-start gap-1.5 rounded-lg border border-zinc-200 bg-secondary/40 px-2.5 py-1.5 text-left text-[11px] leading-relaxed text-muted-foreground'

/** 复核提示的壳：琥珀色。与段头「建议复核」徽标、左栏三角标同一套语义色 */
const REVIEW_CLS =
  'flex items-start gap-1.5 rounded-lg border border-amber-300 bg-amber-50/60 px-2.5 py-1.5 text-left text-[11px] leading-relaxed text-amber-800'

/** 内联在正文里的单页提示：比栏顶提示条更轻，不抢正文本体的行距 */
const PAGE_CLS =
  'flex items-start gap-1.5 rounded-lg border border-zinc-200 bg-secondary/40 px-2.5 py-1.5 text-left text-[11px] leading-relaxed text-muted-foreground'

/** 本段覆盖到的证件页（页号 + 证件类型码 + 该页缺的字段） */
export interface DocHintPage {
  page: number
  doc: string
  /** 未读出的字段；空数组 / 缺省 = 类型认出来了但说不出缺哪个字段 */
  missing?: string[]
}

/**
 * 右栏正文面板**顶部**的段级提示条。
 *
 * 这里只剩两类「与具体某页无关」的信号：
 *
 * - **建议复核**：自动分段把边界或名字定错了，错的可能是整段（切错边界＝把别的
 *   材料末尾混进来），不是某一页的问题。它必须写在律师开始读之前。
 * - **quality_flags 兜底**：老任务没有逐页质量画像，只剩后端一个段级标记
 *   （文字稀疏 / 空白页）。有逐页数据时那些提示走 `SegmentPageHint` 挂到对应页。
 *
 * ## 逐页问题为什么不在这里
 *
 * 证件页缺字段、某页是图纸——这些**对应到具体一页**的信号堆在栏顶会变成一张清单，
 * 律师要自己在正文里找「P31 在哪」。同一段里已经有双引擎分歧做过示范：挂到该页
 * 正文第一行之前，读到哪页就看到那页的问题。所以它们搬去了 `SegmentPageHint`。
 *
 * ## 配色
 *
 * 图纸 / 证件页 / 退化页 / 列数突变页都不上彩色语义：这不是错误，只是「你看到的
 * 正文不等于原件全部内容」的事实陈述。复核用琥珀色，因为它要的是**动作**（去核对）。
 */
export function SegmentQualityHint({
  review = null,
  flags = [],
}: {
  /** 段级复核信号（`reviewHintOf(seg)`）；null = 这一段不需要复核 */
  review?: SegmentReviewHint | null
  /** 后端给的段级质量标记（未知取值原样展示，不丢信息） */
  flags?: string[]
}) {
  // 没有逐页画像的老任务：后端只给段级标记，只能整段说一句
  const flagText =
    flags.length > 0 ? `本段识别质量偏低（${[...new Set(flags.map(qualityFlagLabel))].join('、')}）· 建议核对原页` : ''
  if (!review && !flagText) return null

  return (
    <div className="flex flex-col gap-1">
      {review && <ReviewRow review={review} />}
      {flagText && (
        <div data-quality-hint className={HINT_CLS}>
          <AlertTriangle className="mt-0.5 h-3 w-3 flex-none opacity-60" aria-hidden />
          <span>{flagText}</span>
        </div>
      )}
    </div>
  )
}

/**
 * 段级复核提示：「⚠ 建议复核 · 起点是按版面标题推断的，可能把上一份的末尾切进来 ·
 * 自动分段置信度 62% · 请核对本段起止页与材料名」。
 *
 * 尾巴那句「核对什么」固定带上：复核标签本身不是行动指引，律师看完原因还得知道
 * 具体该动哪两样（边界、名字）。
 */
function ReviewRow({ review }: { review: SegmentReviewHint }) {
  return (
    <div data-review-hint className={REVIEW_CLS}>
      <AlertTriangle className="mt-0.5 h-3 w-3 flex-none text-amber-600" aria-hidden />
      <span>
        <span className="font-medium">{review.label}</span>
        {review.reason ? `：${review.reason}` : ''}
        {' · 请核对本段起止页与材料名'}
      </span>
    </div>
  )
}

/**
 * 退化页那行：**带页号**，因为这类提示最常出现在 orphan 位置（正文之后补一行，
 * 该页整页没有正文），而那时行里只有「本页」两个字，律师不知道是哪一页。
 *
 * 措辞只说「已换识别路径重取」，不说「已改用本地识别」——后端只承诺
 * 「判为退化 → 清空 → 扔回 pending 走兜底链」，最终可能是下一个云端候选接手、
 * 也可能是 PDF 文本层补齐，甚至本地兜底也会失败（此时该页同时进 ocr_failed）。
 * 说成「本地识别兜底」会在这些情形下变成一句假话。
 */
function degenerateTextOf(page: number): string {
  return `P${page} 云端取字判为退化，已换识别路径重取 · 建议核对原页`
}

/**
 * **一页**的「需要核对」提示，挂在 Markdown 里这一页正文的第一行之前。
 *
 * 与双引擎分歧同一落点（`SegmentMarkdown` 按 `isFirstOfPage` 插入）：律师读到那一页
 * 的时候，问题就在头顶上，不用去栏顶比页号、再回来找位置。
 *
 * 「这页是图纸」与「这页是身份证但姓名没读出」必须两句话：前者本来就没字，看一眼
 * 原图即可；后者有字但没读出来，而姓名 / 身份证号 / 住址是必须抄进卷宗的字段。
 * 混成一句会让人以为证件页也跟图纸一样不用管。退化页 / 列数突变页同理——一个说
 * 「这页的字换了识别路径」，一个说「这页的数字可能挂在错的表头下」，都单独成行。
 *
 * 行序按严重度：正文根本不可信（退化）> 数字可能挂错表头（列数突变）> 字段没读出
 * （证件）> 内容不完整（图纸）。与左栏段行标记的优先级阶梯同一口径。
 */
export function SegmentPageHint({
  page,
  doc,
  graphic = false,
  degenerate = false,
  columnAnomaly = null,
  onGotoPage,
}: {
  page: number
  /** 这一页的证件类型 + 未读出字段（`page_quality.doc_hints`） */
  doc?: DocHintPage
  /** 这一页疑似图纸 / 照片（`page_quality.graphic_pages`） */
  graphic?: boolean
  /** 这一页云端取字判为退化、正文已改由本地 OCR 兜底（`summary.degenerate_pages`） */
  degenerate?: boolean
  /** 这一页表格列数与上一页不同（`summary.table_geometry.column_anomalies`） */
  columnAnomaly?: ColumnAnomaly | null
  /** 点提示跳原页；不传则只陈述、不可点 */
  onGotoPage?: (page: number) => void
}) {
  if (!doc && !graphic && !degenerate && !columnAnomaly) return null
  return (
    <>
      {degenerate && (
        <PageRow page={page} text={degenerateTextOf(page)} onGotoPage={onGotoPage} mark="degenerate" />
      )}
      {columnAnomaly && (
        <PageRow
          page={page}
          text={columnAnomalyTextOf(columnAnomaly)}
          onGotoPage={onGotoPage}
          mark="column"
        />
      )}
      {doc && <PageRow page={page} text={docTextOf(doc)} onGotoPage={onGotoPage} mark="doc" />}
      {graphic && (
        <PageRow
          page={page}
          text={`P${page} 疑似图纸 / 照片，正文可能不完整 · 建议核对原页`}
          onGotoPage={onGotoPage}
          mark="graphic"
        />
      )}
    </>
  )
}

/**
 * 列数突变那行：必须把「本页几列 vs 上一页几列」并排放出来。
 *
 * 只说「列数异常」律师无法判断该不该信这页的表格；给了两组数字，他翻原页时
 * 一眼就能对上。页号沿用本文件既有的 `P{页号}` 写法（与证件 / 图纸行一致）。
 */
function columnAnomalyTextOf(a: ColumnAnomaly): string {
  // 「列被并/拆」是后端判据的原话（并/拆列会让数字挂到错误表头下）；
  // 「并列」是内部口语，律师读不出含义。同时保留「换了表格模板」这一种可能。
  return `P${a.page_no} 表格 ${a.cols} 列，上一页 P${a.prev_page_no} 为 ${a.prev_cols} 列 · 列可能被并/拆或换了模板，请核对数字表头`
}

/** 证件页那一行说清三件事：第几页 / 是什么证件 / 缺了哪些字段 */
function docTextOf(doc: DocHintPage): string {
  const label = docTypeLabel(doc.doc)
  // 字段用「 / 」分隔而不是顿号：字段名本身可能带顿号（「姓名、曾用名」），
  // 再用顿号分项就分不清哪是字段、哪是分隔。
  const missing = doc.missing && doc.missing.length > 0 ? `，缺：${doc.missing.join(' / ')}` : '，关键字段可能未读出'
  return `P${doc.page} ${label}${missing} · 建议核对原页`
}

/** 提示行的种类 → `<div>`/`<button>` 上的 data 属性（测试与样式靠它区分是哪一类） */
const HINT_ATTR = {
  doc: { 'data-doc-hint': '' },
  graphic: { 'data-quality-hint': '' },
  degenerate: { 'data-degenerate-hint': '' },
  column: { 'data-column-anomaly-hint': '' },
} as const

/** 单行提示：可点时整行是按钮（提示要能一步回到原件，否则律师还得自己翻） */
function PageRow({
  page,
  text,
  onGotoPage,
  mark,
}: {
  page: number
  text: string
  onGotoPage?: (page: number) => void
  mark: keyof typeof HINT_ATTR
}) {
  const body = (
    <>
      <AlertTriangle className="mt-0.5 h-3 w-3 flex-none opacity-60" aria-hidden />
      <span>{text}</span>
    </>
  )
  const dataAttr = HINT_ATTR[mark]
  if (!onGotoPage) {
    return (
      <div {...dataAttr} className={PAGE_CLS}>
        {body}
      </div>
    )
  }
  return (
    <button
      type="button"
      {...dataAttr}
      title={`跳到原页 P${page}`}
      onClick={() => onGotoPage(page)}
      className={`${PAGE_CLS} cursor-pointer transition-colors hover:bg-secondary/70 hover:text-foreground`}
    >
      {body}
    </button>
  )
}
