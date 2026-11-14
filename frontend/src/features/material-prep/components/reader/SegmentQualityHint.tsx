import { AlertTriangle } from 'lucide-react'

import { docTypeLabel, pagesText, qualityFlagLabel } from '../../draft/quality'

/** 一条提示的视觉壳：淡灰底 + 灰图标，交互态与宽屏口一视同仁 */
const HINT_CLS =
  'flex items-start gap-1.5 rounded-lg border border-zinc-200 bg-secondary/40 px-2.5 py-1.5 text-left text-[11px] leading-relaxed text-muted-foreground'

/** 本段覆盖到的证件页（页号 + 证件类型码 + 该页缺的字段） */
export interface DocHintPage {
  page: number
  doc: string
  /** 未读出的字段；空数组 / 缺省 = 类型认出来了但说不出缺哪个字段 */
  missing?: string[]
}

/**
 * 右栏正文面板顶部的质量提示条。
 *
 * ## 两类提示，语气必须分开
 *
 * - **图纸页**：「本段含 N 页疑似图纸，正文可能不完整」——这页**本来就没字**，
 *   正文不全是正常的，看一眼原图即可。
 * - **证件页**：「P23 是身份证，姓名 / 身份证号 / 住址 未读出」——这页**有字但没
 *   读出来**，而姓名、身份证号、住址是律师必须抄进卷宗的字段。说成「疑似图纸、
 *   正文可能不完整」会让人以为跟图纸一样不用管，正好漏掉最该补的东西。
 *
 * 所以证件页单独成行、逐页说清缺什么，而不是混进上面那句手机文案里。
 *
 * ## 为什么单独成组件
 *
 * 文案拼装（图形页 / 稀疏页 / 后端 quality_flags / 证件页四种来源并存的去重）有
 * 自己的一套规则，塞进 `SegmentMarkdown` 会把这个已经承载「对照、编辑、可疑点」
 * 三件事的面板再顶高一档，也让那段文案没法单测。
 *
 * ## 配色
 *
 * 不上彩色语义：淡灰底 + 灰图标，与删掉彩色类型圆点的决定一致。这不是错误，
 * 只是「你看到的正文不等于原件全部内容」的事实陈述。
 *
 * 点整条跳原页（多页时跳到第一页）：提示要能一步回到原件，否则律师还得自己去翻。
 */
export function SegmentQualityHint({
  flags = [],
  graphicPages = [],
  docPages = [],
  onGotoPage,
}: {
  /** 后端给的段级质量标记（未知取值原样展示，不丢信息） */
  flags?: string[]
  /** 本段覆盖的疑似图形页 */
  graphicPages?: number[]
  /** 本段覆盖的证件页（`page_quality.doc_hints` 收窄而来；旧任务为空） */
  docPages?: DocHintPage[]
  /** 点提示条跳原页；不传则只陈述、不可点 */
  onGotoPage?: (page: number) => void
}) {
  const parts: string[] = []
  if (graphicPages.length > 0) parts.push(`含 ${graphicPages.length} 页疑似图纸`)
  // 没有图形页时，把后端标记里除图形页之外的（稀疏 / 空白 / 未知）说出来。
  // 两者都有时以图形页为主：同一句话里再堆「文字稀疏」只会让主信息变糊。
  if (parts.length === 0 && flags.length > 0) {
    const labels = [...new Set(flags.map(qualityFlagLabel))]
    parts.push(`识别质量偏低（${labels.join('、')}）`)
  }

  const graphicText = parts.length > 0 ? `本段${parts.join('，')}，正文可能不完整 · 建议核对原页` : ''
  if (!graphicText && docPages.length === 0) return null

  return (
    <div className="flex flex-col gap-1">
      {/* 证件页在前：缺的是「必须抄进卷宗的字段」，比「这一页看不出内容」更该先处理 */}
      {docPages.map((d, i) => (
        <DocHintRow
          // 跨源合并段同一页可能出现两次，用下标兜底保证 key 唯一
          key={`${d.page}-${i}`}
          item={d}
          onGotoPage={onGotoPage}
        />
      ))}
      {graphicText && (
        <GraphicHintRow
          text={graphicText}
          graphicPages={graphicPages}
          target={graphicPages[0]}
          onGotoPage={onGotoPage}
        />
      )}
    </div>
  )
}

/** 一行证件页提示：「⚠ P23 身份证 · 缺：姓名 / 身份证号 / 住址 · 建议核对原页」 */
function DocHintRow({ item, onGotoPage }: { item: DocHintPage; onGotoPage?: (page: number) => void }) {
  const label = docTypeLabel(item.doc)
  // 字段用「 / 」分隔而不是顿号：字段名本身可能带顿号（「姓名、曾用名」），
  // 再用顿号分项就分不清哪是字段、哪是分隔。
  const missingText = item.missing && item.missing.length > 0 ? `缺：${item.missing.join(' / ')}` : ''
  const body = (
    <>
      <AlertTriangle className="mt-0.5 h-3 w-3 flex-none opacity-60" aria-hidden />
      <span>
        <span className="tabular-nums">P{item.page}</span> {label}
        {missingText ? `，${missingText}` : '，关键字段可能未读出'} · 建议核对原页
      </span>
    </>
  )

  if (!onGotoPage) {
    return (
      <div data-doc-hint className={HINT_CLS}>
        {body}
      </div>
    )
  }
  return (
    <button
      type="button"
      data-doc-hint
      title={`跳到原页 P${item.page}`}
      onClick={() => onGotoPage(item.page)}
      className={`${HINT_CLS} cursor-pointer transition-colors hover:bg-secondary/70 hover:text-foreground`}
    >
      {body}
    </button>
  )
}

/** 一行图形页提示：「⚠ 本段含 N 页疑似图纸，正文可能不完整 · 建议核对原页（P147–148）」 */
function GraphicHintRow({
  text,
  graphicPages,
  target,
  onGotoPage,
}: {
  text: string
  graphicPages: number[]
  target?: number
  onGotoPage?: (page: number) => void
}) {
  const body = (
    <>
      <AlertTriangle className="mt-0.5 h-3 w-3 flex-none opacity-60" aria-hidden />
      <span>
        {text}
        {graphicPages.length > 0 && <span className="tabular-nums">（{pagesText(graphicPages)}）</span>}
      </span>
    </>
  )

  if (!onGotoPage || target === undefined) {
    return (
      <div data-quality-hint className={HINT_CLS}>
        {body}
      </div>
    )
  }
  return (
    <button
      type="button"
      data-quality-hint
      title={`跳到原页 ${pagesText(graphicPages)}`}
      onClick={() => onGotoPage(target)}
      className={`${HINT_CLS} cursor-pointer transition-colors hover:bg-secondary/70 hover:text-foreground`}
    >
      {body}
    </button>
  )
}
