import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'

import { FEE_MODE_OPTIONS } from '../../contract-enums'
import type { FormErrors, ProjectEditForm } from './project-edit-form'

/**
 * 收费一节。
 *
 * **为什么整节都带一句「需管理员确认」**：后端对这四个字段有三重门——只要出现在
 * payload 里就必须 `confirm_finance=true`（否则 400），而且改的人是 superuser
 * （否则 403），还会写一条财务日志。与其让人填完才发现没权限，不如提前说清楚。
 */
export function FinanceFieldsSection({
  form,
  errors,
  onChange,
}: {
  form: ProjectEditForm
  errors: FormErrors
  onChange: (patch: Partial<ProjectEditForm>) => void
}) {
  return (
    <section className="flex flex-col gap-4 border-b border-border-light pb-5">
      <div className="flex flex-wrap items-baseline gap-2">
        <h2 className="text-[13px] font-[650]">收费</h2>
        <span className="text-[11px] text-muted-foreground/80">
          改动这几个字段会记一条财务日志，且需要管理员权限
        </span>
      </div>

      <div className="grid grid-cols-3 gap-3 max-[680px]:grid-cols-1">
        <label className="flex flex-col gap-1">
          <span className="text-[12px] font-[600] text-secondary-foreground">收费方式</span>
          <select
            className="h-9 w-full min-w-0 rounded-md border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]"
            value={form.feeMode}
            onChange={(e) => onChange({ feeMode: e.target.value })}
          >
            {FEE_MODE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-[12px] font-[600] text-secondary-foreground">
            {form.feeMode === 'FULL_RISK' ? '前期律师费（可空）' : '固定 / 前期律师费'}
          </span>
          <Input
            inputMode="decimal"
            value={form.fixedAmount}
            placeholder="例：50000"
            onChange={(e) => onChange({ fixedAmount: e.target.value })}
          />
          {errors.fixedAmount && <span className="text-[11px] text-status-red">{errors.fixedAmount}</span>}
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-[12px] font-[600] text-secondary-foreground">风险比例（%）</span>
          <Input
            inputMode="decimal"
            value={form.riskRate}
            placeholder="例：15"
            onChange={(e) => onChange({ riskRate: e.target.value })}
          />
          {errors.riskRate && <span className="text-[11px] text-status-red">{errors.riskRate}</span>}
        </label>
      </div>

      {errors.fee && <span className="text-[11.5px] text-status-red">{errors.fee}</span>}

      <label className="flex flex-col gap-1">
        <span className="text-[12px] font-[600] text-secondary-foreground">
          自定义收费条款{form.feeMode === 'CUSTOM' ? '（必填）' : '（可选）'}
        </span>
        <Textarea
          value={form.customTerms}
          placeholder="例：前期 2 万 + 判决金额的 8%，含执行阶段"
          onChange={(e) => onChange({ customTerms: e.target.value })}
        />
      </label>
    </section>
  )
}
