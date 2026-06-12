/**
 * 工作流详情面板
 */
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { X } from 'lucide-react'
import { useWorkflowDetail, useApproveWorkflow } from './hooks/useWorkflows'
import { StatusBadge } from './components/StatusBadge'
import { StepTimeline } from './components/StepTimeline'
import { GateApprovalDialog } from './components/GateApprovalDialog'
import { useState } from 'react'

interface WorkflowDetailPanelProps {
  runId: number
  onClose: () => void
}

export function WorkflowDetailPanel({ runId, onClose }: WorkflowDetailPanelProps) {
  const { data: detail, isLoading } = useWorkflowDetail(runId)
  const approveMutation = useApproveWorkflow()
  const [showApproval, setShowApproval] = useState(false)

  if (isLoading || !detail) {
    return null
  }

  const needsApproval = detail.status === 'waiting_human'

  return (
    <Card className="mt-4">
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <div>
          <CardTitle className="text-lg">{detail.template}</CardTitle>
          <p className="text-sm text-muted-foreground mt-1">
            案件: {detail.case_name} · <StatusBadge status={detail.status} />
          </p>
        </div>
        <div className="flex gap-2">
          {needsApproval && (
            <Button size="sm" onClick={() => setShowApproval(true)}>
              审批当前步骤
            </Button>
          )}
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <StepTimeline steps={detail.steps} />

        {detail.result && (
          <div className="mt-4 p-3 bg-muted rounded-md">
            <p className="text-sm font-medium mb-1">运行结果</p>
            <pre className="text-xs text-muted-foreground whitespace-pre-wrap">
              {JSON.stringify(detail.result, null, 2)}
            </pre>
          </div>
        )}
      </CardContent>

      {needsApproval && (
        <GateApprovalDialog
          open={showApproval}
          onOpenChange={setShowApproval}
          stepName={detail.current_step}
          caseName={detail.case_name}
          onApprove={(comment) =>
            approveMutation.mutate(
              { runId, approved: true, comment },
              { onSuccess: () => setShowApproval(false) }
            )
          }
          onReject={(comment) =>
            approveMutation.mutate(
              { runId, approved: false, comment },
              { onSuccess: () => setShowApproval(false) }
            )
          }
          isPending={approveMutation.isPending}
        />
      )}
    </Card>
  )
}
