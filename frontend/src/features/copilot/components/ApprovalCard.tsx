/**
 * 高危工具调用审批卡：agent 要执行删除/外发类操作时弹出，
 * 同意/拒绝后流继续；不决定服务端按拒绝处理（fail-closed），
 * 所以卡上带倒计时提醒。
 *
 * 风险分级（后端 approval.py 四级）：
 * - high：默认红调卡（与旧版一致）
 * - critical：更深红 + 图标，同意需**二次确认**（首击只「解锁」，再击才提交）
 * - 离线待审（后台任务挂起的，从 /approvals/pending 拉回）：琥珀色卡 +
 *   「后台任务」标记，倒计时按 7200s（OFFLINE_TIMEOUT）从服务端创建时间起算
 */

import { useEffect, useState } from 'react'
import { AlertTriangle, Clock, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { approvalWindowSec, previewToolArgs, shortToolName } from '../domain'
import { useCopilot } from '../store'
import type { PendingApproval } from '../types'

/** 二次确认的回退时间：解锁后 8 秒不点就收回去（防误触解锁后长期停留） */
const SECOND_CONFIRM_RESET_MS = 8000

function formatRemain(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

export function ApprovalCard({ approval }: { approval: PendingApproval }) {
  const decide = useCopilot((s) => s.decide)
  const dismissApproval = useCopilot((s) => s.dismissApproval)
  const [armed, setArmed] = useState(false)
  const [showReason, setShowReason] = useState(false)
  const [reasonText, setReasonText] = useState('')
  const [remain, setRemain] = useState(() =>
    Math.max(0, approvalWindowSec(approval.riskLevel, approval.offline)),
  )

  const windowSec = approvalWindowSec(approval.riskLevel, approval.offline)
  const isCritical = approval.riskLevel === 'critical' || approval.needsSecondConfirmation === true
  const needSecondConfirm = isCritical && !approval.offline

  // 离线卡的 receivedAt 来自服务端 created_at（可能已挂起多时），统一按它算剩余
  useEffect(() => {
    setRemain(Math.max(0, windowSec - Math.floor((Date.now() - approval.receivedAt) / 1000)))
  }, [windowSec, approval.receivedAt])

  useEffect(() => {
    if (approval.decided) return
    const timer = setInterval(() => {
      setRemain(Math.max(0, windowSec - Math.floor((Date.now() - approval.receivedAt) / 1000)))
    }, 1000)
    return () => clearInterval(timer)
  }, [approval.decided, approval.receivedAt, windowSec])

  // 二次确认解锁后 8 秒不动作就收回（保持「紧急操作必须想清楚」的语义）
  useEffect(() => {
    if (!armed || approval.decided) return
    const timer = setTimeout(() => setArmed(false), SECOND_CONFIRM_RESET_MS)
    return () => clearTimeout(timer)
  }, [armed, approval.decided])

  const expired = remain <= 0 && !approval.decided
  const argsPreview = previewToolArgs(approval.toolArgs)

  const cardCls = approval.offline
    ? 'rounded-[10px] border border-amber-500/50 bg-amber-500/5 px-3 py-2.5'
    : isCritical
      ? 'rounded-[10px] border border-destructive/70 bg-destructive/10 px-3 py-2.5'
      : 'rounded-[10px] border border-destructive/40 bg-destructive/5 px-3 py-2.5'

  const onApproveClick = () => {
    if (needSecondConfirm && !armed) {
      setArmed(true)
      return
    }
    void decide(approval.approvalId, true)
  }

  return (
    <div className={cardCls}>
      <div className="flex items-center gap-2">
        {isCritical && <AlertTriangle className="h-3.5 w-3.5 flex-none text-destructive" />}
        {approval.offline && <Clock className="h-3.5 w-3.5 flex-none text-amber-600 dark:text-amber-400" />}
        <span className="text-[12.5px] font-semibold text-foreground">需要确认：{shortToolName(approval.toolName)}</span>
        {isCritical && !approval.offline && (
          <span className="rounded-[4px] bg-destructive/15 px-1 py-px text-[10.5px] font-medium text-destructive">紧急</span>
        )}
        {approval.offline && (
          <span className="rounded-[4px] bg-amber-500/15 px-1 py-px text-[10.5px] font-medium text-amber-700 dark:text-amber-400">
            后台任务
          </span>
        )}
        <span className="ml-auto flex flex-none items-center gap-1.5 text-[11px] tabular-nums text-muted-foreground">
          {approval.decided
            ? approval.decided === 'approved'
              ? '已同意'
              : '已拒绝'
            : expired
              ? '已超时（按拒绝处理）'
              : formatRemain(remain)}
          {/* 已决/已超时的卡可关闭：僵尸卡不再永久占屏（服务端已按拒绝处理，本地移除无副作用） */}
          {(approval.decided || expired) && (
            <button
              type="button"
              className="flex h-5 w-5 items-center justify-center rounded-[5px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
              aria-label="关闭此审批卡"
              title="关闭（该操作已按拒绝/你的决定处理完毕）"
              onClick={() => dismissApproval(approval.approvalId)}
            >
              <X className="h-3 w-3" />
            </button>
          )}
        </span>
      </div>
      {(approval.message || approval.offline) && (
        <p className="mt-1 text-[12px] leading-relaxed text-secondary-foreground">
          {approval.message || '后台运行的任务在等待你确认这个高危操作，同意后会继续执行。'}
        </p>
      )}
      {argsPreview && (
        <p className="mt-1 font-mono text-[11px] break-all text-muted-foreground">{argsPreview}</p>
      )}
      {!approval.decided && !expired && (
        <div className="mt-2 flex gap-2">
          <Button
            variant="destructive"
            size="sm"
            className="h-7 px-3 text-[12px]"
            onClick={() => {
              if (showReason) {
                void decide(approval.approvalId, false, reasonText.trim())
              } else {
                setShowReason(true) // 先展开理由输入，再点一次才真正拒绝
              }
            }}
          >
            {showReason ? '确认拒绝' : '拒绝'}
          </Button>
          <Button
            variant={needSecondConfirm && armed ? 'destructive' : 'outline'}
            size="sm"
            className="h-7 px-3 text-[12px]"
            onClick={onApproveClick}
          >
            {needSecondConfirm ? (armed ? '再次确认执行' : '同意') : '同意'}
          </Button>
        </div>
      )}
      {needSecondConfirm && armed && !approval.decided && !expired && (
        <p className="mt-1 text-[11px] text-destructive">这是不可恢复的批量操作，请确认上方工具名后再点击。</p>
      )}
      {showReason && !approval.decided && !expired && (
        <div className="mt-2 flex gap-1.5">
          <input
            autoFocus
            value={reasonText}
            maxLength={200}
            placeholder="拒绝理由（选填，AI 会据此调整方案）"
            className="h-7 min-w-0 flex-1 rounded-[8px] border border-input bg-background px-2 text-[12px] text-foreground outline-none focus:border-foreground/40"
            onChange={(e) => setReasonText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void decide(approval.approvalId, false, reasonText.trim())
              if (e.key === 'Escape') setShowReason(false)
            }}
          />
          <button
            type="button"
            className="flex-none rounded-[6px] px-1.5 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
            onClick={() => setShowReason(false)}
          >
            取消
          </button>
        </div>
      )}
    </div>
  )
}
