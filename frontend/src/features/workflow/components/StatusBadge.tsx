/**
 * 工作流状态标签
 */
import { Badge } from '@/components/ui/badge'
import type { WorkflowStatus } from '../types'

const STATUS_CONFIG: Record<WorkflowStatus, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
  running: { label: '运行中', variant: 'default' },
  waiting_human: { label: '等待审批', variant: 'secondary' },
  waiting_event: { label: '等待外部', variant: 'outline' },
  completed: { label: '已完成', variant: 'outline' },
  failed: { label: '失败', variant: 'destructive' },
  cancelled: { label: '已取消', variant: 'secondary' },
  timed_out: { label: '超时', variant: 'destructive' },
}

export function StatusBadge({ status }: { status: WorkflowStatus }) {
  const config = STATUS_CONFIG[status] || { label: status, variant: 'outline' as const }
  return <Badge variant={config.variant}>{config.label}</Badge>
}
