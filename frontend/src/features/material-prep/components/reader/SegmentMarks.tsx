import { AlertTriangle, FileImage, IdCard, Repeat, Table } from 'lucide-react'
import { docTypeLabel, reviewHintOf } from '../../draft'
import type { Segment } from '../../types'

/**
 * 左栏段行的**质量标记组**：几张按严重度互斥单选的灰/琥珀图标，加证件页 tooltip
 * 的分档文案（`docHintLabels` / `docHintTooltip`）。
 *
 * 从 `RailSegRow.tsx` 拆出的原因：行本体管的是**交互**（点击跳转、多选、双击改名、
 * 拖拽落点、右键菜单），而这里管的是**「这一份材料有什么问题」的表达口径**——
 * 缺哪个字段怎么说、几类标记谁优先、tooltip 写哪句话。
 * 两者改动理由完全不同：调 tip 措辞不该碰到 dragOver 逻辑，改拖拽也不该
 * 在一堆 title 字符串之间找插入点。标记的 DOM 契约（`data-*-mark`）由
 * `RailSegRow.dom.test.tsx` 直接断言，所以属性名与结构逐字保留。
 */

/**
 * 证件类型码列表 → tooltip 里的类型名：去重后拼成「身份证 / 不动产权证」，
 * 超过两种就只说前两种 + 「等」——tooltip 不是清单，堆太长反而没人看。
 */
function docHintLabels(docs: string[]): string {
  const labels = [...new Set(docs.map(docTypeLabel))]
  if (labels.length <= 2) return labels.join(' / ')
  return `${labels.slice(0, 2).join(' / ')} 等${labels.length}类证件`
}

/**
 * 证件页的 tooltip：**按「有没有缺字段」分档**，不能一律写「关键字段可能未读出」。
 *
 * 实测 p30 结婚证：姓名两个人都读出来了，`missing` 是空数组。若仍提示「可能未读出」，
 * 律师翻原图发现字段好好地在——**下次就不信这个提示了**。误报会让整个功能失效，
 * 与之前删掉彩色类型圆点是同一个道理。
 *
 * 分档口径：
 *   · 有缺字段 → 点名缺什么（与右栏提示条、待补录清单保持一致）
 *   · 无缺字段 → 中性描述「已认出类型，建议核对原图」
 */
function docHintTooltip(pages: { page: number; doc: string; missing: string[] }[]): string {
  const labels = docHintLabels(pages.map((p) => p.doc))
  const missing = [...new Set(pages.flatMap((p) => p.missing))]
  if (missing.length > 0) {
    return `含${labels}页，${missing.slice(0, 3).join(' / ')}未读出，请核对原图`
  }
  return `含${labels}页，建议核对原图`
}

/**
 * 行内质量标记：**只给图标 + tooltip，不写文字**。
 *
 * 「复核」两个字常驻是左栏最贵的一笔开销：40 份材料里三十多行都挂着它，
 * 每行固定吃掉 22px——在 232px 宽的栏里等于直接拿走两个字的名字位。
 * 同一个意思用 12px 的琥珀色三角说，信息一点不少（tooltip 里连置信度百分比
 * 和「该核对什么」都写清楚），宽度只剩一半，而且与右栏 `SegmentQualityHint`
 * 用的是同一个图形，读起来是一套语言。
 */
export function SegmentMarks({
  seg,
  docHintPages,
  graphicPages,
  ocrFailedPages,
  degeneratePages,
  columnAnomalyPages,
}: {
  seg: Segment
  docHintPages: { page: number; doc: string; missing: string[] }[]
  graphicPages: number[]
  ocrFailedPages: number[]
  degeneratePages: number[]
  columnAnomalyPages: number[]
}) {
  const reviewHint = reviewHintOf(seg)
  return (
    <span className="flex flex-none items-center gap-0.5">
      {/* 徽标是**互斥单选**（232px 的栏里放不下 4 个，段名会先被挤死），按严重度排：
          ocrFailed > degenerate > columnAnomaly > doc > graphic。
          理由：正文根本不可信（整页没字）> 正文不可信（云端退化、换本地 OCR）>
          数字可能挂错表头 > 字段没读出 > 内容不完整。
          取字失败用琥珀色（要动作）；退化 / 列数突变是灰的（与右栏页提示同一色的
          事实陈述），只有 tooltip 里那句「建议核对」「请核对」是行动指引。 */}
      {ocrFailedPages.length > 0 ? (
        <span
          data-ocr-failed-mark
          className="flex-none text-amber-600"
          title={`含 ${ocrFailedPages.length} 页未取到任何文字（P${ocrFailedPages.join('、P')}），正文里没有这几页 · 请核对原图补录`}
        >
          <AlertTriangle className="h-3 w-3" aria-hidden />
        </span>
      ) : degeneratePages.length > 0 ? (
        <span
          data-degenerate-mark
          className="flex-none text-zinc-400"
          title={`含 ${degeneratePages.length} 页云端取字判为退化（P${degeneratePages.join('、P')}），已改用本地识别兜底 · 建议核对原页`}
        >
          <Repeat className="h-3 w-3" aria-hidden />
        </span>
      ) : columnAnomalyPages.length > 0 ? (
        <span
          data-column-anomaly-mark
          className="flex-none text-zinc-400"
          title={`含 ${columnAnomalyPages.length} 页表格列数与上一页不同（P${columnAnomalyPages.join('、P')}），数字可能挂错表头 · 请核对数字表头`}
        >
          <Table className="h-3 w-3" aria-hidden />
        </span>
      ) : docHintPages.length > 0 ? (
        <span data-doc-mark className="flex-none text-zinc-400" title={docHintTooltip(docHintPages)}>
          <IdCard className="h-3 w-3" aria-hidden />
        </span>
      ) : graphicPages.length > 0 ? (
        <span
          data-graphic-mark
          className="flex-none text-zinc-400"
          title={`含 ${graphicPages.length} 页疑似图纸/照片，请核对原图`}
        >
          <FileImage className="h-3 w-3" aria-hidden />
        </span>
      ) : null}
      {reviewHint && (
        <span
          data-review-mark
          className="flex-none text-amber-600"
          // tooltip 走 reviewHintOf：与段头徽标、右栏提示条同一句话（含「核对什么」）
          title={reviewHint.reason ? `${reviewHint.label}：${reviewHint.reason}` : reviewHint.label}
        >
          <AlertTriangle className="h-3 w-3" aria-hidden />
        </span>
      )}
    </span>
  )
}
