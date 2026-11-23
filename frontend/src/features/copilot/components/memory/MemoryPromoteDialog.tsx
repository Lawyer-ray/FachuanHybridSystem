/**
 * 策展提升对话框：把成员的个人记忆提炼为团队/律所级规则。
 *
 * ## 为什么是「挑选 + 强制改写」而不是「一键合并」
 *
 * 自动聚合个人记忆会产出三类有害结果（后端 `approve_memory` 三道闸门对应）：
 *
 * | 场景 | 聚合后果 |
 * |:-|:-|
 * | A「这个客户同意分期」+ B「这个客户拒绝分期」 | 模型看到矛盾，输出不稳定 |
 * | A 的个人风格进团队层 | 强加给全所 |
 * | A 记住了保密和解金额 | 团队可见即泄密 |
 *
 * 所以本对话框的交互顺序刻意是「**先看候选 → 再自己写规则 → 最后选来源**」，
 * 而不是「勾选后点合并」。改写框必填且不得与来源原文相同——这一条既完成脱敏，
 * 也把「具体案件事实」挡在跨人可见层之外。
 *
 * ## PII 前置提示
 *
 * 候选里命中的敏感模式（`pii_risk`）直接在行上标出，改写框实时跑同一套规则
 * （身份证/手机/案号/银行卡/完整当事人名），让律师一次填对，而不是提交后
 * 被后端拒绝、再猜哪里不对。
 *
 * ## 跨层修正走渲染期派生值，不用 useEffect
 *
 * 「切到律所层清 teamId」「律所层不允许事实」「离开律所层清确认」三条曾是三条
 * useEffect 互相纠正 state——多渲染一趟才收敛，还容易与候选查询的 enabled 判定
 * 错位。现在只在 `open` 时写一次默认目标（唯一一条 effect），其余全部在渲染期
 * 派生（`teamId` / `kind` / `effectiveFirmAck`），提交也用派生值，保证「界面显示
 * 什么就提交什么」。
 *
 * 拆分记录：草稿状态与跨层派生值在 `use-promote-draft`；本文件只留候选查询、提交
 * 与外壳。
 */

import type { MemoryScopes } from '../../types'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { PromoteCandidatesPanel } from './PromoteCandidatesPanel'
import { PromoteRuleEditor } from './PromoteRuleEditor'
import { usePromoteDraft } from './use-promote-draft'
import { usePromoteSubmission } from './use-promote-submission'

export function MemoryPromoteDialog({
  open,
  onOpenChange,
  scopes,
  onPromoted,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  scopes: MemoryScopes | undefined
  onPromoted: () => void
}) {
  const draft = usePromoteDraft({ open, scopes })
  const { candidates, loading, selectedCandidates, sameAsSource, draftPii, blocker, submitting, submitError, submit } =
    usePromoteSubmission({ open, draft, onPromoted })
  const { target, teamId, kind, content, selected, firmAck, setKind, setContent, setFirmAck, changeTarget, toggleSelected } =
    draft

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] sm:max-w-[min(720px,calc(100vw-2rem))] flex-col">
        <DialogHeader>
          <DialogTitle>提炼为团队/律所规则</DialogTitle>
          <DialogDescription>
            从成员的记忆里挑出共性，改写成一条不含具体案件信息的规则。改写是必须的——原样共享会把某个客户的事实带进全所可见范围。
          </DialogDescription>
        </DialogHeader>

        <div className="grid min-h-0 flex-1 gap-4 overflow-hidden md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <PromoteCandidatesPanel
            target={target}
            teamId={teamId}
            scopes={scopes}
            candidates={candidates}
            loading={loading}
            selected={selected}
            onTargetChange={changeTarget}
            onToggleSelected={toggleSelected}
          />
          <PromoteRuleEditor
            target={target}
            kind={kind}
            onKindChange={setKind}
            content={content}
            onContentChange={setContent}
            sourceCount={selectedCandidates.length}
            sameAsSource={sameAsSource}
            draftPii={draftPii}
            firmAck={firmAck}
            onFirmAckChange={setFirmAck}
          />
        </div>

        {submitError && <p className="text-[11px] text-destructive">提交失败：{submitError}</p>}
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>取消</Button>
          <Button disabled={Boolean(blocker) || submitting} onClick={submit}>
            {submitting ? '提交中…' : '提炼'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
