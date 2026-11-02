import { cn } from '@/lib/utils'

/** 整包分段的处理阶段。状态机：idle → uploading → splitting → review → confirming → importing → done/failed */
export type BundlePhase =
  | 'idle'
  | 'uploading'
  | 'splitting'
  | 'review'
  | 'confirming'
  | 'importing'
  | 'done'
  | 'failed'

const STEPS: { key: BundlePhase[]; label: string }[] = [
  { key: ['uploading', 'splitting'], label: '识别' },
  { key: ['review', 'confirming'], label: '复核' },
  { key: ['importing'], label: '归案' },
  { key: ['done'], label: '完成' },
]

/** 四步进度关节（识别 → 复核 → 归案 → 完成），当前步反色高亮 */
export function StepBar({ phase }: { phase: BundlePhase }) {
  const idx = STEPS.findIndex((s) => s.key.includes(phase))
  return (
    <div className="flex items-center gap-1.5">
      {STEPS.map((s, i) => {
        const active = i === idx
        const passed = idx >= 0 && i < idx
        return (
          <div key={s.label} className="flex items-center gap-1.5">
            <span
              className={cn(
                'rounded-[5px] px-2 py-0.5 text-[11px]',
                active
                  ? 'bg-foreground font-medium text-background'
                  : passed
                    ? 'text-status-green'
                    : 'text-muted-foreground',
              )}
            >
              {s.label}
            </span>
            {i < STEPS.length - 1 ? <span className="text-[10px] text-border">›</span> : null}
          </div>
        )
      })}
    </div>
  )
}
