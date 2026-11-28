/**
 * 抽屉内的技能编辑器（二级视图）：新建与编辑共用。
 *
 * 三条硬约束：
 * 1. **保存前先调 `/skills/validate`**：正文最终由后端渲染成 SKILL.md，只有
 *    服务端能说「这份草稿 AI 会读成什么」。错误带 `field` 回传，直接标到对应
 *    输入框下方，而不是弹一句笼统的「保存失败」。
 * 2. **失败保留草稿**：校验不过、版本冲突（409）、网络失败都只提示、不关视图
 *    ——写了几百字正文被关掉等于让人重写。
 * 3. **未保存离开要二次确认**：关编辑视图与关抽屉都算。`dirty` 上报给
 *    `SkillDrawer`，因为 Sheet 的 Esc / 点遮罩关闭不经过本组件。
 *
 * 新建时技能名自动生成 `skill-xxxx`（可手改，即时校验 slug 规则）；编辑态
 * 名字只读——后端 PUT 的请求体里没有 `name`（它是技能目录名，建后不可改）。
 */

import { useEffect, useState, type ChangeEvent, type ReactNode } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { toast } from 'sonner'

import { fetchAgentSkill, validateAgentSkill } from '../../skill-api'
import type { AgentSkill } from '../../types'
import { ErrorBlock, LoadingBlock } from '@/components/shared/AsyncState'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { errMessage } from '@/lib/errors'
import { SkillPreview } from './SkillPreview'
import { SKILLS_QUERY_KEY, useSkillMutations } from './use-skill-mutations'

/** 首次保存前的一次性告知（只写一次，之后不再打扰） */
const NOTICE_KEY = 'fachuan:skill-notice:v1'
/** slug 规则与后端 `NAME_RE` 同口径：小写字母/数字/连字符，字母或数字打头 */
const NAME_RE = /^[a-z0-9][a-z0-9-]{0,63}$/
const NAME_HINT = '只能用小写字母、数字和连字符，以字母或数字开头（它就是 /skill: 后面的命令名）'

/** 字段 → 控件 id（聚焦首个错误用；顺序与表单一致） */
const FIELD_IDS: Record<string, string> = {
  title: 'skill-title',
  name: 'skill-name',
  description: 'skill-description',
  body: 'skill-body',
}

/** 把焦点送到第一个出错的字段：错误文案在长表单底部，不滚过去等于没报错 */
function focusFirstError(found: Record<string, string>): void {
  const field = Object.keys(FIELD_IDS).find((key) => found[key])
  const id = field ? FIELD_IDS[field] : undefined
  if (!id) return
  requestAnimationFrame(() => document.getElementById(id)?.focus())
}

/** 编辑器的打开目标：新建，或编辑某个已有技能 */
export type SkillEditorTarget = { mode: 'create' } | { mode: 'edit'; skill: AgentSkill }

/** 表单初值（新建为空壳；名字预生成一份给用户看得见、可改） */
interface SkillFormValues {
  name: string
  title: string
  description: string
  body: string
  version: number
}

function generateSkillName(): string {
  return `skill-${Math.random().toString(36).slice(2, 6).padEnd(4, '0')}`
}

function noticeSeen(): boolean {
  try {
    return localStorage.getItem(NOTICE_KEY) === '1'
  } catch {
    // 隐私模式读不到 localStorage：按「已看过」处理，别因存储不可用反复拦截保存
    return true
  }
}

function markNoticeSeen(): void {
  try {
    localStorage.setItem(NOTICE_KEY, '1')
  } catch {
    // 写不进去就下次再提示一次；不阻断保存
  }
}

