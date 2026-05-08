import type { CalculationPeriod, PrincipalChange } from '../api'

export const RATE_MODE_OPTIONS = [
  { value: 'lpr', label: 'LPR 利率' },
  { value: 'custom', label: '自定义利率' },
  { value: 'delay', label: '迟延履行利率' },
] as const

export const RATE_TYPE_OPTIONS = [
  { value: '1y', label: '一年期 LPR' },
  { value: '5y', label: '五年期以上 LPR' },
] as const

export const YEAR_DAYS_OPTIONS = [
  { value: 360, label: '360天/年' },
  { value: 365, label: '365天/年' },
  { value: 0, label: '实际天数' },
] as const

export const DATE_INCLUSION_OPTIONS = [
  { value: 'both', label: '起止日期均计算在内' },
  { value: 'start_only', label: '只计起始日' },
  { value: 'end_only', label: '只计截止日' },
  { value: 'neither', label: '起止均不计' },
] as const

export const CUSTOM_RATE_UNIT_OPTIONS = [
  { value: 'percent', label: '%（年）' },
  { value: 'permille', label: '‰（天）' },
  { value: 'permyriad', label: '‱（天）' },
] as const

export interface HistoryItem {
  id: number
  timestamp: string
  useChanges: boolean
  form: {
    start_date: string
    end_date: string
    principal: string
    rate_mode: string
    rate_type: string
    multiplier: string
    custom_rate_unit: string
    custom_rate_value: string
    year_days: number
    date_inclusion: string
    changes: PrincipalChange[]
  }
  result: {
    total_interest: string
    total_days: number
    total_principal: string
  }
  rateInfo: string
}

export interface PrincipalGroup {
  principal: number
  periods: CalculationPeriod[]
  totalDays: number
  totalInterest: number
}

export function formatMoney(value: string | null | undefined): string {
  if (!value) return '0.00'
  const num = parseFloat(value)
  if (isNaN(num)) return value
  return num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export function formatDate(d: string): string {
  if (!d) return ''
  return d.split('T')[0]
}

export function getRateInfo(form: HistoryItem['form']): string {
  if (form.rate_mode === 'lpr') {
    const type = form.rate_type === '1y' ? '一年期' : '五年期'
    return `LPR ${type} · ${form.multiplier}倍`
  }
  if (form.rate_mode === 'delay') {
    return '迟延履行 · 1.75‱/天'
  }
  const unitMap: Record<string, string> = { percent: '%/年', permille: '‰/天', permyriad: '‱/天' }
  return `自定义 · ${form.custom_rate_value}${unitMap[form.custom_rate_unit] || ''}`
}

export function groupByPrincipal(periods: CalculationPeriod[]): PrincipalGroup[] {
  const groups: PrincipalGroup[] = []
  let current: PrincipalGroup | null = null
  let lastEnd: string | null = null

  for (const p of periods) {
    const principal = parseFloat(p.principal)
    const start = new Date(p.start_date)
    const lastEndObj = lastEnd ? new Date(lastEnd) : null

    const isNew = !current
      || (lastEndObj && start <= lastEndObj)
      || current.principal !== principal

    if (isNew) {
      if (current) groups.push(current)
      current = { principal, periods: [p], totalDays: p.days, totalInterest: parseFloat(p.interest) }
    } else if (current) {
      current.periods.push(p)
      current.totalDays += p.days
      current.totalInterest += parseFloat(p.interest)
    }
    lastEnd = p.end_date
  }
  if (current) groups.push(current)
  return groups
}

export function formatRateDisplay(rate: string, rateUnit: string | null, rateMode: string): string {
  const r = parseFloat(rate) || 0
  if (rateMode === 'lpr') return `${r.toFixed(2)}%/年`
  if (rateUnit === 'permille') return `${r.toFixed(2)}‰/天`
  if (rateUnit === 'permyriad') return `${r.toFixed(2)}‱/天`
  return `${r.toFixed(2)}%/年`
}
