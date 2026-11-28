/**
 * 技能编辑器的字段区（新建与编辑共用）。
 *
 * 只回答「值长什么样、错在哪」：草稿状态、校验顺序、保存与放弃确认都在外壳
 * `SkillEditor`。做成纯展示的字段区，新建态与编辑态才不会各长一套校验与保存。
 *
 * 字段顺序就是律师的思考顺序：显示名（列表里靠它辨认）→ 技能名（`/skill:` 后面的
 * 命令名）→ 描述（一句话适用场景）→ 正文（AI 执行的做法）。描述不承诺「AI 会自己
 * 判断何时用它」——P0 只做 `/skill:` 点名展开，索引注入落地后再放开措辞。
 */

import type { ReactNode } from 'react'

import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'

/** slug 规则与后端 `NAME_RE` 同口径：小写字母/数字/连字符，字母或数字打头 */
export const NAME_RE = /^[a-z0-9][a-z0-9-]{0,63}$/
export const NAME_HINT = '只能用小写字母、数字和连字符，以字母或数字开头（它就是 /skill: 后面的命令名）'

/** 表单四栏的值（`version` 是乐观锁，属于外壳而不是字段） */
export interface SkillFormValues {
  name: string
  title: string
  description: string
  body: string
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

export function SkillForm({
  mode,
  values,
  errors,
  onChange,
}: {
  mode: 'create' | 'edit'
  values: SkillFormValues
  /** 字段 → 错误文案（服务端 `field` 与本地必填同口径：name/title/description/body） */
  errors: Record<string, string>
  onChange: (field: keyof SkillFormValues, value: string) => void
}) {
  return (
    <>
      <Field id="skill-title" label="显示名" error={errors.title}>
        <Input
          id="skill-title"
          value={values.title}
          onChange={(e) => onChange('title', e.target.value)}
          placeholder="例如：合同审查三段式"
          className="h-8 text-[12.5px]"
          aria-invalid={Boolean(errors.title)}
        />
      </Field>

      <Field
        id="skill-name"
        label="技能名（/skill: 后面的命令名）"
        hint={mode === 'create' ? NAME_HINT : '建好后不能改名（它就是技能目录名）'}
        error={errors.name || (mode === 'create' && values.name && !NAME_RE.test(values.name) ? NAME_HINT : '')}
      >
        <Input
          id="skill-name"
          value={values.name}
          readOnly={mode === 'edit'}
          onChange={(e) => onChange('name', e.target.value)}
          className="h-8 font-mono text-[12px]"
          aria-invalid={Boolean(errors.name)}
        />
      </Field>

      <Field
        id="skill-description"
        label="描述（一句话说清它管什么）"
        hint="写适用场景与产出，不要换行；抽屉与 / 菜单里靠它辨认，点名使用时也随技能一起交给 AI"
        error={errors.description}
      >
        <Input
          id="skill-description"
          value={values.description}
          onChange={(e) => onChange('description', e.target.value)}
          placeholder="例如：审阅买卖合同时，按主体、标的、违约、争议解决四段逐项核对"
          className="h-8 text-[12.5px]"
          aria-invalid={Boolean(errors.description)}
        />
      </Field>

      <Field id="skill-body" label="正文（AI 执行的做法）" error={errors.body}>
        <Textarea
          id="skill-body"
          value={values.body}
          onChange={(e) => onChange('body', e.target.value)}
          rows={10}
          placeholder={'写做法，不写客户名/案号/金额。例如：\n1. 先列主体与签章页是否齐全\n2. 标的条款核对数量、单价、总价是否自洽\n3. 违约责任看是否对等、有无上限'}
          className="min-h-40 resize-y font-mono text-[12px]"
          aria-invalid={Boolean(errors.body)}
        />
      </Field>
    </>
  )
}
