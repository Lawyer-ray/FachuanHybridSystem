/**
 * 单份材料的识别详情：扫描件可翻页、置信度可展开、可排除
 *
 * 抽屉要回答的问题是「它凭什么说这是借款合同、98% 是怎么来的」。
 * 所以内容是三层：识别依据（一句话）→ 置信度因子（4 项带分）→ 扫描件预览（可翻页、标出识别框）。
 */

import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'

import { DEMO_INTAKE_SEGMENTS, DEMO_X1_CONFIDENCE_FACTORS, DEMO_X1_SEGMENT_PREVIEWS } from '../demo-data'
import type { X1ConfidenceFactorRow } from '../demo-data'
import { ActionButton, InsetBlock, KeyValueRow, Pill } from '../ui'
import { cn } from '@/lib/utils'
import { DetailDrawer } from './DetailDrawer'
import { ScanPreview } from './ScanPreview'

export function MaterialDrawer({
  seq,
  onClose,
  excluded,
  onExclude,
}: {
  seq: number | null
  onClose: () => void
  excluded: Set<number>
  onExclude: (seq: number) => void
}) {
  const seg = seq == null ? null : DEMO_INTAKE_SEGMENTS.find((x) => x.seq === seq)
  const isExcluded = seg ? excluded.has(seg.seq) : false
  const preview = seq == null ? null : DEMO_X1_SEGMENT_PREVIEWS.find((p) => p.seq === seq)
  const factors = seq == null ? [] : DEMO_X1_CONFIDENCE_FACTORS.filter((f) => f.seq === seq)

  return (
    <DetailDrawer
      open={seg != null}
      onClose={onClose}
      title={seg?.fileName ?? ''}
      subtitle={seg ? `${seg.type} · ${seg.pages} · 置信度 ${(seg.confidence * 100).toFixed(0)}%` : undefined}
      badge={
        seg ? (
          <Pill tone={seg.status === 'ok' ? 'green' : seg.status === 'review' ? 'yellow' : 'red'}>
            {isExcluded ? '已排除' : seg.status === 'ok' ? '已认准' : seg.status === 'review' ? '待核对' : '未识别'}
          </Pill>
        ) : null
      }
      footer={
        seg ? (
          <>
            <ActionButton dark onClick={onClose}>
              确认识别结果
            </ActionButton>
            <ActionButton onClick={onClose}>重新识别</ActionButton>
            <ActionButton onClick={() => onExclude(seg.seq)}>排除这份</ActionButton>
          </>
        ) : null
      }
    >
      {seg ? (
        <div className="flex flex-col gap-3">
          <dl>
            <KeyValueRow label="页码区间">{seg.pages}</KeyValueRow>
            <KeyValueRow label="识别类型">{seg.type}</KeyValueRow>
            <KeyValueRow label="置信度">
              <span
                className={
                  seg.confidence >= 0.9
                    ? 'text-status-green'
                    : seg.confidence >= 0.5
                      ? 'text-status-yellow'
                      : 'text-status-red'
                }
              >
                {(seg.confidence * 100).toFixed(0)}%
              </span>
            </KeyValueRow>
            <KeyValueRow label="归入槽位">{seg.status === 'ok' ? '1-立案材料' : '待人工指定'}</KeyValueRow>
          </dl>

          <InsetBlock className="bg-secondary/25">
            <div className="text-[10px] text-muted-foreground">识别依据</div>
            <p className="mt-1 text-[11px] leading-[1.7] text-secondary-foreground">{seg.note}</p>
          </InsetBlock>

          {factors.length > 0 ? <ConfidenceBreakdown factors={factors} /> : null}

          <InsetBlock>
            {preview ? (
              <ScanPreview pages={preview.pages} />
            ) : (
              <div className="grid aspect-[3/4] place-items-center rounded-[4px] border border-border-light bg-secondary/40">
                <span className="text-[10.5px] text-muted-foreground">（本份暂无扫描件预览）</span>
              </div>
            )}
          </InsetBlock>
        </div>
      ) : null}
    </DetailDrawer>
  )
}

/** 「为什么是 98%」：4 个因子各带分值，条形长度即该项在总分里的占比 */
function ConfidenceBreakdown({ factors }: { factors: X1ConfidenceFactorRow[] }) {
  const [open, setOpen] = useState(false)
  const total = factors.reduce((n, f) => n + f.score, 0)
  const Chevron = open ? ChevronDown : ChevronRight

  return (
    <div className="rounded-[9px] border border-border-light">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-secondary/40"
      >
        <Chevron className="size-3 flex-none text-muted-foreground" />
        <span className="text-[11.5px] font-medium">为什么是 {total}%</span>
        <span className="ml-auto text-[10px] text-muted-foreground">4 个因子 · 点开看各占多少</span>
      </button>

      {open ? (
        <div className="border-t border-border-light px-3 py-2">
          <ul className="flex flex-col gap-2">
            {factors.map((f) => (
              <li key={f.label}>
                <div className="flex items-baseline gap-2">
                  <span className="text-[11.5px]">{f.label}</span>
                  <span className="ml-auto text-[11px] tabular-nums font-medium">{f.score} 分</span>
                </div>
                <div className="mt-1 h-[3px] overflow-hidden rounded-full bg-secondary">
                  <div
                    className={cn(
                      'h-full rounded-full',
                      f.score >= 25 ? 'bg-status-green' : f.score >= 10 ? 'bg-status-yellow' : 'bg-status-red',
                    )}
                    style={{ width: `${(f.score / 40) * 100}%` }}
                  />
                </div>
                <div className="mt-1 text-[10px] leading-[1.6] text-muted-foreground">{f.detail}</div>
              </li>
            ))}
          </ul>
          <div className="mt-2 flex items-baseline gap-2 border-t border-border-light pt-1.5">
            <span className="text-[10.5px] text-muted-foreground">合计</span>
            <span className="ml-auto text-[11.5px] tabular-nums font-medium">{total} 分</span>
          </div>
        </div>
      ) : null}
    </div>
  )
}
