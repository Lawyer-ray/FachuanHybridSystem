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
 */

import { useEffect, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'

import { fetchPromoteCandidates, promoteMemory, type MemoryKind, type MemoryScopes } from '../../memory-api'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { LAW_FIRM_KINDS, MAX_RULE_CHARS } from './labels'
import { PromoteRuleEditor } from './PromoteRuleEditor'
import { PromoteCandidatesPanel } from './PromoteCandidatesPanel'
import { normalize, scanPii } from './pii'

/** 提交闸门的前置拦截：返回第一条不满足的原因（空串 = 可提交） */
function findBlocker(input: {
  selectedCount: number
  trimmed: string
  sameAsSource: boolean
  draftPii: string[]
  target: 'team' | 'law_firm'
  firmAck: boolean
}): string {
  if (input.selectedCount === 0) return '请至少选择一条来源记忆'
  if (!input.trimmed) return '请写一条可复用的规则'
  if (input.trimmed.length > MAX_RULE_CHARS) return `规则过长（上限 ${MAX_RULE_CHARS} 字）`
  if (input.sameAsSource) return '不能原样提升，请改写成可复用的规则（脱敏）'
  if (input.draftPii.length > 0) return `内容仍含敏感信息：${input.draftPii.join('、')}`
  if (input.target === 'law_firm' && !input.firmAck) return '请先确认该规则将对全所所有律师生效'
  return ''
}

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
  const [target, setTarget] = useState<'team' | 'law_firm'>('team')
  const [pickedTeamId, setTeamId] = useState<number | null>(null)
  const [selected, setSelected] = useState<string[]>([])
  const [content, setContent] = useState('')
  const [pickedKind, setKind] = useState<MemoryKind>('procedure')
  // 律所层影响全所，需显式确认（与后端 acknowledged_firm_wide 对应）
  const [firmAck, setFirmAck] = useState(false)

  const curatableTeams = scopes?.teams.filter((t) => t.can_curate) ?? []
  const canFirm = scopes?.law_firm.can_curate ?? false
  const firstTeamId = curatableTeams[0]?.id ?? null

  // 唯一保留的 effect：打开时落到第一个可策展目标，避免律师先看一个空面板。
  // 依赖里刻意不带 curatableTeams——否则 scopes 一到就重跑，把律师已选的团队冲掉。
  useEffect(() => {
    if (!open) return
    if (firstTeamId !== null) {
      setTarget('team')
      setTeamId((prev) => prev ?? firstTeamId)
    } else if (canFirm) {
      setTarget('law_firm')
      setTeamId(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  // 三条跨层修正都在渲染期派生：律所层不带 teamId（后端按 scope 校验，混传会被拒）、
  // 律所层不允许「事实」（非法类型拉回惯例）、离开律所层不认之前的确认
  // （避免「在团队层勾过、切到律所层后忘了」这种假确认）
  const teamId = target === 'law_firm' ? null : (pickedTeamId ?? firstTeamId)
  const kind = target === 'law_firm' && !LAW_FIRM_KINDS.includes(pickedKind) ? 'procedure' : pickedKind
  const effectiveFirmAck = target === 'law_firm' && firmAck

  const candidatesQuery = useQuery({
    queryKey: ['copilot', 'memory', 'candidates', target, teamId],
    queryFn: () =>
      fetchPromoteCandidates({
        scope: target,
        teamId: target === 'team' ? (teamId ?? undefined) : undefined,
      }),
    enabled: open && (target === 'law_firm' ? canFirm : teamId != null),
    staleTime: 60_000,
  })

  const promoteMutation = useMutation({
    mutationFn: () =>
      promoteMemory({
        sourceIds: selected,
        content: content.trim(),
        kind,
        scope: target,
        teamId: target === 'team' ? (teamId ?? undefined) : undefined,
        acknowledgedFirmWide: effectiveFirmAck,
      }),
    onSuccess: onPromoted,
  })

  const candidates = candidatesQuery.data ?? []
  const selectedCandidates = candidates.filter((c) => selected.includes(c.id))
  const trimmed = content.trim()
  const sameAsSource = selectedCandidates.some((c) => normalize(c.content) === normalize(trimmed))
  const draftPii = scanPii(trimmed)
  const blocker = findBlocker({
    selectedCount: selected.length,
    trimmed,
    sameAsSource,
    draftPii,
    target,
    firmAck: effectiveFirmAck,
  })

  /** 换目标：换团队/换层都要清空已选（旧候选的 id 不属于新池） */
  const handleTargetChange = (next: 'team' | 'law_firm', nextTeamId: number | null) => {
    setTarget(next)
    setTeamId(nextTeamId)
    setSelected([])
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] max-w-[min(720px,calc(100vw-2rem))] flex-col">
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
            loading={candidatesQuery.isLoading}
            selected={selected}
            onTargetChange={handleTargetChange}
            onToggleSelected={(id, checked) =>
              setSelected((prev) => (checked ? [...prev, id] : prev.filter((item) => item !== id)))
            }
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
            firmAck={effectiveFirmAck}
            onFirmAckChange={setFirmAck}
          />
        </div>

        {promoteMutation.isError && <p className="text-[11px] text-destructive">提交失败：{promoteMutation.error.message}</p>}
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>取消</Button>
          <Button disabled={Boolean(blocker) || promoteMutation.isPending} onClick={() => promoteMutation.mutate()}>
            {promoteMutation.isPending ? '提交中…' : '提炼'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
