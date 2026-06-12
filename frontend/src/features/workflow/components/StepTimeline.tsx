/**
 * 步骤时间线组件
 */
import { CheckCircle2, Circle, Clock, XCircle, Loader2, SkipForward } from 'lucide-react'
import type { StepExecution } from '../types'

const STATUS_ICON: Record<string, React.ReactNode> = {
  success: <CheckCircle2 className="h-4 w-4 text-green-500" />,
  failed: <XCircle className="h-4 w-4 text-red-500" />,
  running: <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />,
  waiting: <Clock className="h-4 w-4 text-yellow-500" />,
  skipped: <SkipForward className="h-4 w-4 text-gray-400" />,
  pending: <Circle className="h-4 w-4 text-gray-300" />,
}

export function StepTimeline({ steps }: { steps: StepExecution[] }) {
  return (
    <div className="space-y-3">
      {steps.map((step, i) => (
        <div key={step.step_id} className="flex items-start gap-3">
          <div className="flex flex-col items-center">
            {STATUS_ICON[step.status] || STATUS_ICON.pending}
            {i < steps.length - 1 && <div className="w-px h-6 bg-border mt-1" />}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">{step.name}</span>
              <span className="text-xs text-muted-foreground">({step.type})</span>
            </div>
            {step.output_summary && (
              <p className="text-xs text-muted-foreground mt-0.5 truncate">{step.output_summary}</p>
            )}
            {step.error && (
              <p className="text-xs text-red-500 mt-0.5">{step.error}</p>
            )}
            {step.started_at && (
              <p className="text-xs text-muted-foreground mt-0.5">
                {new Date(step.started_at).toLocaleString('zh-CN')}
              </p>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
