/**
 * 一条核对发现项的渲染（档位徽标 + 标题 + `expected → actual`）。
 *
 * 严重度三档是三种**处置**（红线不得放行 / 疑似待确认 / 无法核对），不是三种装饰，
 * 所以档位映射只此一份；覆盖度文案这类纯换算在 `run-coverage.ts`（组件文件只导出组件，
 * 是 `react-refresh` 的硬要求）。
 */

import { cn } from '@/lib/utils'

import type { FindingOut } from './api'

interface SeverityStyle {
  /** 给律师看的档位名，与后端 `domain/contracts.py` 的 Severity 一一对应 */
  label: string
  chip: string
  title: string
}

const SEVERITY_RED: SeverityStyle = {
  label: '红线',
  chip: 'bg-red-50 text-red-700 ring-red-200',
  title: 'text-red-700',
}
const SEVERITY_YELLOW: SeverityStyle = {
  label: '疑似',
  chip: 'bg-amber-50 text-amber-700 ring-amber-200',
  title: 'text-amber-800',
}
const SEVERITY_GRAY: SeverityStyle = {
  label: '无法核对',
  chip: 'bg-zinc-100 text-zinc-600 ring-zinc-200',
  title: 'text-zinc-600',
}

/**
 * severity → 展示样式。三档是三种处置（红线不得放行 / 疑似待确认 / 无法核对），
 * 不是三种装饰。未知值按 gray 渲染：把不认识的档位画成红线会制造假警报。
 */
function severityStyle(severity: string): SeverityStyle {
  if (severity === 'red') return SEVERITY_RED
  if (severity === 'yellow') return SEVERITY_YELLOW
  return SEVERITY_GRAY
}

/** 一条发现项：档位徽标 + 标题 + `expected → actual`（后端为空串时不渲染箭头）。 */
export function FindingLine({ finding }: { finding: FindingOut }) {
  const style = severityStyle(finding.severity)
  const pair =
    finding.expected || finding.actual
      ? `${finding.expected || '（空）'} → ${finding.actual || '（空）'}`
      : ''
  return (
    <div className="flex items-start gap-1.5 text-[11.5px] leading-relaxed">
      <span
        className={cn(
          'mt-px flex-none rounded px-1 text-[10px] leading-4 ring-1 ring-inset',
          style.chip,
        )}
      >
        {style.label}
      </span>
      <span className="min-w-0 flex-1">
        <span className={cn('font-medium', style.title)}>{finding.title}</span>
        {pair && <span className="ml-1 text-muted-foreground">{pair}</span>}
      </span>
    </div>
  )
}
