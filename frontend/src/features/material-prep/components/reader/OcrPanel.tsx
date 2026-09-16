import { Loader2 } from 'lucide-react'
import type { OcrPending } from '../../types'
import { cn } from '@/lib/utils'

export function OcrPanel({
  pending,
  fromLabel,
  toLabel,
  onText,
  onRedo,
  onCancel,
  onOk,
}: {
  pending: OcrPending
  fromLabel: string
  toLabel: string
  onText: (v: string) => void
  onRedo: () => void
  onCancel: () => void
  onOk: () => void
}) {
  return (
    <div className="fixed bottom-5 left-1/2 z-[110] w-[min(560px,92vw)] -translate-x-1/2 rounded-2xl border border-border bg-card p-4 shadow-2xl">
      <div className="mb-2 flex items-center gap-2">
        <span className="rounded-full bg-zinc-900 px-2 py-0.5 text-[10.5px] font-medium text-white">RapidOCR</span>
        <span className="text-[12.5px] text-muted-foreground">{fromLabel}</span>
        <span className="text-[12.5px] text-muted-foreground">→</span>
        <span className="text-[12.5px] font-medium">{toLabel}</span>
        {pending.loading && (
          <span className="ml-auto flex items-center gap-1 text-[11.5px] text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" /> 识别中…
          </span>
        )}
      </div>
      <input
        value={pending.text}
        onChange={(e) => onText(e.target.value)}
        disabled={pending.loading}
        placeholder={pending.loading ? '识别中…' : '这块没识别到字，可以手打'}
        className="h-9 w-full rounded-lg border border-input bg-background px-3 text-[13px] outline-none focus:border-blue-300"
      />
      <div className="mt-2.5 flex items-center gap-2">
        <span className={cn('min-w-0 flex-1 truncate text-[11.5px]', pending.text ? 'text-muted-foreground' : 'text-amber-700')}>
          {pending.text ? '识别结果可直接改，继续拖手柄还能调范围' : '换个位置重框，或直接手打'}
        </span>
        <button
          type="button"
          onClick={onRedo}
          className="h-8 rounded-md border border-border px-2.5 text-[12.5px] text-secondary-foreground hover:bg-secondary"
        >
          重框
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="h-8 rounded-md border border-border px-2.5 text-[12.5px] text-secondary-foreground hover:bg-secondary"
        >
          取消
        </button>
        <button
          type="button"
          onClick={onOk}
          className="h-8 rounded-md bg-zinc-900 px-3 text-[12.5px] font-medium text-white hover:bg-zinc-700"
        >
          填入「{toLabel}」
        </button>
      </div>
    </div>
  )
}
