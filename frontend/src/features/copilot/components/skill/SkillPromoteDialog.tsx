/**
 * 提审 / 发布对话框：把**一条**技能送去审批（个人 → 团队/所内，或共享层的工作区改动）。
 *
 * 与记忆策展那个 `MemoryPromoteDialog` 的关系只是「外壳像」：那边是「多选候选 → 改写
 * 成一条规则」，技能这边是**单条 4 字段结构化表单**，没有候选池可挑。所以这里刻意不
 * 照搬它的候选面板，只借用外壳（Dialog + 就地区块错误 + 影响面勾选）。
 *
 * 四个字段：
 * 1. **显示名**：只读（改标题是编辑器的活，发布不该顺手改文案）；
 * 2. **技能名（slug）**：只在「个人 → 共享」这条路径上可改——目标层已有同名技能时，
 *    不改名就只能等对方下线（服务端撞名回 409）。提交前先走 `/skills/validate`，
 *    撞名/保留字/格式错误**就地**落在输入框下方，而不是弹一句笼统的「提交失败」；
 * 3. **目标层**：只渲染服务端 `promotable_scopes` 给的那几层（前端不硬编码，也不拿
 *    `is_admin` 猜）；共享层的条目原地提审，目标层不可改；
 * 4. **备注**：给审批人看的说明（改了什么、为什么现在要改）。
 *
 * 安全闸门：`hard` 命中直接挡住提交（服务端也会拒），`soft` 命中必须逐条勾选确认——
 * soft 是「像敏感信息但可能是必要引用」，只有作者能判断，所以不替他决定。
 *
 * 团队层不给「选哪个团队」的下拉：本前端没有可信的「我能发布到哪些团队」清单
 * （`promotable_scopes` 只说层级，`team_id` 可省略即由服务端选定）。与其猜一份
 * 团队清单让人选错，不如照实说明。
 */

import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { errMessage } from '@/lib/errors'

import { fetchAgentSkill, submitAgentSkill, validateAgentSkill } from '../../skill-api'
import type { AgentSkill, AgentSkillValidation, AgentSkillWritableScope } from '../../skill-types'
import { SkillFindingList } from './SkillReviewPanel'
import { NAME_HINT, NAME_RE } from './SkillForm'
import { SKILL_SCOPE_LABELS } from './skill-status'

/** 可直接提交的两个共享层（`builtin` 随代码发布，不可写入） */
const WRITABLE_TARGETS: AgentSkillWritableScope[] = ['law_firm', 'team']

/**
 * 能提升到哪一层：只认服务端 `promotable_scopes`，且只有个人条目能提。
 * 服务端没下发/下发空 → 空数组（调用方据此不给入口，绝不默认允许）。
 */
function promotableTargets(skill: AgentSkill): AgentSkillWritableScope[] {
  if (skill.scope !== 'lawyer') return []
  return (skill.promotable_scopes ?? []).filter((scope) => WRITABLE_TARGETS.includes(scope))
}

/**
 * 从服务端拼好的字段级消息里摘出某个字段的那一条。
 *
 * `services/skills/errors.py::as_message` 的口径是 `field: message；field: message`，
 * 所以按「；」切开再找前缀：撞名（409）与正文问题（422）会一起回来，不摘的话名字的
 * 错误会跑到「提交失败」那一行上，作者还是不知道该改哪个框。
 */
function serverFieldMessage(message: string, field: string): string {
  const hit = message
    .split('；')
    .map((part) => part.trim())
    .find((part) => part.startsWith(`${field}:`) || part.startsWith(`${field}：`))
  return hit ? hit.slice(field.length + 1).trim() : ''
}

export function SkillPromoteDialog({
  skill,
  onOpenChange,
  onPromoted,
}: {
  /** `null` = 没有打开（弹窗只认这一个目标，避免「上次选的还在」的错位状态） */
  skill: AgentSkill | null
  onOpenChange: (open: boolean) => void
  /** 提审成功：抽屉据此切到目标层 tab 并失效清单缓存 */
  onPromoted: (scope: AgentSkillWritableScope) => void
}) {
  return (
    <Dialog open={skill !== null} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[min(560px,calc(100vw-2rem))]">
        <DialogHeader>
          <DialogTitle>{skill?.scope === 'lawyer' ? '提审到共享层' : '提交审批'}</DialogTitle>
          <DialogDescription>
            提审只把工作区送去审批，线上旧版继续生效；审批通过后才会换版。
          </DialogDescription>
        </DialogHeader>
        {skill ? (
          // key 换条目就重挂一次：slug / 目标层 / 备注全部回到新条目的初值，不用 effect 重置
          <PromoteForm skill={skill} onClose={() => onOpenChange(false)} onPromoted={onPromoted} />
        ) : null}
      </DialogContent>
    </Dialog>
  )
}