/** 字段壳：标签 + 控件 + 提示/错误二选一（错误优先） */
function Field({ id, label, hint, error, children }: { id: string; label: string; hint?: string; error?: string; children: ReactNode }) {
  return (
    <div className="mb-3">
      <label htmlFor={id} className="mb-1 block text-[11.5px] font-[650] text-foreground">
        {label}
      </label>
      {children}
      {error ? (
        <p role="alert" className="mt-1 text-[10.5px] leading-relaxed text-destructive">
          {error}
        </p>
      ) : hint ? (
        <p className="mt-1 text-[10.5px] leading-relaxed text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  )
}

export function SkillEditor({
  target,
  onClose,
  onDirtyChange,
  onSaved,
}: {
  target: SkillEditorTarget
  /** 保存成功 / 放弃修改后回到列表 */
  onClose: () => void
  /** 未保存改动的上报口（抽屉关闭时据此二次确认） */
  onDirtyChange: (dirty: boolean) => void
  /** 仅在**保存成功**后触发（取消/放弃不触发）：抽屉据此切到「我的」 */
  onSaved?: () => void
}) {
  if (target.mode === 'create') {
    return (
      <SkillForm
        mode="create"
        initial={{ name: generateSkillName(), title: '', description: '', body: '', version: 0 }}
        onClose={onClose}
        onDirtyChange={onDirtyChange}
        onSaved={onSaved}
      />
    )
  }
  return <SkillDetailLoader skill={target.skill} onClose={onClose} onDirtyChange={onDirtyChange} onSaved={onSaved} />
}

/** 编辑态先拉正文：列表项没有 `body`，也要拿最新 `version` 做乐观锁 */
function SkillDetailLoader({
  skill,
  onClose,
  onDirtyChange,
  onSaved,
}: {
  skill: AgentSkill
  onClose: () => void
  onDirtyChange: (dirty: boolean) => void
  onSaved?: () => void
}) {
  const detailQuery = useQuery({
    queryKey: [...SKILLS_QUERY_KEY, skill.key],
    queryFn: () => fetchAgentSkill(skill.key),
    staleTime: 0,
  })

  if (detailQuery.isLoading) return <LoadingBlock size="sm" text="正在打开技能…" />
  if (!detailQuery.data) {
    return <ErrorBlock error={detailQuery.error} fallback="技能正文加载失败" onRetry={() => void detailQuery.refetch()} />
  }
  const detail = detailQuery.data
  return (
    <SkillForm
      key={detail.key}
      mode="edit"
      skillKey={skill.key}
      initial={{ name: detail.name, title: detail.title, description: detail.description, body: detail.body, version: detail.version }}
      onClose={onClose}
      onDirtyChange={onDirtyChange}
      onSaved={onSaved}
    />
  )
}

function SkillForm({
  mode,
  initial,
  skillKey,
  onClose,
  onDirtyChange,
  onSaved,
}: {
  mode: 'create' | 'edit'
  initial: SkillFormValues
  /** 编辑时的技能 key（新建时无） */
  skillKey?: string
  onClose: () => void
  onDirtyChange: (dirty: boolean) => void
  onSaved?: () => void
}) {
  const [name, setName] = useState(initial.name)
  const [title, setTitle] = useState(initial.title)
  const [description, setDescription] = useState(initial.description)
  const [body, setBody] = useState(initial.body)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [preview, setPreview] = useState('')
  const [noticeOpen, setNoticeOpen] = useState(false)
  const [leaveOpen, setLeaveOpen] = useState(false)

  const { createMutation, updateMutation } = useSkillMutations()
  const validateMutation = useMutation({ mutationFn: validateAgentSkill })

  const dirty =
    title !== initial.title || description !== initial.description || body !== initial.body || (mode === 'create' && name !== initial.name)
  const saving = createMutation.isPending || updateMutation.isPending || validateMutation.isPending

  // 每次改动把 dirty 上报给抽屉（Esc/遮罩关闭会绕过本组件的取消按钮）
  useEffect(() => onDirtyChange(dirty), [dirty, onDirtyChange])

  /** 字段改动：写值并清掉该字段上一次的错误（错误随改字失效） */
  const change =
    (field: string, set: (value: string) => void) => (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      set(event.target.value)
      setErrors((prev) => (prev[field] ? { ...prev, [field]: '' } : prev))
    }

  /** 本地必填先挡（一次网络往返才说「标题不能为空」太慢）；slug 即时校验 */
  const localErrors = (): Record<string, string> => {
    const found: Record<string, string> = {}
    if (!title.trim()) found.title = '填一个显示名，列表里靠它辨认'
    if (!description.trim()) found.description = '写一句它管什么——这句话决定 AI 什么时候用它'
    if (!body.trim()) found.body = '正文不能为空'
    if (mode === 'create' && (!name.trim() || !NAME_RE.test(name))) found.name = NAME_HINT
    return found
  }

  const runValidate = async (): Promise<boolean> => {
    const found = localErrors()
    if (Object.keys(found).length > 0) {
      setErrors(found)
      focusFirstError(found)
      return false
    }
    try {
      const result = await validateMutation.mutateAsync({
        ...(mode === 'create' ? { name } : {}),
        title: title.trim(),
        description: description.trim(),
        body,
      })
      if (!result.ok) {
        // 服务端字段错误直接落位（`field` 就是 name/title/description/body）
        const serverErrors = Object.fromEntries(result.errors.map((item) => [item.field, item.message]))
        setErrors(serverErrors)
        focusFirstError(serverErrors)
        setPreview('')
        return false
      }
      setErrors({})
      setPreview(result.preview)
      return true
    } catch (error) {
      toast.error('校验失败', { description: errMessage(error, '请稍后重试') })
      return false
    }
  }

  const commit = async () => {
    try {
      if (mode === 'create') {
        await createMutation.mutateAsync({ name, title: title.trim(), description: description.trim(), body })
      } else {
        await updateMutation.mutateAsync({
          key: skillKey ?? '',
          input: { title: title.trim(), description: description.trim(), body, version: initial.version },
        })
      }
      // 先通知外壳切 tab（新建可能在「系统」tab 打开，新技能在「我的」里），再关视图
      onSaved?.()
      onClose()
    } catch (error) {
      // 409（别人改过）/ 422（服务端复校验不过）/ 网络失败：草稿留着，只说明原因
      toast.error('保存失败', { description: errMessage(error, '请稍后重试') })
    }
  }

  const handleSave = async () => {
    if (saving) return
    if (!(await runValidate())) return
    if (mode === 'create' && !noticeSeen()) {
      setNoticeOpen(true)
      return
    }
    await commit()
  }

  const handleCancel = () => {
    if (dirty) setLeaveOpen(true)
    else onClose()
  }

  return (
    <div>
      <div className="mb-3 flex items-center gap-2">
        <Button variant="ghost" size="sm" className="h-7 gap-1 px-1.5 text-[11px]" onClick={handleCancel}>
          <ArrowLeft className="h-3 w-3" />
          返回
        </Button>
        <span className="text-[13px] font-semibold text-foreground">{mode === 'create' ? '新建技能' : '编辑技能'}</span>
      </div>

      <Field id="skill-title" label="显示名" error={errors.title}>
        <Input id="skill-title" value={title} onChange={change('title', setTitle)} placeholder="例如：合同审查三段式" className="h-8 text-[12.5px]" aria-invalid={Boolean(errors.title)} />
      </Field>

      <Field
        id="skill-name"
        label="技能名（/skill: 后面的命令名）"
        hint={mode === 'create' ? NAME_HINT : '建好后不能改名（它就是技能目录名）'}
        error={errors.name || (mode === 'create' && name && !NAME_RE.test(name) ? NAME_HINT : '')}
      >
        <Input id="skill-name" value={name} readOnly={mode === 'edit'} onChange={change('name', setName)} className="h-8 font-mono text-[12px]" aria-invalid={Boolean(errors.name)} />
      </Field>

      <Field id="skill-description" label="描述（决定 AI 什么时候用它）" hint="一句话写清适用场景与产出，会进系统提示；不要换行" error={errors.description}>
        <Input
          id="skill-description"
          value={description}
          onChange={change('description', setDescription)}
          placeholder="例如：审阅买卖合同时，按主体、标的、违约、争议解决四段逐项核对"
          className="h-8 text-[12.5px]"
          aria-invalid={Boolean(errors.description)}
        />
      </Field>

      <Field id="skill-body" label="正文（AI 执行的做法）" error={errors.body}>
        <Textarea
          id="skill-body"
          value={body}
          onChange={change('body', setBody)}
          rows={10}
          placeholder={'写做法，不写客户名/案号/金额。例如：\n1. 先列主体与签章页是否齐全\n2. 标的条款核对数量、单价、总价是否自洽\n3. 违约责任看是否对等、有无上限'}
          className="min-h-40 resize-y font-mono text-[12px]"
          aria-invalid={Boolean(errors.body)}
        />
      </Field>

      <SkillPreview preview={preview} />

      <div className="mt-4 flex items-center gap-2">
        <Button variant="outline" size="sm" className="h-7 px-2.5 text-[11px]" disabled={saving} onClick={() => void runValidate()}>
          预览
        </Button>
        <Button variant="ghost" size="sm" className="ml-auto h-7 px-2.5 text-[11px]" disabled={saving} onClick={handleCancel}>
          取消
        </Button>
        <Button size="sm" className="h-7 px-3 text-[11px]" disabled={saving} onClick={() => void handleSave()}>
          {saving ? '保存中…' : '保存'}
        </Button>
      </div>

      <ConfirmDialog
        open={noticeOpen}
        onOpenChange={setNoticeOpen}
        title="写技能前须知"
        description="技能会作为指令交给 AI 执行，不能改变审批等级；只写做法，不要写客户名、案号、金额。"
        confirmText="我知道了，继续保存"
        cancelText="再想想"
        pending={saving}
        onConfirm={() => {
          markNoticeSeen()
          void commit()
        }}
      />

      <ConfirmDialog
        open={leaveOpen}
        onOpenChange={setLeaveOpen}
        title="放弃未保存的修改？"
        description="关掉之后，这次填写的内容不会保留。"
        confirmText="放弃修改"
        cancelText="继续编辑"
        tone="destructive"
        onConfirm={onClose}
      />
    </div>
  )
}
