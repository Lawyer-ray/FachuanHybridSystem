/**
 * 扫描件预览（可翻页 + 识别框）
 *
 * 抽屉里原先只有一个「第 1 页预览」占位框 —— 律师看到「认成借款合同，置信度 98%」
 * 之后的第一反应是「它凭什么这么说」，一个灰框答不了这个问题。
 *
 * 这里用 div 模拟扫描件的版式节奏（居中标题 / 条款小标题 / 正文 / 表格行 /
 * 印章圆圈），并在被识别的区域上叠虚线框，鼠标悬停给出识别结论。
 * 页面数据来自 DEMO_X1_SEGMENT_PREVIEWS，每份材料的页码与 DEMO_INTAKE_SEGMENTS 一致，
 * 所以翻页翻到第几页，和右边写的「P1–14」对得上。
 */

import { useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'

import type { X1DocLineKind, X1PreviewPage } from '../demo-data'
import { ActionButton, Pill } from '../ui'

/** 每种版式行的样子 —— 只管视觉，不含语义 */
const LINE_CLASS: Record<X1DocLineKind, string> = {
  title: 'mx-auto w-[72%] text-center text-[11px] font-semibold tracking-[.04em] text-foreground/80',
  meta: 'mx-auto w-[64%] text-center text-[8.5px] text-muted-foreground',
  heading: 'text-[9.5px] font-semibold text-foreground/75',
  para: 'text-[8.5px] leading-[1.75] text-secondary-foreground/85',
  field: 'text-[8.5px] text-secondary-foreground/85',
  table:
    'border-y border-dashed border-border-light bg-secondary/40 px-1 text-[8px] leading-[1.6] tabular-nums text-secondary-foreground/80',
  seal: 'mt-1 inline-block rounded-full border border-status-red/50 px-2 py-0.5 text-[8px] text-status-red/80',
  sign: 'text-[8.5px] text-secondary-foreground/70',
}

/** 页面内容（不含翻页器），也被「原文对照」复用 */
export function ScanPageView({ page }: { page: X1PreviewPage }) {
  return (
    <div className="relative aspect-[3/4] w-full overflow-hidden rounded-[4px] border border-border-light bg-[#fdfdfb] pt-4">
      <div className="flex h-full flex-col gap-[5px] px-3 pt-3 pb-3">
        {page.lines.map((l, i) =>
          l.kind === 'seal' ? (
            <span key={i} className={LINE_CLASS.seal}>
              {l.text}
            </span>
          ) : (
            <div key={i} className={LINE_CLASS[l.kind]}>
              {l.text}
            </div>
          ),
        )}
      </div>

      {/* 识别框：虚线框 + 悬停显示结论 */}
      {page.boxes.map((b, i) => (
        <div
          key={i}
          className="group/box absolute rounded-[2px] border border-dashed border-status-blue/80 bg-status-blue/5"
          style={{ top: `${b.top}%`, left: `${b.left}%`, width: `${b.width}%`, height: `${b.height}%` }}
        >
          <span className="pointer-events-none absolute -top-[15px] left-0 hidden whitespace-nowrap rounded-[3px] bg-status-blue px-1 py-px text-[8.5px] font-medium text-white group-hover/box:block">
            {b.label}
          </span>
        </div>
      ))}

      <span className="absolute right-2 bottom-1.5 text-[8px] tabular-nums text-muted-foreground">
        — 第 {page.pageNo} 页 —
      </span>
    </div>
  )
}

export function ScanPreview({ pages }: { pages: X1PreviewPage[] }) {
  const [i, setI] = useState(0)
  const page = pages[Math.min(i, pages.length - 1)]

  if (!page) return null

  return (
    <div>
      <div className="flex items-center justify-between">
        <span className="text-[10px] text-muted-foreground">扫描件预览</span>
        <Pill tone="blue">{page.boxes.length} 处识别框</Pill>
      </div>

      <div className="mt-2">
        {/* key 让翻页时重放淡入，看得出「换了一页」（见 index.css 的 page-fade） */}
        <div key={page.pageNo} className="page-fade">
          <ScanPageView page={page} />
        </div>
      </div>

      <div className="mt-2 flex items-center gap-2">
        <ActionButton
          sm
          title="上一页"
          disabled={i === 0}
          onClick={() => setI((v) => Math.max(0, v - 1))}
        >
          <ChevronLeft className="size-3" /> 上一页
        </ActionButton>
        <span className="min-w-[86px] flex-1 text-center text-[11px] tabular-nums">
          第 {i + 1} 页 / 共 {pages.length} 页
        </span>
        <ActionButton
          sm
          title="下一页"
          disabled={i === pages.length - 1}
          onClick={() => setI((v) => Math.min(pages.length - 1, v + 1))}
        >
          下一页 <ChevronRight className="size-3" />
        </ActionButton>
      </div>

      <ul className="mt-2 flex flex-col gap-[3px]">
        {page.boxes.map((b, k) => (
          <li key={k} className="text-[10px] leading-[1.6] text-muted-foreground">
            <span className="mr-1 text-status-blue">□</span>
            {b.label}
          </li>
        ))}
      </ul>
    </div>
  )
}