function PromoteForm({ skill, onClose, onPromoted }: {
  skill: AgentSkill
  onClose: () => void
  onPromoted: (scope: AgentSkillWritableScope) => void
}) {
  const promoting = skill.scope === 'lawyer'
  const targets = promotableTargets(skill)
  /** 共享条目原地提审（服务端不接受改层）；内置条目没有提审入口，走不到这里 */
  const fixedTarget: AgentSkillWritableScope = skill.scope === 'team' ? 'team' : 'law_firm'

  const [slug, setSlug] = useState(skill.name)
  const [target, setTarget] = useState<AgentSkillWritableScope>(promoting ? (targets[0] ?? 'law_firm') : fixedTarget)
  const [note, setNote] = useState('')
  const [nameError, setNameError] = useState('')
  const [serverError, setServerError] = useState('')
  const [softAck, setSoftAck] = useState(false)
  const [firmAck, setFirmAck] = useState(false)
  /** 打开时先校验一次（拿 safety），之后每次提交前再校验一次覆盖它 */
  const [check, setCheck] = useState<AgentSkillValidation | null>(null)

  /** 工作区正文：`/skills/validate` 必须带正文才跑安全闸门，而清单里不带正文 */
  const workspaceQuery = useQuery({
    queryKey: ['agent-skill-promote', skill.key],
    queryFn: async () => {
      const detail = await fetchAgentSkill(skill.key)
      const result = await validateAgentSkill({
        name: detail.name,
        title: detail.title,
        description: detail.description,
        body: detail.body,
      })
      return { detail, check: result }
    },
    staleTime: 30_000,
  })

  const validateMutation = useMutation({ mutationFn: validateAgentSkill })
  const submitMutation = useMutation({
    mutationFn: (input: { name?: string; target: AgentSkillWritableScope; note: string; firmAck: boolean }) =>
      submitAgentSkill(skill.key, {
        target_scope: input.target,
        ...(input.note ? { note: input.note } : {}),
        // 改名只在「个人 → 共享」这条路径上生效（服务端语义）
        ...(input.name ? { name: input.name } : {}),
        ...(input.firmAck ? { acknowledged_firm_wide: true } : {}),
      }),
  })

  const detail = workspaceQuery.data?.detail
  const current = check ?? workspaceQuery.data?.check
  const findings = current?.safety ?? []
  const hardFindings = findings.filter((finding) => finding.level === 'hard')
  const softFindings = findings.filter((finding) => finding.level === 'soft')
  /** 非空即不能提交，文案就是原因（不给禁用却不解释的按钮） */
  const blocker =
    hardFindings.length > 0
      ? '正文命中硬性敏感信息，服务端会拒绝提审；请先回编辑器改掉'
      : softFindings.length > 0 && !softAck
        ? '请先逐条核对上面的软告警，确认无误后勾选'
        : promoting && target === 'law_firm' && !firmAck
          ? '发布到所内会影响全所律师的 AI，请先勾选确认'
          : ''

  const busy = submitMutation.isPending || validateMutation.isPending

  /** 服务端校验一次：字段级错误就地落位（撞名、保留字、正文超限都走这里） */
  const recheck = async (): Promise<AgentSkillValidation | null> => {
    if (!detail) return null
    const result = await validateMutation.mutateAsync({
      name: slug.trim(),
      title: detail.title,
      description: detail.description,
      body: detail.body,
    })
    setCheck(result)
    const nameProblem = result.errors.find((item) => item.field === 'name')
    setNameError(nameProblem ? nameProblem.message : '')
    return result
  }

  const handleSlugBlur = () => {
    if (!promoting || !slug.trim() || slug === skill.name) return
    if (!NAME_RE.test(slug.trim())) {
      setNameError(NAME_HINT)
      return
    }
    // 焦点离开就查一次撞名：等到点提交再说太晚，作者已经写完备注了
    void recheck().catch((error: unknown) => {
      setNameError(errMessage(error, '技能名查重失败，请稍后重试'))
    })
  }

  const submit = async () => {
    setServerError('')
    if (promoting && !NAME_RE.test(slug.trim())) {
      setNameError(NAME_HINT)
      return
    }
    if (blocker) return
    try {
      const result = await recheck()
      if (!result) return
      if (result.errors.some((item) => item.field === 'name')) return
      const freshHard = (result.safety ?? []).some((finding) => finding.level === 'hard')
      if (freshHard) {
        setServerError('正文命中硬性敏感信息，服务端会拒绝提审；请先回编辑器改掉')
        return
      }
      await submitMutation.mutateAsync({
        name: promoting && slug.trim() !== detail?.name ? slug.trim() : undefined,
        target,
        note: note.trim(),
        firmAck: promoting && target === 'law_firm' && firmAck,
      })
      toast.success('已提审，等审批人处理', { description: '线上仍是上一版；通过后下一轮对话按新版执行' })
      onPromoted(target)
      onClose()
    } catch (error) {
      const message = errMessage(error, '提交失败，请稍后重试')
      const nameOnly = serverFieldMessage(message, 'name')
      if (nameOnly) {
        setNameError(nameOnly)
        return
      }
      setServerError(message)
    }
  }

  return (
    <>
      <div className="mb-3">
        <span className="mb-1 block text-[11.5px] font-[650] text-foreground">显示名</span>
        <p className="rounded-[7px] border border-border bg-secondary/50 px-2 py-1.5 text-[12.5px] text-foreground">
          {detail?.title ?? skill.title}
        </p>
        <p className="mt-1 text-[10.5px] leading-relaxed text-muted-foreground">发布不改标题；要改先去编辑器改工作区。</p>
      </div>

      <div className="mb-3">
        <label htmlFor="skill-promote-name" className="mb-1 block text-[11.5px] font-[650] text-foreground">
          技能名（/skill: 后面的命令名）
        </label>
        <Input
          id="skill-promote-name"
          value={slug}
          readOnly={!promoting}
          onChange={(event) => {
            setSlug(event.target.value)
            if (nameError) setNameError('')
          }}
          onBlur={handleSlugBlur}
          className="h-8 font-mono text-[12px]"
          aria-invalid={Boolean(nameError)}
        />
        {nameError ? (
          <p role="alert" className="mt-1 text-[10.5px] leading-relaxed text-destructive">
            {nameError}
          </p>
        ) : (
          <p className="mt-1 text-[10.5px] leading-relaxed text-muted-foreground">
            {promoting ? NAME_HINT : '共享层的条目提审时不能改名（命令名是别人正在用的引用）'}
          </p>
        )}
      </div>

      <div className="mb-3">
        <label htmlFor="skill-promote-target" className="mb-1 block text-[11.5px] font-[650] text-foreground">
          发布到哪一层
        </label>
        {promoting && targets.length > 1 ? (
          <select
            id="skill-promote-target"
            value={target}
            onChange={(event) => setTarget(event.target.value as AgentSkillWritableScope)}
            className="h-8 rounded-[7px] border border-border bg-card px-2 text-[11.5px]"
          >
            {targets.map((scope) => (
              <option key={scope} value={scope}>
                {SKILL_SCOPE_LABELS[scope]}（{scope}）
              </option>
            ))}
          </select>
        ) : (
          <p className="rounded-[7px] border border-border bg-secondary/50 px-2 py-1.5 text-[12px] text-foreground">
            {SKILL_SCOPE_LABELS[promoting ? target : fixedTarget]}（{promoting ? target : fixedTarget}）
          </p>
        )}
        <p className="mt-1 text-[10.5px] leading-relaxed text-muted-foreground">
          {promoting
            ? target === 'team'
              ? '团队层由服务端按你所属的律师团队选定'
              : '所内层对所有律师生效，需要本所管理员审批'
            : '共享层原地提审：这一层不会变，改动通过审批后才换版'}
        </p>
      </div>

      <div className="mb-3">
        <label htmlFor="skill-promote-note" className="mb-1 block text-[11.5px] font-[650] text-foreground">
          备注（给审批人看）
        </label>
        <Textarea
          id="skill-promote-note"
          value={note}
          onChange={(event) => setNote(event.target.value)}
          placeholder="例如：按新送达规则补了第 3 段，其余未动"
          className="min-h-[56px] text-[12px]"
        />
      </div>

      {findings.length > 0 ? (
        <div className="mb-3">
          <SkillFindingList findings={findings} />
        </div>
      ) : null}

      <SoftAckRow count={softFindings.length} checked={softAck} onChange={setSoftAck} />
      {promoting && target === 'law_firm' ? (
        <label className="mb-2 flex items-start gap-2 text-[11px] leading-relaxed text-foreground">
          <input type="checkbox" className="mt-[3px]" checked={firmAck} onChange={(event) => setFirmAck(event.target.checked)} />
          我已确认这条指令在全所范围内成立
        </label>
      ) : null}

      {blocker ? <p className="mb-2 text-[11px] leading-relaxed text-status-yellow">{blocker}</p> : null}
      {serverError ? (
        <p role="alert" className="mb-2 text-[11px] leading-relaxed text-destructive">
          {serverError}
        </p>
      ) : null}

      <DialogFooter>
        <Button variant="ghost" onClick={onClose}>
          取消
        </Button>
        {/* 正文没到手就没法跑安全闸门，这时提交等于盲提 */}
        <Button disabled={busy || workspaceQuery.isLoading || Boolean(blocker)} onClick={() => void submit()}>
          {busy ? '提交中…' : '提审'}
        </Button>
      </DialogFooter>
    </>
  )
}

/** 软告警的确认行：只在真有 soft 命中时出现（没有命中就不该多一次点击） */
function SoftAckRow({ count, checked, onChange }: { count: number; checked: boolean; onChange: (checked: boolean) => void }) {
  if (count === 0) return null
  return (
    <label className="mb-2 flex items-start gap-2 text-[11px] leading-relaxed text-foreground">
      <input type="checkbox" className="mt-[3px]" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      我已逐条核对上面的 {count} 条软告警，确认是必要引用
    </label>
  )
}
