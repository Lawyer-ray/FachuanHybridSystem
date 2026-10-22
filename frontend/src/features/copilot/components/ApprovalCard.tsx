/**
 * 高危工具调用审批卡：agent 要执行删除/外发类操作时弹出，
 * 同意/拒绝后流继续；300 秒不决定服务端按拒绝处理（fail-closed），
 * 所以卡上带倒计时提醒。
 */

import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { shortToolName, previewToolArgs } from '../domain'
import { useCopilot } from '../store'
import type { PendingApproval } from '../types'

/** 服务端审批等待上限（backend approval.DEFAULT_TIMEOUT），fail-closed */
const APPROVAL_TIMEOUT_S = 300

function formatRemain(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

export function ApprovalCard({ approval }: { approval: PendingApproval }) {
  const decide = useCopilot((s) => s.decide)
  const [remain, setRemain] = useState(() =>
    Math.max(0, APPROVAL_TIMEOUT_S - Math.floor((Date.now() - approval.receivedAt) / 1000)),
  )

  useEffect(() => {
    if (approval.decided) return
    const timer = setInterval(() => {
      setRemain(Math.max(0, APPROVAL_TIMEOUT_S - Math.floor((Date.now() - approval.receivedAt) / 1000)))
    }, 1000)
    return () => clearInterval(timer)
  }, [approval.decided, approval.receivedAt])

  const expired = remain <= 0 && !approval.decided
  const argsPreview = previewToolArgs(approval.toolArgs)

  return (
    <div className="rounded-[10px] border border-destructive/40 bg-destructive/5 px-3 py-2.5">
      <div className="flex items-center gap-2">
        <span className="text-[12.5px] font-semibold text-foreground">需要确认：{shortToolName(approval.toolName)}</span>
        <span className="ml-auto text-[11px] tabular-nums text-muted-foreground">
          {approval.decided ? (approval.decided === 'approved' ? '已同意' : '已拒绝') : expired ? '已超时（按拒绝处理）' : formatRemain(remain)}
        </span>
      </div>
      <p className="mt-1 text-[12px] leading-relaxed text-secondary-foreground">{approval.message}</p>
      {argsPreview && (
        <p className="mt-1 font-mono text-[11px] break-all text-muted-foreground">{argsPreview}</p>
      )}
      {!approval.decided && !expired && (
        <div className="mt-2 flex gap-2">
          <Button
            variant="destructive"
            size="sm"
            className="h-7 px-3 text-[12px]"
            onClick={() => void decide(approval.approvalId, false)}
          >
            拒绝
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-7 px-3 text-[12px]"
            onClick={() => void decide(approval.approvalId, true)}
          >
            同意
          </Button>
        </div>
      )}
    </div>
  )
}
