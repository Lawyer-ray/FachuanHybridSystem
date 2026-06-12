/**
 * 诉讼流程看板
 */
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { RefreshCw, GitBranch, Settings } from 'lucide-react'
import { useWorkflows, useApproveWorkflow } from './hooks/useWorkflows'
import { StatusBadge } from './components/StatusBadge'
import { GateApprovalDialog } from './components/GateApprovalDialog'
import { WorkflowDetailPanel } from './WorkflowDetail'
import type { WorkflowRun } from './types'

export function WorkflowDashboard() {
  const navigate = useNavigate()
  const { data: runs, isLoading, refetch } = useWorkflows()
  const [selectedRun, setSelectedRun] = useState<WorkflowRun | null>(null)
  const [approvalTarget, setApprovalTarget] = useState<WorkflowRun | null>(null)
  const approveMutation = useApproveWorkflow()

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">诉讼流程</h1>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => navigate('/admin/workflows/templates')}>
            <GitBranch className="h-4 w-4 mr-2" />
            模板管理
          </Button>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            <RefreshCw className="h-4 w-4 mr-2" />
            刷新
          </Button>
        </div>
      </div>

      {(!runs || runs.length === 0) ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            暂无诉讼流程。可通过工作台或 Claude 发起。
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4">
          {runs.map((run) => (
            <Card
              key={run.run_id}
              className={`cursor-pointer transition-colors hover:bg-accent/50 ${
                run.status === 'waiting_human' ? 'border-yellow-400' : ''
              }`}
              onClick={() => setSelectedRun(run)}
            >
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">{run.template}</CardTitle>
                  <StatusBadge status={run.status} />
                </div>
              </CardHeader>
              <CardContent>
                <div className="flex items-center justify-between text-sm text-muted-foreground">
                  <span>案件: {run.case_name}</span>
                  <span>当前步骤: {run.current_step}</span>
                  <span>{new Date(run.started_at).toLocaleString('zh-CN')}</span>
                </div>
                {run.status === 'waiting_human' && (
                  <div className="mt-3">
                    <Button
                      size="sm"
                      onClick={(e) => { e.stopPropagation(); setApprovalTarget(run) }}
                    >
                      审批
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* 详情面板 */}
      {selectedRun && (
        <WorkflowDetailPanel
          runId={selectedRun.run_id}
          onClose={() => setSelectedRun(null)}
        />
      )}

      {/* 审批弹窗 */}
      {approvalTarget && (
        <GateApprovalDialog
          open={!!approvalTarget}
          onOpenChange={(open) => !open && setApprovalTarget(null)}
          stepName={approvalTarget.current_step}
          caseName={approvalTarget.case_name}
          onApprove={(comment) =>
            approveMutation.mutate(
              { runId: approvalTarget.run_id, approved: true, comment },
              { onSuccess: () => setApprovalTarget(null) }
            )
          }
          onReject={(comment) =>
            approveMutation.mutate(
              { runId: approvalTarget.run_id, approved: false, comment },
              { onSuccess: () => setApprovalTarget(null) }
            )
          }
          isPending={approveMutation.isPending}
        />
      )}
    </div>
  )
}
