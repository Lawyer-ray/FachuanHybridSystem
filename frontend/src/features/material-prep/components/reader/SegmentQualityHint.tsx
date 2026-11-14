import { AlertTriangle } from 'lucide-react'

import { pagesText, qualityFlagLabel } from '../../draft/quality'

/**
 * 右栏正文面板顶部的一条淡灰质量提示：「本段含 N 页疑似图纸，正文可能不完整」。
 *
 * ## 为什么单独成组件
 *
 * 文案拼装（图形页 / 稀疏页 / 后端 quality_flags 三种来源并存的去重）有自己的一套
 * 规则，塞进 `SegmentMarkdown` 会把这个已经承载「对照、编辑、可疑点」三件事的面板
 * 再顶高一档，也让那段文案没法单测。
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
  onGotoPage,
}: {
  /** 后端给的段级质量标记（未知取值原样展示，不丢信息） */
  flags?: string[]
  /** 本段覆盖的疑似图形页 */
  graphicPages?: number[]
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
  if (parts.length === 0) return null

  const text = `本段${parts.join('，')}，正文可能不完整 · 建议核对原页`
  const target = graphicPages[0]
  const cls = 'flex items-start gap-1.5 rounded-lg border border-zinc-200 bg-secondary/40 px-2.5 py-1.5 text-left text-[11px] leading-relaxed text-muted-foreground'
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
      <div data-quality-hint className={cls}>
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
      className={`${cls} cursor-pointer transition-colors hover:bg-secondary/70 hover:text-foreground`}
    >
      {body}
    </button>
  )
}
