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
 * 分工：本文件是外壳（初始值 / 校验 / 保存 / 放弃确认），字段区在 `SkillForm`，
 * 编辑态的取数三态在 `SkillDetailLoader`。两态共用一套保存与放弃逻辑，差异只在
 * 「初始值从哪来」与「保存打哪个接口」。
 *
 * 新建时技能名自动生成 `skill-xxxx`（可手改，即时校验 slug 规则）；编辑态
 * 名字只读——后端 PUT 的请求体里没有 `name`（它是技能目录名，建后不可改）。
 *
 * 新建还要带**建到哪一层**（`scope`）：在「所内」tab 点新建写的是所内草稿，保存后
 * 仍需管理员审批才生效。保存成功把落点回传给抽屉（`onSaved`），由它切到对应 tab——
 * 不切的话新技能在当前 tab 里根本看不见，会被当成「保存失败」。
 */

import { useEffect, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { toast } from 'sonner'

import { validateAgentSkill } from '../../skill-api'
import type { AgentSkill, AgentSkillScope } from '../../types'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { Button } from '@/components/ui/button'
import { errMessage } from '@/lib/errors'
import { SkillDetailLoader } from './SkillDetailLoader'
import { NAME_HINT, NAME_RE, SkillForm, type SkillFormValues } from './SkillForm'
import { SkillPreview } from './SkillPreview'
import type { SkillCreateScope } from './skill-tabs'
import { useSkillMutations } from './use-skill-mutations'

/** 首次保存前的一次性告知（只写一次，之后不再打扰） */
const NOTICE_KEY = 'fachuan:skill-notice:v1'

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

/** 编辑器的打开目标：新建（要说明建到哪一层），或编辑某个已有技能 */
export type SkillEditorTarget = { mode: 'create'; scope: SkillCreateScope } | { mode: 'edit'; skill: AgentSkill }

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
  /** 仅在**保存成功**后触发（取消/放弃不触发）：抽屉据此切到条目所在的 tab */
  onSaved?: (scope: AgentSkillScope) => void
}) {
  // 新建态的初始名只算一次（惰性初始化）。若在 render 期间调 `generateSkillName()`，
  // 每次重渲染都会换一份新名字，`name !== initial.name` 就恒成立 → `dirty` 被永久
  // 锁死为 true，连空表单关闭也会弹「放弃未保存的修改」。编辑态也会算一次（一次
  // Math.random 的代价），为的是不把 hook 放进条件分支。
  const [createInitial] = useState<SkillFormValues>(() => ({ name: generateSkillName(), title: '', description: '', body: '' }))

  if (target.mode === 'create') {
    return (
      <SkillDraft
        mode="create"
        scope={target.scope}
        initial={createInitial}
        onClose={onClose}
        onDirtyChange={onDirtyChange}
        onSaved={onSaved}
      />
    )
  }
  return (
    <SkillDetailLoader skill={target.skill}>
      {(detail) => (
        <SkillDraft
          key={detail.key}
          mode="edit"
          skillKey={detail.key}
          version={detail.version}
          initial={{ name: detail.name, title: detail.title, description: detail.description, body: detail.body }}
          onClose={onClose}
          onDirtyChange={onDirtyChange}
          onSaved={onSaved}
        />
      )}
    </SkillDetailLoader>
  )
}

/** 编辑器的实现本体：草稿状态 + 校验 + 保存 + 两个确认框（新建/编辑共用） */
function SkillDraft({
  mode,
  scope = 'lawyer',
  initial,
  skillKey,
  version = 0,
  onClose,
  onDirtyChange,
  onSaved,
}: {
  mode: 'create' | 'edit'
  /** 新建时建到哪一层（编辑态由既有条目决定，不看这个） */
  scope?: SkillCreateScope
  initial: SkillFormValues
  /** 编辑时的技能 key（新建时无） */
  skillKey?: string
  /** 编辑时的乐观锁版本（不符后端 409） */
  version?: number
  onClose: () => void
  onDirtyChange: (dirty: boolean) => void
  onSaved?: (scope: AgentSkillScope) => void
}) {
  const [values, setValues] = useState(initial)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [preview, setPreview] = useState('')
  const [noticeOpen, setNoticeOpen] = useState(false)
  const [leaveOpen, setLeaveOpen] = useState(false)

  const { createMutation, updateMutation } = useSkillMutations()
  const validateMutation = useMutation({ mutationFn: validateAgentSkill })

  const dirty =
    values.title !== initial.title ||
    values.description !== initial.description ||
    values.body !== initial.body ||
    (mode === 'create' && values.name !== initial.name)
  const saving = createMutation.isPending || updateMutation.isPending || validateMutation.isPending

  // 每次改动把 dirty 上报给抽屉（Esc/遮罩关闭会绕过本组件的取消按钮）
  useEffect(() => onDirtyChange(dirty), [dirty, onDirtyChange])

  /** 字段改动：写值并清掉该字段上一次的错误（错误随改字失效） */
  const change = (field: keyof SkillFormValues, value: string) => {
    setValues((prev) => ({ ...prev, [field]: value }))
    setErrors((prev) => (prev[field] ? { ...prev, [field]: '' } : prev))
  }

  /** 本地必填先挡（一次网络往返才说「标题不能为空」太慢）；slug 即时校验 */
  const localErrors = (): Record<string, string> => {
    const found: Record<string, string> = {}
    if (!values.title.trim()) found.title = '填一个显示名，列表里靠它辨认'
    if (!values.description.trim()) found.description = '写一句它管什么——列表与 / 菜单里靠这句辨认'
    if (!values.body.trim()) found.body = '正文不能为空'
    if (mode === 'create' && (!values.name.trim() || !NAME_RE.test(values.name))) found.name = NAME_HINT
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
        ...(mode === 'create' ? { name: values.name } : {}),
        title: values.title.trim(),
        description: values.description.trim(),
        body: values.body,
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
        const created = await createMutation.mutateAsync({
          name: values.name,
          title: values.title.trim(),
          description: values.description.trim(),
          body: values.body,
          // 省略 scope 就是个人技能；所内要服务端 `can_create_firm` 才给得到这个入口
          ...(scope === 'law_firm' ? { scope } : {}),
        })
        onSaved?.(created.scope)
      } else {
        const updated = await updateMutation.mutateAsync({
          key: skillKey ?? '',
          input: { title: values.title.trim(), description: values.description.trim(), body: values.body, version },
        })
        onSaved?.(updated.scope)
      }
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

      {mode === 'create' ? (
        <p className="mb-2 text-[10.5px] leading-relaxed text-muted-foreground">
          {scope === 'law_firm'
            ? '建在所内：保存后先是草稿，要本所管理员审批通过才会对全所生效。'
            : '建在我的技能：只对你自己生效，随时可以改。'}
        </p>
      ) : null}

      <SkillForm mode={mode} values={values} errors={errors} onChange={change} />

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
