import { JURISDICTION_OPTIONS } from './doc-review-api'

/**
 * 审查法域选择器。
 *
 * ## 为什么这个下拉必须存在（而不是写死中国法）
 *
 * 后端按法域选标准库：中国法是《民法典》口径，泰国法是 `Civil and Commercial Code` /
 * `Land Code` / `Foreign Business Act` 口径，且非中国法域才会对合同引用的外国法做
 * 域外法查明。写死中国法意味着**一份泰国合同永远查不出「租期超过 30 年无效」**，
 * 却会被报一堆「缺少统一社会信用代码」。
 *
 * 单独成文件还有一个原因：`ReviewPanel.tsx` 已经贴着 450 行的文件规模红线，
 * 往里加 20 行 JSX 会直接踩线（eslint `max-lines`）。
 */
export function JurisdictionSelect({
  value,
  onChange,
  disabled,
}: {
  value: string
  onChange: (next: string) => void
  disabled?: boolean
}) {
  return (
    <>
      <label className="sr-only" htmlFor="doc-review-jurisdiction">
        审查依据的法域
      </label>
      <select
        id="doc-review-jurisdiction"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled}
        title="审查依据的法域：决定用哪国标准库，以及是否对合同引用的外国法做域外法查明"
        className="h-[26px] rounded-[7px] border border-border bg-card px-1 text-[11px] text-foreground disabled:opacity-50"
      >
        {JURISDICTION_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </>
  )
}
