import { Copy } from 'lucide-react'
import { toast } from 'sonner'

import { copyTextToClipboard } from '../domain'

/** 行内复制按钮：点击复制并 toast */
export function CopyButton({ title, getText }: { title: string; getText: () => string }) {
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      className="mt-0.5 flex size-6 flex-none items-center justify-center rounded-[7px] text-muted-foreground/50 opacity-60 transition-all hover:bg-foreground hover:text-background hover:opacity-100"
      onClick={(e) => {
        e.stopPropagation()
        const text = getText()
        void copyTextToClipboard(text).then(() => {
          toast.success('已复制：' + (text.split('\n')[0]?.replace(/（.*?）/, '').trim() ?? ''))
        })
      }}
    >
      <Copy className="size-3" />
    </button>
  )
}

export function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-6 pt-4 pb-2 text-[11px] font-[650] tracking-[0.09em] text-muted-foreground uppercase">
      {children}
    </div>
  )
}

export function MetaRow({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-border-light py-[5px] text-xs last:border-b-0">
      <span className="flex-none text-[11px] text-muted-foreground">{k}</span>
      <span className="min-w-0 text-right font-[560] break-all tabular-nums">{v}</span>
    </div>
  )
}

export function MoneyCell({ label, value, hot }: { label: string; value: string; hot?: boolean }) {
  return (
    <div className="min-w-0 rounded-[11px] bg-secondary px-[11px] pt-2 pb-[7px]">
      <div className="text-[10.5px] whitespace-nowrap text-muted-foreground">{label}</div>
      <div className={'mt-px text-[15px] font-bold tracking-[-0.01em] truncate tabular-nums ' + (hot ? 'text-status-red' : '')}>
        {value}
      </div>
    </div>
  )
}

/** 程序节点：实心点=已结、空心粗环=在办，同阶段聚合 ×N */
export function StageNode({ stage, n, live, first }: { stage: string; n: number; live: boolean; first: boolean }) {
  return (
    <div className="flex flex-none items-center gap-[7px]">
      {!first && <span className={'mx-[7px] h-0.5 w-6 flex-none rounded-sm ' + (live ? 'bg-border' : 'bg-foreground')} />}
      <span
        className={
          'size-[11px] flex-none rounded-full border-2 ' +
          (live ? 'border-foreground bg-card shadow-[0_0_0_3px_rgba(24,24,27,0.09)]' : 'border-foreground bg-foreground')
        }
      />
      <b className="text-xs font-[620]">{stage}</b>
      {n > 1 && <span className="-ml-1 text-[10px] font-semibold text-muted-foreground/70 tabular-nums">×{n}</span>}
      <span className={'text-[10.5px] ' + (live ? 'font-semibold text-foreground' : 'text-muted-foreground')}>
        {live ? '在办' : '已结'}
      </span>
    </div>
  )
}
