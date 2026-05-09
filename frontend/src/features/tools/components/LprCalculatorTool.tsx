import { useState, useCallback } from 'react'
import { copyToClipboard } from '@/lib/clipboard'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Plus, Trash2, Copy, RotateCcw, Clock, X } from 'lucide-react'
import { useLprRates } from '../hooks/use-lpr-rates'
import { useLprCalculate } from '../hooks/use-lpr-calculate'
import type { LprCalculateRequest, LprCalculateResponse, PrincipalChange } from '../api'
import {
  RATE_MODE_OPTIONS, RATE_TYPE_OPTIONS, YEAR_DAYS_OPTIONS,
  DATE_INCLUSION_OPTIONS, CUSTOM_RATE_UNIT_OPTIONS,
  formatMoney, formatDate, getRateInfo, groupByPrincipal, formatRateDisplay,
  type HistoryItem,
} from '../utils/lpr'

export function LprCalculatorTool() {
  const [principalMode, setPrincipalMode] = useState<'fixed' | 'variable'>('fixed')
  const [principal, setPrincipal] = useState('100000')
  const [startDate, setStartDate] = useState(() => {
    const d = new Date()
    d.setFullYear(d.getFullYear() - 1)
    return d.toISOString().split('T')[0]
  })
  const [endDate, setEndDate] = useState(() => new Date().toISOString().split('T')[0])
  const [principalChanges, setPrincipalChanges] = useState<PrincipalChange[]>([
    { start_date: '', end_date: '', principal: '' },
  ])
  const [rateMode, setRateMode] = useState<'lpr' | 'custom' | 'delay'>('lpr')
  const [rateType, setRateType] = useState<'1y' | '5y'>('1y')
  const [multiplier, setMultiplier] = useState('1')
  const [customRateUnit, setCustomRateUnit] = useState<'percent' | 'permille' | 'permyriad'>('percent')
  const [customRateValue, setCustomRateValue] = useState('')
  const [yearDays, setYearDays] = useState(360)
  const [dateInclusion, setDateInclusion] = useState<'both' | 'start_only' | 'end_only' | 'neither'>('both')

  const [result, setResult] = useState<LprCalculateResponse | null>(null)
  const [showDetail, setShowDetail] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [history, setHistory] = useState<HistoryItem[]>(() => {
    const saved = localStorage.getItem('lpr_calculator_history')
    return saved ? JSON.parse(saved) : []
  })
  const [syncMessage, setSyncMessage] = useState('')

  const { data: lprData } = useLprRates()
  const rates = lprData?.items ?? []
  const latestRate = rates[0] ?? null
  const calcMutation = useLprCalculate()

  const saveToHistory = useCallback((data: LprCalculateResponse) => {
    if (!data.success) return
    const item: HistoryItem = {
      id: Date.now(),
      timestamp: new Date().toISOString(),
      useChanges: principalMode === 'variable',
      form: {
        start_date: startDate,
        end_date: endDate,
        principal,
        rate_mode: rateMode,
        rate_type: rateType,
        multiplier,
        custom_rate_unit: customRateUnit,
        custom_rate_value: customRateValue,
        year_days: yearDays,
        date_inclusion: dateInclusion,
        changes: principalChanges,
      },
      result: {
        total_interest: data.total_interest ?? '0',
        total_days: data.total_days ?? 0,
        total_principal: data.total_principal ?? '0',
      },
      rateInfo: getRateInfo({
        start_date: startDate, end_date: endDate, principal,
        rate_mode: rateMode, rate_type: rateType, multiplier,
        custom_rate_unit: customRateUnit, custom_rate_value: customRateValue,
        year_days: yearDays, date_inclusion: dateInclusion, changes: principalChanges,
      }),
    }
    const updated = [item, ...history].slice(0, 20)
    setHistory(updated)
    localStorage.setItem('lpr_calculator_history', JSON.stringify(updated))
  }, [history, principalMode, startDate, endDate, principal, rateMode, rateType, multiplier, customRateUnit, customRateValue, yearDays, dateInclusion, principalChanges])

  const addPrincipalChange = () => {
    const last = principalChanges[principalChanges.length - 1]
    let nextStart = ''
    if (last?.end_date) {
      const d = new Date(last.end_date)
      d.setDate(d.getDate() + 1)
      nextStart = d.toISOString().split('T')[0]
    }
    setPrincipalChanges((prev) => [...prev, { start_date: nextStart, end_date: '', principal: last?.principal ?? '' }])
  }

  const removePrincipalChange = (index: number) => {
    setPrincipalChanges((prev) => prev.filter((_, i) => i !== index))
  }

  const updatePrincipalChange = (index: number, field: keyof PrincipalChange, value: string) => {
    setPrincipalChanges((prev) => prev.map((item, i) => {
      if (i !== index) return item
      const updated = { ...item, [field]: value }
      if (field === 'end_date' && updated.start_date && updated.end_date && updated.end_date < updated.start_date) {
        updated.end_date = updated.start_date
      }
      return updated
    }))
  }

  const handleCalculate = () => {
    const body: LprCalculateRequest = {
      year_days: yearDays,
      date_inclusion: dateInclusion,
    }

    if (rateMode === 'lpr') {
      body.rate_mode = 'lpr'
      body.rate_type = rateType
      body.multiplier = multiplier || '1'
    } else if (rateMode === 'delay') {
      body.rate_mode = 'custom'
      body.custom_rate_unit = 'permyriad'
      body.custom_rate_value = '1.75'
    } else {
      body.rate_mode = 'custom'
      body.custom_rate_unit = customRateUnit
      body.custom_rate_value = customRateValue || null
    }

    if (principalMode === 'variable') {
      body.principal_changes = principalChanges.filter((c) => c.start_date && c.end_date && c.principal)
      if (!body.principal_changes.length) {
        setResult({ success: false, message: '请填写完整的本金变动信息', total_interest: null, total_days: null, total_principal: null, start_date: null, end_date: null, periods: null, code: null, sync_info: null })
        return
      }
    } else {
      body.start_date = startDate || null
      body.end_date = endDate || null
      body.principal = principal || null
      if (!body.start_date || !body.end_date || !body.principal) {
        setResult({ success: false, message: '请填写日期和本金', total_interest: null, total_days: null, total_principal: null, start_date: null, end_date: null, periods: null, code: null, sync_info: null })
        return
      }
    }

    setResult(null)
    setSyncMessage('')
    calcMutation.mutate(body, {
      onSuccess: (data) => {
        setResult(data)
        if (data.sync_info) setSyncMessage(data.sync_info)
        if (data.success) saveToHistory(data)
      },
    })
  }

  const handleReset = () => {
    setPrincipalMode('fixed')
    setPrincipal('100000')
    const today = new Date()
    const lastYear = new Date(today)
    lastYear.setFullYear(lastYear.getFullYear() - 1)
    setEndDate(today.toISOString().split('T')[0])
    setStartDate(lastYear.toISOString().split('T')[0])
    setPrincipalChanges([{ start_date: '', end_date: '', principal: '' }])
    setRateMode('lpr')
    setRateType('1y')
    setMultiplier('1')
    setCustomRateUnit('percent')
    setCustomRateValue('')
    setYearDays(360)
    setDateInclusion('both')
    setResult(null)
    setSyncMessage('')
  }

  const loadFromHistory = (item: HistoryItem) => {
    setPrincipalMode(item.useChanges ? 'variable' : 'fixed')
    setStartDate(item.form.start_date)
    setEndDate(item.form.end_date)
    setPrincipal(item.form.principal)
    setPrincipalChanges(item.form.changes)
    setRateMode(item.form.rate_mode as 'lpr' | 'custom' | 'delay')
    setRateType(item.form.rate_type as '1y' | '5y')
    setMultiplier(item.form.multiplier)
    setCustomRateUnit(item.form.custom_rate_unit as 'percent' | 'permille' | 'permyriad')
    setCustomRateValue(item.form.custom_rate_value)
    setYearDays(item.form.year_days)
    setDateInclusion(item.form.date_inclusion as 'both' | 'start_only' | 'end_only' | 'neither')
    setShowHistory(false)
  }

  const deleteHistoryItem = (id: number) => {
    const updated = history.filter((h) => h.id !== id)
    setHistory(updated)
    localStorage.setItem('lpr_calculator_history', JSON.stringify(updated))
  }

  const [clearConfirmOpen, setClearConfirmOpen] = useState(false)

  const clearHistory = () => {
    setClearConfirmOpen(true)
  }

  const handleClearConfirm = () => {
    setClearConfirmOpen(false)
    setHistory([])
    localStorage.removeItem('lpr_calculator_history')
  }

  const copyDetail = () => {
    if (!result?.success || !result.periods) return
    const groups = groupByPrincipal(result.periods)
    let text = 'LPR利息计算明细\n\n'
    for (const g of groups) {
      text += `本金: ¥${formatMoney(String(g.principal))} | 天数: ${g.totalDays} | 利息: ¥${formatMoney(String(g.totalInterest))}\n`
      text += `期间 | 天数 | 利率 | 利息\n`
      text += '-'.repeat(50) + '\n'
      for (const p of g.periods) {
        text += `${formatDate(p.start_date)}~${formatDate(p.end_date)} | ${p.days} | ${formatRateDisplay(p.rate, p.rate_unit, rateMode)} | ¥${formatMoney(p.interest)}\n`
      }
      text += '\n'
    }
    text += `总计 | ${result.total_days}天 | - | ¥${formatMoney(result.total_interest)}\n`
    copyToClipboard(text, '明细已复制')
  }

  const copyResult = () => {
    if (!result?.success) return
    const text = `LPR利息计算结果\n总利息: ¥${formatMoney(result.total_interest)}\n计息天数: ${result.total_days}天\n本金: ¥${formatMoney(result.total_principal)}`
    copyToClipboard(text, '已复制到剪贴板')
  }

  const groups = result?.success && result.periods ? groupByPrincipal(result.periods) : []

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">利息/违约金计算器</h1>
        <p className="text-muted-foreground text-sm mt-1">基于贷款市场报价利率计算利息</p>
      </div>

      {/* Latest LPR Rate */}
      <div className="rounded-lg border p-4 flex items-center gap-6 bg-muted/30">
        <div className="flex-1">
          <div className="text-sm font-medium">
            当前LPR利率
            {latestRate && <span className="text-muted-foreground font-normal ml-1">（生效日期: {latestRate.effective_date}）</span>}
          </div>
          {latestRate ? (
            <div className="flex gap-6 text-sm text-muted-foreground mt-1">
              <span>一年期: <strong className="text-foreground">{latestRate.rate_1y}%</strong></span>
              <span>五年期: <strong className="text-foreground">{latestRate.rate_5y}%</strong></span>
            </div>
          ) : (
            <div className="text-sm text-destructive mt-1">暂无LPR数据</div>
          )}
        </div>
      </div>

      {/* Form */}
      <div className="rounded-lg border p-6 space-y-5">
        {/* Principal mode */}
        <div>
          <div className="flex gap-1 rounded-md bg-muted p-0.5 w-fit">
            {(['fixed', 'variable'] as const).map((m) => (
              <button
                key={m}
                className={`rounded-sm px-4 py-1.5 text-xs font-medium transition-colors ${principalMode === m ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}
                onClick={() => setPrincipalMode(m)}
              >
                {m === 'fixed' ? '固定本金' : '变动本金'}
              </button>
            ))}
          </div>
        </div>

        {principalMode === 'fixed' ? (
          <div className="space-y-4">
            <div className="grid gap-4 grid-cols-1 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs text-muted-foreground">开始日期</label>
                <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs text-muted-foreground">结束日期</label>
                <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
              </div>
            </div>
            <div className="grid gap-4 grid-cols-1 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs text-muted-foreground">本金金额（元）</label>
                <Input type="number" value={principal} onChange={(e) => setPrincipal(e.target.value)} placeholder="请输入本金金额" />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs text-muted-foreground">日期计算方式</label>
                <select
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  value={dateInclusion}
                  onChange={(e) => setDateInclusion(e.target.value as typeof dateInclusion)}
                >
                  {DATE_INCLUSION_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <label className="text-xs text-muted-foreground font-medium">本金变动记录</label>
              <Button variant="outline" size="sm" className="h-7 text-xs" onClick={addPrincipalChange}>
                <Plus className="size-3 mr-1" />添加本金变动
              </Button>
            </div>
            <div className="rounded-md bg-muted/50 p-4 space-y-3">
              {principalChanges.map((pc, i) => (
                <div key={i} className="grid grid-cols-[1fr_1fr_1fr_auto] gap-2.5 items-end">
                  <div className="flex flex-col gap-1">
                    {i === 0 && <label className="text-xs text-muted-foreground">开始日期</label>}
                    <Input type="date" value={pc.start_date} onChange={(e) => updatePrincipalChange(i, 'start_date', e.target.value)} className="h-9 text-xs" />
                  </div>
                  <div className="flex flex-col gap-1">
                    {i === 0 && <label className="text-xs text-muted-foreground">结束日期</label>}
                    <Input type="date" value={pc.end_date} onChange={(e) => updatePrincipalChange(i, 'end_date', e.target.value)} className="h-9 text-xs" />
                  </div>
                  <div className="flex flex-col gap-1">
                    {i === 0 && <label className="text-xs text-muted-foreground">本金（元）</label>}
                    <Input type="number" value={pc.principal} onChange={(e) => updatePrincipalChange(i, 'principal', e.target.value)} placeholder="本金金额" className="h-9 text-xs" />
                  </div>
                  {principalChanges.length > 1 && (
                    <Button variant="ghost" size="sm" className="h-9 w-9 p-0 text-muted-foreground hover:text-destructive" onClick={() => removePrincipalChange(i)}>
                      <Trash2 className="size-3.5" />
                    </Button>
                  )}
                </div>
              ))}
            </div>
            <div className="flex flex-col gap-1.5 max-w-xs">
              <label className="text-xs text-muted-foreground">日期计算方式</label>
              <select
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                value={dateInclusion}
                onChange={(e) => setDateInclusion(e.target.value as typeof dateInclusion)}
              >
                {DATE_INCLUSION_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
          </div>
        )}

        {/* Rate settings */}
        <div className="pt-4 border-t">
          <div className="flex gap-1 rounded-md bg-muted p-0.5 w-fit mb-4">
            {RATE_MODE_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                className={`rounded-sm px-4 py-1.5 text-xs font-medium transition-colors whitespace-nowrap ${rateMode === opt.value ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}
                onClick={() => setRateMode(opt.value)}
              >
                {opt.label}
              </button>
            ))}
          </div>

          {rateMode === 'lpr' && (
            <div className="grid gap-4 grid-cols-1 sm:grid-cols-3">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs text-muted-foreground">利率类型</label>
                <select
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  value={rateType}
                  onChange={(e) => setRateType(e.target.value as '1y' | '5y')}
                >
                  {RATE_TYPE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs text-muted-foreground">利率倍数</label>
                <Input type="number" step="0.1" min="0.1" value={multiplier} onChange={(e) => setMultiplier(e.target.value)} placeholder="如 1.5" list="lpr-multiplier-suggestions" />
                <datalist id="lpr-multiplier-suggestions">
                  <option value="1" /><option value="1.3" /><option value="1.5" />
                </datalist>
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs text-muted-foreground">计息基准</label>
                <select
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  value={yearDays}
                  onChange={(e) => setYearDays(Number(e.target.value))}
                >
                  {YEAR_DAYS_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </div>
            </div>
          )}

          {rateMode === 'custom' && (
            <div className="grid gap-4 grid-cols-1 sm:grid-cols-3">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs text-muted-foreground">利率单位</label>
                <select
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  value={customRateUnit}
                  onChange={(e) => setCustomRateUnit(e.target.value as 'percent' | 'permille' | 'permyriad')}
                >
                  {CUSTOM_RATE_UNIT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs text-muted-foreground">利率数值</label>
                <Input type="number" step="0.01" min="0" value={customRateValue} onChange={(e) => setCustomRateValue(e.target.value)} placeholder="请输入具体数值" />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs text-muted-foreground">计息基准</label>
                <select
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  value={yearDays}
                  onChange={(e) => setYearDays(Number(e.target.value))}
                >
                  {YEAR_DAYS_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </div>
            </div>
          )}

          {rateMode === 'delay' && (
            <div className="grid gap-4 grid-cols-1 sm:grid-cols-3">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs text-muted-foreground">利率单位</label>
                <Input value="万分之（‱/天）" disabled className="bg-muted text-muted-foreground" />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs text-muted-foreground">利率数值</label>
                <Input value="1.75" disabled className="bg-muted text-muted-foreground" />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs text-muted-foreground">计息基准</label>
                <select
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  value={yearDays}
                  onChange={(e) => setYearDays(Number(e.target.value))}
                >
                  {YEAR_DAYS_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </div>
            </div>
          )}
        </div>

        {syncMessage && (
          <p className="text-xs text-green-700 bg-green-50 border border-green-200 rounded-md px-3 py-2">{syncMessage}</p>
        )}

        {/* Actions */}
        <div className="flex gap-3 items-center pt-2">
          <Button onClick={handleCalculate} disabled={calcMutation.isPending}>
            {calcMutation.isPending ? '计算中...' : '计算利息'}
          </Button>
          <Button variant="outline" onClick={handleReset}>
            <RotateCcw className="size-3.5 mr-1.5" />重置表单
          </Button>
          <Button variant="outline" className="ml-auto" onClick={() => setShowHistory(!showHistory)}>
            <Clock className="size-3.5 mr-1.5" />历史记录
            {history.length > 0 && <span className="text-[11px] text-muted-foreground ml-1">({history.length})</span>}
          </Button>
        </div>

        {/* History panel */}
        {showHistory && (
          <div className="rounded-md bg-muted/50 border p-4 space-y-3">
            <div className="flex items-center justify-between">
              <div className="text-sm font-medium">计算历史</div>
              {history.length > 0 && (
                <button className="text-xs text-destructive hover:underline" onClick={clearHistory}>清空</button>
              )}
            </div>
            {history.length === 0 ? (
              <div className="text-center py-6 text-muted-foreground text-sm">暂无历史记录</div>
            ) : (
              <div className="max-h-[300px] overflow-y-auto space-y-2">
                {history.map((item) => (
                  <div key={item.id} className="flex items-center gap-3 bg-background rounded-md border p-3">
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-medium">
                        <span>{item.useChanges ? '变动本金' : '固定本金'}</span>
                        <span className="text-primary ml-1">· ¥{formatMoney(item.result.total_interest)}</span>
                      </div>
                      <div className="text-[11px] text-muted-foreground mt-0.5">
                        {new Date(item.timestamp).toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                        <span>· {item.result.total_days}天</span>
                      </div>
                      <div className="text-[10px] text-muted-foreground mt-0.5">
                        <span className="bg-muted px-1.5 py-0.5 rounded">{item.rateInfo}</span>
                      </div>
                    </div>
                    <button
                      className="text-xs text-primary bg-primary/10 px-3 py-1.5 rounded hover:bg-primary/20 whitespace-nowrap"
                      onClick={() => loadFromHistory(item)}
                    >
                      加载
                    </button>
                    <button
                      className="text-xs text-destructive bg-destructive/10 px-2 py-1.5 rounded hover:bg-destructive/20"
                      onClick={() => deleteHistoryItem(item.id)}
                    >
                      <X className="size-3" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Results */}
      {result && result.success && (
        <div className="rounded-lg border p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div className="text-sm font-medium">计算明细</div>
            <div className="flex gap-3 items-center">
              <button className="text-xs text-primary hover:underline" onClick={() => setShowDetail(!showDetail)}>
                {showDetail ? '收起' : '展开'}
              </button>
              <button className="text-xs text-primary bg-primary/10 px-3 py-1 rounded hover:bg-primary/20" onClick={copyDetail}>
                复制明细
              </button>
            </div>
          </div>

          {!showDetail ? (
            /* Simplified view */
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>本金</TableHead>
                    <TableHead>计息期间</TableHead>
                    <TableHead className="text-center">天数</TableHead>
                    <TableHead className="text-right">利息</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {groups.map((g, i) => {
                    const start = formatDate(g.periods[0].start_date)
                    const end = formatDate(g.periods[g.periods.length - 1].end_date)
                    return (
                      <TableRow key={i}>
                        <TableCell className="text-sm">¥{formatMoney(String(g.principal))}</TableCell>
                        <TableCell className="text-sm">{start} ~ {end}</TableCell>
                        <TableCell className="text-center text-sm">{g.totalDays}</TableCell>
                        <TableCell className="text-right font-medium text-sm">¥{formatMoney(String(g.totalInterest))}</TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
                <tfoot>
                  <tr className="bg-primary text-primary-foreground font-semibold text-sm">
                    <td className="px-4 py-2.5">合计</td>
                    <td className="px-4 py-2.5">-</td>
                    <td className="px-4 py-2.5 text-center">{result.total_days}</td>
                    <td className="px-4 py-2.5 text-right text-[15px] font-bold">¥{formatMoney(result.total_interest)}</td>
                  </tr>
                </tfoot>
              </Table>
            </div>
          ) : (
            /* Detailed view */
            <div className="space-y-4">
              {groups.map((g, gi) => (
                <div key={gi}>
                  <div className="bg-primary/10 text-primary font-semibold text-sm px-3 py-2 rounded-t-md border border-primary/20">
                    本金: ¥{formatMoney(String(g.principal))} | 天数: {g.totalDays} | 利息: ¥{formatMoney(String(g.totalInterest))}
                  </div>
                  <div className="overflow-x-auto rounded-b-md border border-t-0">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>期间</TableHead>
                          <TableHead className="text-center">天数</TableHead>
                          <TableHead>利率</TableHead>
                          <TableHead className="text-right">利息</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {g.periods.map((p, pi) => (
                          <TableRow key={pi}>
                            <TableCell className="text-sm">{formatDate(p.start_date)} ~ {formatDate(p.end_date)}</TableCell>
                            <TableCell className="text-center text-sm">{p.days}</TableCell>
                            <TableCell className="text-sm whitespace-nowrap">{formatRateDisplay(p.rate, p.rate_unit, rateMode)}</TableCell>
                            <TableCell className="text-right font-medium text-sm">¥{formatMoney(p.interest)}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </div>
              ))}
              <div className="overflow-x-auto rounded-md border">
                <Table>
                  <tfoot>
                    <tr className="bg-primary text-primary-foreground font-semibold text-sm">
                      <td className="px-4 py-2.5">总计</td>
                      <td className="px-4 py-2.5 text-center">{result.total_days}</td>
                      <td className="px-4 py-2.5">-</td>
                      <td className="px-4 py-2.5 text-right text-[15px] font-bold">¥{formatMoney(result.total_interest)}</td>
                    </tr>
                  </tfoot>
                </Table>
              </div>
            </div>
          )}

          <div className="flex justify-end">
            <Button variant="outline" size="sm" onClick={copyResult}>
              <Copy className="size-3.5 mr-1.5" />复制结果
            </Button>
          </div>
        </div>
      )}

      {/* Error */}
      {result && !result.success && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          {result.message}
        </div>
      )}

      <AlertDialog open={clearConfirmOpen} onOpenChange={setClearConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认清空</AlertDialogTitle>
            <AlertDialogDescription>确定要清空所有历史记录吗？此操作不可撤销。</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleClearConfirm}>确定清空</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
