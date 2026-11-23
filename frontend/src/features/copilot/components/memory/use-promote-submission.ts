/**
 * 策展提升的写入面：候选查询 + 提交 mutation + 提交闸门。
 *
 * 从 `MemoryPromoteDialog` 拆出（后者单函数超软红线）。候选查询的 key/enabled 判据与
 * 闸门判定必须贴着目标层走（换代团队/换层后旧候选的 id 不属于新池），所以两者同文件；
 * 草稿状态本身在 `use-promote-draft`。
 *
 * 闸门是**后端三道校验的前置拦截**：未选来源 / 原样提升 / 含敏感信息 / 律所层未确认，
 * 任一命中就不让提交——目的是律师一次填对，而不是提交后猜哪里被拒。
 */

import { useMutation, useQuery } from '@tanstack/react-query'

import { fetchPromoteCandidates, promoteMemory } from '../../memory-api'
import { MAX_RULE_CHARS } from './labels'
import { normalize, scanPii } from './pii'
import type { usePromoteDraft } from './use-promote-draft'

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

export function usePromoteSubmission({
  open,
  draft,
  onPromoted,
}: {
  open: boolean
  /** 草稿状态（目标层 / 团队 / 已选来源 / 规则正文 / 律所层确认） */
  draft: ReturnType<typeof usePromoteDraft>
  /** 提交成功后的回调（外层关窗 + 失效缓存） */
  onPromoted: () => void
}) {
  const { target, teamId, canFirm, kind, content, selected, firmAck } = draft

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
        acknowledgedFirmWide: firmAck,
      }),
    onSuccess: onPromoted,
  })

  const candidates = candidatesQuery.data ?? []
  const selectedCandidates = candidates.filter((candidate) => selected.includes(candidate.id))
  const trimmed = content.trim()
  const sameAsSource = selectedCandidates.some((candidate) => normalize(candidate.content) === normalize(trimmed))
  const draftPii = scanPii(trimmed)
  const blocker = findBlocker({
    selectedCount: selected.length,
    trimmed,
    sameAsSource,
    draftPii,
    target,
    firmAck,
  })

  return {
    candidates,
    loading: candidatesQuery.isLoading,
    /** 已选中的候选（右栏显示「N 条来源」与是否原样提升都按它算） */
    selectedCandidates,
    sameAsSource,
    draftPii,
    /** 非空 = 不能提交，文案即原因 */
    blocker,
    submitting: promoteMutation.isPending,
    /** 提交失败的原因（null = 无错） */
    submitError: promoteMutation.isError ? promoteMutation.error.message : null,
    submit: () => promoteMutation.mutate(),
  }
}
