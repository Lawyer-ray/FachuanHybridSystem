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
 */

import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { AlertTriangle, ShieldAlert } from 'lucide-react'

import {
  fetchPromoteCandidates,
  promoteMemory,
  type MemoryKind,
  type MemoryScopes,
  type PromoteCandidate,
} from '../memory-api'
import { Button } from '@/components/ui/button'
import { EmptyBlock, LoadingBlock } from '@/components/shared/AsyncState'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'

const KIND_LABEL: Record<MemoryKind, string> = {
  correction: '纠正',
  preference: '偏好',
  procedure: '惯例',
  fact: '事实',
  // 策展不提供「操作指引」：指引是该由管理员直接撰写的长篇规范，
  // 从个人短记忆「提炼」成 8000 字 SOP 不合理（见 MEMORY_KINDS 注释）。
  playbook: '操作指引',
}

/** 律所层只接受惯例/偏好——具体事实进律所层没有正当理由（与后端同口径） */
const LAW_FIRM_KINDS: MemoryKind[] = ['procedure', 'preference']
const TEAM_KINDS: MemoryKind[] = ['procedure', 'preference', 'fact']

/** 与后端 `_PII_PATTERNS` 同源的粗筛，只用于即时提示 */
const PII_RULES: { label: string; pattern: RegExp }[] = [
  { label: '身份证号', pattern: /\b\d{17}[\dXx]\b/ },
  { label: '手机号', pattern: /\b1[3-9]\d{9}\b/ },
  { label: '案号', pattern: /[（(]\s*\d{4}\s*[）)]\s*[\u4e00-\u9fa5]{0,4}\d{1,8}[\u4e00-\u9fa5]*\d*号/ },
  { label: '银行卡号', pattern: /\b\d{16,19}\b/ },
  { label: '完整当事人名称', pattern: /[\u4e00-\u9fa5]{4,20}(?:有限公司|有限责任公司|股份有限公司|事务所|中心|厂)/ },
]

function scanPii(text: string): string[] {
  return PII_RULES.filter((rule) => rule.pattern.test(text)).map((rule) => rule.label)
}

