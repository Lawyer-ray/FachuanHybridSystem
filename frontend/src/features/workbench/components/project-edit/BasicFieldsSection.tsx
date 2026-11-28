import { Input } from '@/components/ui/input'

import { CASE_TYPE_OPTIONS, CONTRACT_STATUS_OPTIONS, stageOptionsFor } from '../../contract-enums'
import type { FormErrors, ProjectEditForm } from './project-edit-form'

/** 字段壳：一行标签 + 控件 + 错误/说明（仓库没有 label/field 组件，照 PaymentDialog 的写法） */
function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string
  hint?: string
  error?: string
  children: React.ReactNode
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[12px] font-[600] text-secondary-foreground">{label}</span>
      {children}
      {error ? (
        <span className="text-[11px] text-status-red">{error}</span>
      ) : hint ? (
        <span className="text-[11px] text-muted-foreground/80">{hint}</span>
      ) : null}
    </label>
  )
}

const selectCls =
  'h-9 w-full min-w-0 rounded-md border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]'

/**
 * 基本信息 + 代理阶段。
 *
 * 阶段只在「这类案子后端真的接受阶段」时出现：涉外/专项/常法在后端的可用集合是
 * 空的，传任何非空数组都会被判「无效的代理阶段」——不如干脆不给这个控件。
 */
export function BasicFieldsSection({
  form,
  errors,
  onChange,
}: {
  form: ProjectEditForm
  errors: FormErrors
  onChange: (patch: Partial<ProjectEditForm>) => void
}) {
  const stageOptions = stageOptionsFor(form.caseType)
  const toggleStage = (code: string) => {
    onChange({
      stages: form.stages.includes(code) ? form.stages.filter((s) => s !== code) : [...form.stages, code],
    })
  }

  return (
    <section className="flex flex-col gap-4 border-b border-border-light pb-5">
      <h2 className="text-[13px] font-[650]">基本信息</h2>

      <Field label="项目名称" error={errors.name} hint="最多 100 字">
        <Input
          value={form.name}
          maxLength={100}
          onChange={(e) => onChange({ name: e.target.value })}
          placeholder="例：某某银行诉某某金融借款合同纠纷"
        />
      </Field>

      <div className="grid grid-cols-2 gap-3 max-[680px]:grid-cols-1">
        <Field label="案件类型" error={errors.caseType} hint="改成非诉类后，已选的代理阶段会被清空">
          <select
            className={selectCls}
            value={form.caseType}
            onChange={(e) => {
              // 换了案型，原来的阶段可能不再合法：先剔除不合法的，别让保存时才被后端打回
              const allowed = new Set(stageOptionsFor(e.target.value).map((s) => s.code))
              onChange({
                caseType: e.target.value,
                stages: form.stages.filter((s) => allowed.has(s)),
              })
            }}
          >
            {CASE_TYPE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </Field>

        <Field
          label="项目状态"
          error={errors.status}
          hint={form.status === 'archived' ? '归档会把本项目下所有在办案件一起结案（不可逆）' : undefined}
        >
          <select
            className={selectCls}
            value={form.status}
            onChange={(e) => onChange({ status: e.target.value })}
          >
            {CONTRACT_STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </Field>
      </div>

      <div className="grid grid-cols-3 gap-3 max-[680px]:grid-cols-1">
        <Field label="指定日期" error={errors.specified}>
          <Input
            type="date"
            value={form.specified}
            onChange={(e) => onChange({ specified: e.target.value })}
          />
        </Field>
        <Field label="服务期开始" error={errors.from} hint="可留空">
          <Input type="date" value={form.from} onChange={(e) => onChange({ from: e.target.value })} />
        </Field>
        <Field label="服务期结束" error={errors.to} hint="可留空">
          <Input type="date" value={form.to} onChange={(e) => onChange({ to: e.target.value })} />
        </Field>
      </div>

      <label className="flex items-center gap-2 text-[12.5px] text-secondary-foreground">
        <input
          type="checkbox"
          className="size-4 accent-foreground"
          checked={form.isFiled}
          onChange={(e) => onChange({ isFiled: e.target.checked })}
        />
        已建档
        <span className="text-[11px] text-muted-foreground/80">（建档编号由后端生成，不在这里填）</span>
      </label>

      {stageOptions.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <span className="text-[12px] font-[600] text-secondary-foreground">代理阶段</span>
          <div className="flex flex-wrap gap-x-4 gap-y-1.5">
            {stageOptions.map((s) => (
              <label
                key={s.code}
                className="flex items-center gap-1.5 text-[12.5px] text-secondary-foreground"
              >
                <input
                  type="checkbox"
                  className="size-4 accent-foreground"
                  checked={form.stages.includes(s.code)}
                  onChange={() => toggleStage(s.code)}
                />
                {s.label}
              </label>
            ))}
          </div>
          {errors.stages ? (
            <span className="text-[11px] text-status-red">{errors.stages}</span>
          ) : (
            <span className="text-[11px] text-muted-foreground/80">
              这里勾的只是「合同约定了哪些程序」；具体案件在详情页左栏推进。
            </span>
          )}
        </div>
      )}
    </section>
  )
}
