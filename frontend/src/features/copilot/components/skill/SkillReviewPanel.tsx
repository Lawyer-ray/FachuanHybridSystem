/**
 * 审批人的工作台（抽屉内的二级视图）：diff + 提交说明 + 安全告警 + 通过/驳回。
 *
 * 三条判据写在这里，因为它们是这个文件存在的理由：
 *
 * 1. **入口只认服务端 `can_*`**：`SkillRow` 在 `can_review && review_status==='pending'`
 *    时才给「审核」按钮。前端判 `is_admin` 等于把权限口径复制一份，还会在「管理员但
 *    不在本所」这类边界上与后端打架。
 * 2. **驳回必须先写理由**：作者下一步只能按这句话改，空备注等于让他盲改。所以本地先拦
 *    一道字段级错误，服务端的 409/422 文案再走 `errMessage` 落到同一处。
 * 3. **「全所确认」只在服务端要求时出现**：管理员自审自发才需要勾
 *    （`permissions.requires_firm_wide_ack`）。默认就勾、或默认就拦着不让提交，都会把
 *    这一次确认变成盲点——**第一次通过先不带该字段**，收到 422 且文案提到「全所」时才
 *    把勾选框亮出来。这条判据只能靠服务端的那句话，前端无法预判。
 *
 * 安全告警的来源是 `POST /skills/validate`（服务端暂无「按待审快照取命中」的端点）：
 * 先取工作区正文再校验。作者提审后又接着改工作区时，这里看到的命中可能与待审快照不同
 * ——**权威闸门是 approve 时对即将生效快照的复扫**，所以本面板不因为 hard 命中就禁用
 * 「通过」，只把命中明确展示出来。
 *
 * diff 的缺省口径是「线上生效版 vs 工作区」（服务端 `review.diff_versions` 的缺省），
 * 所以这里不传 `v1`/`v2`：传错版本号会让审批人对着两份都不是待审内容的文本做决定。
 */

import { useMutation, useQuery } from '@tanstack/react-query'
import { HTTPError } from 'ky'
import { ArrowLeft } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { ErrorBlock, LoadingBlock } from '@/components/shared/AsyncState'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { errMessage } from '@/lib/errors'

import { fetchAgentSkill, fetchAgentSkillDiff, reviewAgentSkill, validateAgentSkill } from '../../skill-api'
import type { AgentSkill, AgentSkillFinding, AgentSkillReviewInput } from '../../skill-types'
import { SkillDiffView } from './SkillDiffView'
import { SkillTrialPanel } from './SkillTrialPanel'
import { useSkillMutations } from './use-skill-mutations'

/** 告警字段的中文说法（`field` 是服务端的 title/description/body） */
const FINDING_FIELD_LABELS: Record<string, string> = {
  title: '显示名',
  description: '描述',
  body: '正文',
}

/**
 * 安全告警列表：审批面板与提审对话框共用一套展示口径（同一份 `AgentSkillFinding`，
 * 两边各写一遍就会出现「审批人看到红、作者看到黄」这种对不上的颜色）。
 */
export function SkillFindingList({ findings }: { findings: AgentSkillFinding[] }) {
  return (
    <ul className="space-y-1 rounded-[9px] border border-border bg-card px-2.5 py-2">
      {findings.map((finding, index) => (
        <FindingRow key={`${finding.code}-${finding.field}-${index}`} finding={finding} />
      ))}
    </ul>
  )
}

/** 一条告警：hard 红（服务端会拒绝发布）、soft 黄（需要人判断） */
function FindingRow({ finding }: { finding: AgentSkillFinding }) {
  const hard = finding.level === 'hard'
  return (
    <li className="flex flex-wrap items-baseline gap-1.5">
      <StatusBadge tone={hard ? 'red' : 'yellow'} size="xs">
        {hard ? '硬拦截' : '需确认'}
      </StatusBadge>
      <span className="text-[11px] text-foreground">
        {FINDING_FIELD_LABELS[finding.field] ?? finding.field}：{finding.message}
      </span>
      {finding.excerpt ? (
        // 只展示脱敏片段（服务端已把身份证/手机号留首尾各 2 位），不把整段正文搬出来
        <code className="rounded-[4px] bg-secondary px-1 py-0.5 font-mono text-[10.5px] text-muted-foreground">
          {finding.excerpt}
        </code>
      ) : null}
    </li>
  )
}

