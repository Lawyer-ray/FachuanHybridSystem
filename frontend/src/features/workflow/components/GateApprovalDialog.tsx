/**
 * 审批弹窗
 */
import { useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'

interface GateApprovalDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  stepName: string
  caseName: string
  onApprove: (comment: string) => void
  onReject: (comment: string) => void
  isPending?: boolean
}

export function GateApprovalDialog({
  open,
  onOpenChange,
  stepName,
  caseName,
  onApprove,
  onReject,
  isPending,
}: GateApprovalDialogProps) {
  const [comment, setComment] = useState('')

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>审批确认</DialogTitle>
          <DialogDescription>
            案件: {caseName} · 步骤: {stepName}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="comment">审批意见（可选）</Label>
          <Textarea
            id="comment"
            placeholder="输入审批意见..."
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
        </div>
        <DialogFooter className="gap-2">
          <Button
            variant="destructive"
            onClick={() => { onReject(comment); setComment('') }}
            disabled={isPending}
          >
            拒绝
          </Button>
          <Button
            onClick={() => { onApprove(comment); setComment('') }}
            disabled={isPending}
          >
            {isPending ? '处理中...' : '通过'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