/** 归一化对比：与后端 `content_hash_of` 同口径，判断是否「原样提升」 */
function normalize(text: string): string {
  return text.split(/\s+/).filter(Boolean).join(' ')
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
  const [teamId, setTeamId] = useState<number | null>(null)
  const [selected, setSelected] = useState<string[]>([])
  const [content, setContent] = useState('')
  const [kind, setKind] = useState<MemoryKind>('procedure')
  // 律所层影响全所，需显式确认（与后端 acknowledged_firm_wide 对应）
  const [firmAck, setFirmAck] = useState(false)

  // useMemo 稳定引用：否则每次渲染都是新数组，下游 useEffect 的依赖恒变
  const curatableTeams = useMemo(() => scopes?.teams.filter((t) => t.can_curate) ?? [], [scopes])
  const canFirm = scopes?.law_firm.can_curate ?? false

  // 打开时默认落到第一个可策展目标，避免律师先看一个空面板
  useEffect(() => {
    if (!open) return
    const firstTeam = curatableTeams[0]
    if (firstTeam) {
      setTarget('team')
      setTeamId((prev) => prev ?? firstTeam.id)
    } else if (canFirm) {
      setTarget('law_firm')
      setTeamId(null)
    }
  }, [open, curatableTeams, canFirm])

  // 切到律所层时清掉 teamId（后端按 scope 校验，混传会被拒）
  useEffect(() => {
    if (target === 'law_firm') setTeamId(null)
    else setTeamId((prev) => prev ?? curatableTeams[0]?.id ?? null)
  }, [target, curatableTeams])

  // 律所层不允许「事实」——切层时把不合法类型拉回惯例
  useEffect(() => {
    if (target === 'law_firm' && !LAW_FIRM_KINDS.includes(kind)) setKind('procedure')
  }, [target, kind])

  // 离开律所层就清掉确认，避免「在团队层勾过、切到律所层后忘了」这种假确认
  useEffect(() => {
    if (target !== 'law_firm') setFirmAck(false)
  }, [target])

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
        acknowledgedFirmWide: target === 'law_firm' ? firmAck : false,
      }),
    onSuccess: onPromoted,
  })

  const candidates = useMemo<PromoteCandidate[]>(() => candidatesQuery.data ?? [], [candidatesQuery.data])
  const selectedCandidates = candidates.filter((c) => selected.includes(c.id))

  const trimmed = content.trim()
  const sameAsSource = selectedCandidates.some((c) => normalize(c.content) === normalize(trimmed))
  const draftPii = scanPii(trimmed)
  const kindOptions = target === 'law_firm' ? LAW_FIRM_KINDS : TEAM_KINDS

  const blocker =
    selected.length === 0
      ? '请至少选择一条来源记忆'
      : !trimmed
        ? '请写一条可复用的规则'
        : trimmed.length > 500
          ? '规则过长（上限 500 字）'
          : sameAsSource
            ? '不能原样提升，请改写成可复用的规则（脱敏）'
            : draftPii.length > 0
              ? `内容仍含敏感信息：${draftPii.join('、')}`
              : target === 'law_firm' && !firmAck
                ? '请先确认该规则将对全所所有律师生效'
                : ''

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
          {/* 左：候选池 */}
          <div className="flex min-h-0 flex-col">
            <div className="mb-2 flex flex-none items-center gap-1.5">
              <select
                aria-label="提升目标"
                value={target === 'team' ? `team:${teamId ?? ''}` : 'law_firm'}
                onChange={(e) => {
                  const value = e.target.value
                  if (value === 'law_firm') {
                    setTarget('law_firm')
                    return
                  }
                  setTarget('team')
                  setTeamId(Number(value.split(':')[1]))
                  setSelected([])
                }}
                className="h-7 rounded-[7px] border border-border bg-card px-2 text-[11px]"
              >
                {curatableTeams.map((team) => (
                  <option key={team.id} value={`team:${team.id}`}>
                    {team.name}（团队）
                  </option>
                ))}
                {canFirm && <option value="law_firm">全所</option>}
              </select>
              <span className="text-[11px] text-muted-foreground">已选 {selected.length}</span>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto rounded-[10px] border border-border">
              {candidatesQuery.isLoading ? (
                <LoadingBlock size="sm" className="py-4" />
              ) : candidates.length === 0 ? (
                <EmptyBlock className="items-start px-3 py-4 text-left leading-relaxed">
                  暂无可提炼的成员记忆。等成员积累了一些偏好后，这里会按使用频次列出候选。
                </EmptyBlock>
              ) : (
                <ul className="divide-y divide-border">
                  {candidates.map((candidate) => {
                    const checked = selected.includes(candidate.id)
                    return (
                      <li key={candidate.id}>
                        <label
                          className={`flex cursor-pointer items-start gap-2 px-2.5 py-2 transition-colors hover:bg-secondary/50 ${
                            checked ? 'bg-secondary/70' : ''
                          }`}
                        >
                          <input
                            type="checkbox"
                            className="mt-1 h-3.5 w-3.5 flex-none"
                            checked={checked}
                            onChange={(e) =>
                              setSelected((prev) =>
                                e.target.checked ? [...prev, candidate.id] : prev.filter((id) => id !== candidate.id),
                              )
                            }
                          />
                          <span className="min-w-0 flex-1">
                            <span className="block text-[12.5px] leading-relaxed text-foreground">
                              {candidate.content}
                            </span>
                            <span className="mt-1 flex flex-wrap items-center gap-1.5">
                              <span className="rounded-[4px] bg-secondary px-1 py-0.5 text-[10px] text-muted-foreground">
                                {KIND_LABEL[candidate.kind]}
                              </span>
                              {candidate.from_lawyer && (
                                <span className="text-[10px] text-muted-foreground">{candidate.from_lawyer}</span>
                              )}
                              {candidate.hit_count > 0 && (
                                <span className="text-[10px] text-muted-foreground/80">
                                  用过 {candidate.hit_count} 次
                                </span>
                              )}
                              {candidate.pii_risk.length > 0 && (
                                <span
                                  className="flex items-center gap-0.5 text-[10px] text-amber-600 dark:text-amber-500"
                                  title="含敏感信息，改写时务必脱敏"
                                >
                                  <ShieldAlert className="h-2.5 w-2.5" />
                                  需脱敏
                                </span>
                              )}
                            </span>
                          </span>
                        </label>
                      </li>
                    )
                  })}
                </ul>
              )}
            </div>
          </div>

          {/* 右：改写框 */}
          <div className="flex min-h-0 flex-col">
            <div className="mb-2 flex flex-none items-center gap-1.5">
              <select
                aria-label="规则类型"
                value={kind}
                onChange={(e) => setKind(e.target.value as MemoryKind)}
                className="h-7 rounded-[7px] border border-border bg-card px-2 text-[11px]"
              >
                {kindOptions.map((k) => (
                  <option key={k} value={k}>
                    {KIND_LABEL[k]}
                  </option>
                ))}
              </select>
              <span className="text-[11px] text-muted-foreground">{trimmed.length}/500</span>
            </div>

            <Textarea
              aria-label="改写后的规则"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="例如：劳动争议类案件回复客户时，先确认是否已过仲裁时效，再谈分期方案"
              className="min-h-[140px] flex-1 resize-none text-[13px]"
            />

            <div className="mt-2 flex-none space-y-1.5">
              {selectedCandidates.length > 0 && (
                <p className="text-[11px] leading-relaxed text-muted-foreground">
                  来源：{selectedCandidates.length} 条成员记忆
                </p>
              )}
              {sameAsSource && (
                <p className="flex items-start gap-1 text-[11px] leading-relaxed text-amber-600 dark:text-amber-500">
                  <AlertTriangle className="mt-0.5 h-3 w-3 flex-none" />
                  与来源原文相同——请提炼成适用范围更广的规则
                </p>
              )}
              {draftPii.length > 0 && (
                <p className="flex items-start gap-1 text-[11px] leading-relaxed text-destructive">
                  <ShieldAlert className="mt-0.5 h-3 w-3 flex-none" />
                  含 {draftPii.join('、')}，请去掉具体信息
                </p>
              )}
              {target === 'law_firm' && (
                <>
                  <p className="text-[11px] leading-relaxed text-muted-foreground">
                    律所层只接受「惯例」或「偏好」——具体事实不属于全所规范。
                  </p>
                  <label className="flex cursor-pointer items-start gap-1.5 text-[11px] leading-relaxed text-foreground">
                    <input
                      type="checkbox"
                      className="mt-0.5 h-3 w-3 flex-none"
                      checked={firmAck}
                      onChange={(e) => setFirmAck(e.target.checked)}
                    />
                    <span>我确认：这条规则将对**全所所有律师**的 AI 助手生效</span>
                  </label>
                </>
              )}
            </div>
          </div>
        </div>

        {promoteMutation.isError && (
          <p className="text-[11px] text-destructive">提交失败：{promoteMutation.error.message}</p>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button disabled={Boolean(blocker) || promoteMutation.isPending} onClick={() => promoteMutation.mutate()}>
            {promoteMutation.isPending ? '提交中…' : '提炼'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
