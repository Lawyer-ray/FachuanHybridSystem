import { useState } from 'react'
import { AlertTriangle, FileImage, IdCard, Repeat, Table } from 'lucide-react'
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from '@/components/ui/context-menu'
import { docTypeLabel, reviewHintOf, segRangeText } from '../../draft'
import type { Segment } from '../../types'
import { cn } from '@/lib/utils'
import { SegmentDownloadMenuItems, SegmentSelectBox } from './SegmentDownloadBar'
import { splitNameTail } from './segment-name'
import type { SegmentRowDownload } from './use-segment-downloads'

export type DropPos = 'before' | 'after'

/**
 * 左栏的一行段：点击跳转、⌘/⇧点 多选、双击（或右键→重命名）行内改名、
 * 右键重命名 / 并入上一份、拖拽移动段序（上半=插到前面，下半=插到后面）。
 *
 * 类型没有 pill：选了类型名字会自动变成「类型.pdf」，元数据在右键菜单里改。
 *
 * ## 宽度预算（左栏默认 232px，可拖到 520px）
 *
 * 一行里常驻的只有四样：勾选框、段名、页范围、质量图标。单段下载（PDF / MD）
 * 在右键菜单里——上一版两个按钮常驻，40 行里段名被挤到四五个字。
 */
export function RailSegRow({
  seg,
  si,
  whole,
  auto,
  classified,
  crossGroup = false,
  selected = false,
  dropPos = null,
  graphicPages = [],
  docHintPages = [],
  ocrFailedPages = [],
  degeneratePages = [],
  columnAnomalyPages = [],
  editing,
  download,
  onStartEdit,
  onFocus,
  onSelectRow,
  onRename,
  onMerge,
  onDragStartRow,
  onHoverDrop,
  onDropRow,
  onDragEndRow,
}: {
  seg: Segment
  si: number
  whole: boolean
  auto: boolean
  classified: boolean
  crossGroup?: boolean
  selected?: boolean
  /** 本行正被拖拽悬停的插入位置（上半 / 下半） */
  dropPos?: DropPos | null
  /** 本段页范围里疑似图纸/照片的页号（来自 summary.page_quality，旧任务为空） */
  graphicPages?: number[]
  /** 本段覆盖到的证件页（含该页缺失字段）。`missing` 为空 = 字段都在，只是认出类型 */
  docHintPages?: { page: number; doc: string; missing: string[] }[]
  /** 本段里**一个字都没读到**的页号（`summary.page_quality.ocr_failed_pages`）。
   *  这些页在正文里完全不存在，所以必须靠徽标告警，而不是正文内提示 */
  ocrFailedPages?: number[]
  /** 本段里云端取字判为退化的页（`summary.degenerate_pages`，正文已改由本地 OCR 兜底） */
  degeneratePages?: number[]
  /** 本段里表格列数与上一页不同的页（`summary.table_geometry.column_anomalies`） */
  columnAnomalyPages?: number[]
  /** 行内改名由父层持有（右键「重命名」也要打开它） */
  editing: boolean
  /** 勾选 + 单个下载的视图模型；undefined = 本段没有后端产物（人工拆的段 / 旧草稿），
   *  此时两个控件都不渲染——不给「点了一定 404」的入口 */
  download?: SegmentRowDownload
  onStartEdit: () => void
  onFocus: () => void
  /** 带修饰键的点击（多选 / 区间选），e 传下去判断 meta/ctrl/shift */
  onSelectRow: (e: React.MouseEvent) => void
  onRename: (name: string) => void
  onMerge?: () => void
  onDragStartRow: () => void
  /** dragOver 悬停时上报插入位置（上半 / 下半） */
  onHoverDrop: (pos: DropPos) => void
  /** 提交拖拽：位置由父层从 dragOver 状态里取 */
  onDropRow: () => void
  onDragEndRow: () => void
}) {
  const [nameDraft, setNameDraft] = useState(seg.fn)

  const commit = () => {
    const name = nameDraft.trim()
    if (name && name !== seg.fn) onRename(name)
  }

  const displayName = whole && auto ? '整份' : seg.fn
  const meta = crossGroup ? `${seg.refs.length} 页` : whole ? '' : segRangeText(seg)

  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>
        <div
          role="button"
          tabIndex={0}
          data-rail-seg={si}
          data-selected={selected || undefined}
          draggable={!editing}
          title={`${seg.fn}\n点击跳转 · ⌘/⇧点 多选 · 双击改名 · 右键改名/下载`}
          className={cn(
            'relative flex items-center gap-1.5 rounded-md px-1.5 py-1 text-left outline-none hover:bg-secondary focus-visible:ring-2 focus-visible:ring-ring',
            selected && 'bg-secondary/70 ring-1 ring-foreground/25',
            !classified && 'text-amber-700',
          )}
          onClick={(e) => {
            if (editing) return
            if (e.metaKey || e.ctrlKey || e.shiftKey) {
              onSelectRow(e)
              return
            }
            onFocus()
          }}
          onDoubleClick={(e) => {
            e.preventDefault()
            onStartEdit()
          }}
          onKeyDown={(e) => {
            if (editing) return
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              onFocus()
            } else if (e.key === 'F2') {
              e.preventDefault()
              onStartEdit()
            }
          }}
          onDragStart={(e) => {
            e.dataTransfer.setData('text/plain', String(si))
            e.dataTransfer.effectAllowed = 'move'
            onDragStartRow()
          }}
          onDragOver={(e) => {
            e.preventDefault()
            e.dataTransfer.dropEffect = 'move'
            const r = e.currentTarget.getBoundingClientRect()
            onHoverDrop(e.clientY < r.top + r.height / 2 ? 'before' : 'after')
          }}
          onDrop={(e) => {
            e.preventDefault()
            onDropRow()
          }}
          onDragEnd={onDragEndRow}
        >
          {/* 拖拽插入线：上半=插到本行前，下半=插到本行后 */}
          {dropPos && (
            <span
              className={cn(
                'absolute right-0 left-0 z-10 h-[3px] rounded-full bg-foreground/70',
                dropPos === 'before' ? '-top-[3px]' : '-bottom-[3px]',
              )}
            />
          )}
          {/* 勾选框放在名字**前**：这里是「按段挑材料去下载」的清单，勾选位在行首
              才符合列表直觉（与邮箱/文件管理器同位置）。改名时收起，把宽度让给输入框 */}
          {!editing && <SegmentSelectBox row={download} name={displayName} />}
          {/* 这里原本是一个按段类型上色的圆点（SEG_COLORS）。已按反馈移除：
              左栏是「找材料」的目录，不是按类型分类的图表；一圈彩色点只会
              把视线从「段名」上拽开，而段名才是律师真正在找的东西。
              类型也没有单独的胶囊：段名本身就带着类型词（选类型 = 改名），
              所以「类型」不会丢，只是不再重复画一遍。 */}
          {editing ? (
            <input
              autoFocus
              aria-label="材料名"
              value={nameDraft}
              onChange={(e) => setNameDraft(e.target.value)}
              onBlur={commit}
              onClick={(e) => e.stopPropagation()}
              onKeyDown={(e) => {
                e.stopPropagation()
                if (e.key === 'Enter') commit()
                if (e.key === 'Escape') onStartEdit()
              }}
              className="h-6 min-w-0 flex-1 rounded border border-zinc-400 bg-white px-1.5 text-[12.5px] outline-none"
            />
          ) : (
            <SegmentName name={displayName} />
          )}
          {meta && !editing && (
            <span className="flex-none text-[10.5px] tabular-nums text-muted-foreground">{meta}</span>
          )}
          {/* 质量标记：只给一个极淡的灰图标，不上色、不加文字。
              左栏是「找材料」的目录，上一版正是因此把彩色类型圆点删掉了；
              但「这一份里有几页是图纸，正文看不出内容」/「这一份里有身份证页，
              关键字段可能没读出」是律师确实会漏掉的信息，所以留一个**最小干扰**
              的标记：图标本身不抢视线，说明放 tooltip。
              证件页优先级高于图纸页：两者都有时只显示证件图标——缺的是必须抄进
              卷宗的字段，比「这页看不出内容」更该先处理；两个图标并排只会互相稀释。 */}
          {!editing && (
            <SegmentMarks
              seg={seg}
              docHintPages={docHintPages}
              graphicPages={graphicPages}
              ocrFailedPages={ocrFailedPages}
              degeneratePages={degeneratePages}
              columnAnomalyPages={columnAnomalyPages}
            />
          )}
        </div>
      </ContextMenuTrigger>
      <ContextMenuContent className="min-w-[180px]">
        {/* 「选类型」已移除：类型词表是 24 个固定选项，而律师需要的只是「这份叫什么」。
            重命名一个入口就能表达，且它才是归案判定看的那个信号（fnAuto）。 */}
        <ContextMenuItem onSelect={onStartEdit}>重命名</ContextMenuItem>
        {onMerge && (
          <>
            <ContextMenuSeparator />
            <ContextMenuItem onSelect={onMerge}>并入上一份</ContextMenuItem>
          </>
        )}
        {/* 单个下载（PDF / Markdown）：行内不占宽度，收进右键菜单，见 SegmentDownloadMenuItems */}
        {download && (
          <>
            <ContextMenuSeparator />
            <SegmentDownloadMenuItems row={download} />
          </>
        )}
      </ContextMenuContent>
    </ContextMenu>
  )
}

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
 * 段名：**头部吃剩余宽度并截断，尾部固定显示**。
 *
 * CSS `truncate` 裁的是尾部，而段名的区分信息恰好全在尾部（`-P20.pdf`）——
 * 两份「授权委托书」只差页号，尾一裁就分不出谁是谁。拆成两段后头部随便截，
 * 尾部永远完整（拆分规则见 `segment-name.ts`）。
 */
function SegmentName({ name }: { name: string }) {
  const { head, tail } = splitNameTail(name)
  if (!tail) return <span className="min-w-0 flex-1 truncate text-[13px]">{name}</span>
  return (
    <span data-seg-name className="flex min-w-0 flex-1 items-baseline text-[13px]">
      <span className="min-w-0 flex-1 truncate">{head}</span>
      <span data-seg-name-tail className="flex-none">
        {tail}
      </span>
    </span>
  )
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
function SegmentMarks({
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