export function SkillReviewPanel({
  skill,
  onClose,
  onReviewed,
}: {
  skill: AgentSkill
  /** 返回列表（不写任何东西） */
  onClose: () => void
  /** 审批成功：抽屉据此失效清单缓存并回到列表 */
  onReviewed: () => void
}) {
  const { invalidate } = useSkillMutations()
  const [note, setNote] = useState('')
  const [noteError, setNoteError] = useState('')
  const [firmAck, setFirmAck] = useState(false)
  const [firmAckRequired, setFirmAckRequired] = useState(false)
  const [actionError, setActionError] = useState('')

  const diffQuery = useQuery({
    queryKey: ['agent-skill-diff', skill.key],
    queryFn: () => fetchAgentSkillDiff(skill.key),
  })
  /** 安全命中：工作区正文 → `/skills/validate`（本面板只看 `safety`，不看字段错误） */
  const findingsQuery = useQuery({
    queryKey: ['agent-skill-findings', skill.key],
    queryFn: async () => {
      const detail = await fetchAgentSkill(skill.key)
      const result = await validateAgentSkill({
        name: detail.name,
        title: detail.title,
        description: detail.description,
        body: detail.body,
      })
      return result.safety ?? []
    },
    staleTime: 30_000,
  })

  const reviewMutation = useMutation({
    mutationFn: (input: AgentSkillReviewInput) => reviewAgentSkill(skill.key, input),
  })

  const findings = findingsQuery.data ?? []
  const busy = reviewMutation.isPending

  const submitReview = async (decision: 'approve' | 'reject') => {
    setActionError('')
    const trimmed = note.trim()
    if (decision === 'reject' && !trimmed) {
      setNoteError('驳回理由必填——作者只能按这句话改，不写等于让他盲改')
      return
    }
    if (decision === 'approve' && firmAckRequired && !firmAck) {
      setActionError('请先勾选「我已确认这条指令在全所范围内成立」再通过')
      return
    }
    try {
      await reviewMutation.mutateAsync({
        decision,
        ...(trimmed ? { note: trimmed } : {}),
        // 只有被服务端要求过、且这次真勾了才带：默认不带是刻意的（见文件头第 3 条）
        ...(decision === 'approve' && firmAck ? { acknowledged_firm_wide: true } : {}),
      })
      toast.success(decision === 'approve' ? `已通过「${skill.title}」` : `已驳回「${skill.title}」`, {
        description:
          decision === 'approve' ? '线上正文已换成这次提审的版本，下一轮对话生效' : '线上仍是上一版，作者可按理由修改后重新提审',
      })
      invalidate()
      onReviewed()
    } catch (error) {
      const status = error instanceof HTTPError ? error.response.status : 0
      const message = errMessage(error, '审批失败，请稍后重试')
      // 422 且文案提到「全所」= 服务端要管理员先确认影响面（管理员自审自发）。只在这时
      // 把勾选框亮出来：前端无法预判这条，猜错任一方向都会让确认流于形式。
      if (decision === 'approve' && status === 422 && message.includes('全所')) {
        setFirmAckRequired(true)
        setActionError(message)
        return
      }
      setActionError(message)
    }
  }

  return (
    <div>
      <div className="mb-3 flex items-center gap-2">
        <Button variant="ghost" size="sm" className="h-7 gap-1 px-1.5 text-[11px]" onClick={onClose}>
          <ArrowLeft className="h-3 w-3" />
          返回
        </Button>
        <span className="truncate text-[13px] font-semibold text-foreground">审核「{skill.title}」</span>
        <code className="truncate font-mono text-[10.5px] text-muted-foreground/80">{skill.name}</code>
      </div>

      {diffQuery.isLoading ? (
        <LoadingBlock size="sm" text="正在拉取改动对比…" />
      ) : diffQuery.isError ? (
        <ErrorBlock error={diffQuery.error} fallback="改动对比加载失败" onRetry={() => void diffQuery.refetch()} />
      ) : diffQuery.data ? (
        <SkillDiffView diff={diffQuery.data} />
      ) : null}

      {skill.review_note ? (
        <section className="mt-3">
          <h3 className="mb-1 text-[11.5px] font-[650] text-foreground">提交说明</h3>
          <p className="whitespace-pre-wrap rounded-[9px] border border-border bg-card px-2.5 py-2 text-[11.5px] leading-relaxed text-muted-foreground">
            {skill.review_note}
          </p>
        </section>
      ) : null}

      <section className="mt-3">
        <h3 className="mb-1 text-[11.5px] font-[650] text-foreground">安全告警</h3>
        {findingsQuery.isLoading ? (
          <p className="text-[11px] text-muted-foreground">正在检查敏感信息与提示注入措辞…</p>
        ) : findingsQuery.isError ? (
          // 检查失败不妨碍审批（真正的闸门在服务端 approve），但要说清「没检查到」≠「干净」
          <p className="text-[11px] text-status-yellow">安全告警未能取到：{errMessage(findingsQuery.error, '请稍后重试')}</p>
        ) : findings.length === 0 ? (
          <p className="text-[11px] text-muted-foreground">未命中身份证、手机号、案号、凭证或提示注入措辞。</p>
        ) : (
          <SkillFindingList findings={findings} />
        )}
      </section>

      {/*
        试跑放在审批动作之前：审批人要凭「模型真读了一遍之后是什么效果」做决定，所以它
        必须和 diff / 安全告警在同一屏，而不是藏进另一层弹窗。可见性只看服务端能力位
        （`can_review`）或本人可编辑——前端不判 is_admin。
      */}
      {skill.can_review || skill.editable ? <SkillTrialPanel skill={skill} /> : null}

      <section className="mt-3">
        <label htmlFor="skill-review-note" className="mb-1 block text-[11.5px] font-[650] text-foreground">
          驳回理由（驳回时必填）
        </label>
        <Textarea
          id="skill-review-note"
          value={note}
          onChange={(event) => {
            setNote(event.target.value)
            if (noteError) setNoteError('')
          }}
          placeholder="例如：第 3 段引用的送达期限已过期，按新民诉法改后再提审"
          className="min-h-[64px] text-[12px]"
          aria-invalid={Boolean(noteError)}
        />
        {noteError ? (
          <p role="alert" className="mt-1 text-[10.5px] leading-relaxed text-destructive">
            {noteError}
          </p>
        ) : (
          <p className="mt-1 text-[10.5px] leading-relaxed text-muted-foreground">
            通过时可以不写；驳回时不写理由，作者就不知道该改哪里。
          </p>
        )}
      </section>

      {firmAckRequired ? (
        <div className="mt-3 rounded-[9px] border border-status-yellow/50 bg-status-yellow-bg px-2.5 py-2">
          <label className="flex items-start gap-2 text-[11px] leading-relaxed text-foreground">
            <input
              type="checkbox"
              className="mt-[3px]"
              checked={firmAck}
              onChange={(event) => setFirmAck(event.target.checked)}
            />
            我已确认这条指令在全所范围内成立
          </label>
        </div>
      ) : null}

      {actionError ? (
        <p role="alert" className="mt-2 text-[11px] leading-relaxed text-destructive">
          {actionError}
        </p>
      ) : null}

      <div className="mt-4 flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          className="h-7 px-3 text-[11px]"
          disabled={busy}
          onClick={() => void submitReview('reject')}
        >
          驳回
        </Button>
        <Button size="sm" className="ml-auto h-7 px-3 text-[11px]" disabled={busy} onClick={() => void submitReview('approve')}>
          {busy ? '提交中…' : '通过'}
        </Button>
      </div>
    </div>
  )
}
