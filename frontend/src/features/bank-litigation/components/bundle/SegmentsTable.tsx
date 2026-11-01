import { StatusBadge, type Tone } from '@/components/shared/status-badge'

import type { PdfSplitSegment } from '../../api'

/** 分段状态 → 语气。低置信度用黄色，未识别用红色。 */
function segTone(flag: string | null | undefined): Tone {
  if (flag === 'low_confidence') return 'yellow'
  if (flag === 'unrecognized' || flag === 'ocr_failed') return 'red'
  return 'neutral'
}

/**
 * 复核表：分段结果逐行列出（页码区间 / 文件名 / 类型 / 置信度）。
 *
 * 这张表是「机器拆完、人还没点头」的中间态，归案前必须核对页码与文件名 ——
 * 归案后这些就是正式卷宗材料。
 */
export function SegmentsTable({ segs }: { segs: PdfSplitSegment[] }) {
  return (
    <div className="overflow-hidden rounded-[8px] border border-border">
      <div className="grid grid-cols-[42px_1fr_84px_64px] gap-2 border-b border-border bg-secondary/40 px-3 py-1.5 text-[10.5px] font-medium text-muted-foreground">
        <span>页</span>
        <span>文件名</span>
        <span>类型</span>
        <span className="text-right">置信度</span>
      </div>
      {segs.map((s) => (
        <div
          key={s.id ?? s.order}
          className="grid grid-cols-[42px_1fr_84px_64px] items-center gap-2 border-b border-border/60 px-3 py-1.5 last:border-b-0"
        >
          <span className="text-[11px] tabular-nums text-muted-foreground">
            {s.page_start === s.page_end ? s.page_start : `${s.page_start}-${s.page_end}`}
          </span>
          <div className="min-w-0">
            <div className="truncate text-[12px]" title={s.filename}>
              {s.filename}
            </div>
            <div className="truncate text-[10.5px] text-muted-foreground">{s.segment_label}</div>
          </div>
          <StatusBadge tone={segTone(s.review_flag)} size="xs">
            {s.review_flag === 'low_confidence'
              ? '需复核'
              : s.review_flag === 'unrecognized'
                ? '未识别'
                : '正常'}
          </StatusBadge>
          <span className="text-right text-[11px] tabular-nums text-muted-foreground">
            {s.confidence != null ? s.confidence.toFixed(2) : '—'}
          </span>
        </div>
      ))}
    </div>
  )
}
