/**
 * 收费节的无状态零件：统计格 / 小节眉头 / 开票状态徽标。
 *
 * 只描述「怎么显示」，不取数也不改数；与 RailFees 的取数和归属动作分开，
 * 改视觉时不必在一个 400 行的文件里翻找。
 */

/** 统计格：灰标签 + 粗体金额；未收不可知（风险代理）时降为一字占位 */
export function StatCell({ label, value, muted = false }: { label: string; value: string; muted?: boolean }) {
  return (
    <div className="flex flex-col items-center gap-px py-[7px]">
      <span className="text-[10.5px] text-muted-foreground/80">{label}</span>
      <b className={'text-[13.5px] font-[680] tabular-nums ' + (muted ? 'text-muted-foreground/50' : 'text-secondary-foreground')}>
        {value}
      </b>
    </div>
  )
}

/** 小节标题（收款/发票两条线各自的眉头）：标题 + 计数 */
export function Subhead({ title, count, extra }: { title: string; count: number; extra?: string }) {
  return (
    <div className="mt-[13px] mb-[5px] flex items-baseline gap-1.5">
      <span className="text-[11px] font-[650] text-muted-foreground/80">{title}</span>
      <span className="text-[10.5px] tabular-nums text-muted-foreground/60">· {count}</span>
      {extra && <span className="ml-auto text-[10.5px] font-[620] text-status-yellow">{extra}</span>}
    </div>
  )
}

/** 开票状态徽标：跟「这笔钱开没开票」走（票归属到收款，状态随之重算） */
export function InvoiceStatusBadge({ status, label }: { status: string; label?: string }) {
  const tone =
    status === 'INVOICED_FULL'
      ? 'bg-status-green/12 text-status-green'
      : status === 'INVOICED_PARTIAL'
        ? 'bg-status-yellow/12 text-status-yellow'
        : 'bg-secondary text-muted-foreground'
  return (
    <span className={'rounded-[5px] px-1.5 py-px text-[10px] font-[620] whitespace-nowrap ' + tone}>
      {label || '未开票'}
    </span>
  )
}
