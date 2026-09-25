import { useState } from 'react'
import { Calculator } from 'lucide-react'
import { toast } from 'sonner'

import { calculateInterest } from '../../api'
import type { LprResult } from '../../types'
import { TOOL_ENDPOINT } from '../../constants'
import { BTN_PRIMARY, FIELD } from '../../ui'
import { Spinner, ToolShell } from './shared'
import { errMessage } from '../../errors'

type RateUnit = 'percent' | 'permille' | 'permyriad'

/** LPR 计息：POST /lpr/calculate（LPR 分档 / 自定义利率） */
export function LprCard() {
  const [principal, setPrincipal] = useState('')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [mode, setMode] = useState<'lpr' | 'custom'>('lpr')
  const [rateType, setRateType] = useState<'1y' | '5y'>('1y')
  const [customRate, setCustomRate] = useState('')
  const [customUnit, setCustomUnit] = useState<RateUnit>('percent')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<LprResult | null>(null)

  const submit = async () => {
    const p = Number(principal)
    if (!p || p <= 0) {
      toast.info('本金要填一个正数')
      return
    }
    if (!start || !end) {
      toast.info('起算日和截止日都要填')
      return
    }
    if (end < start) {
      toast.info('截止日要晚于起算日')
      return
    }
    if (mode === 'custom' && !Number(customRate)) {
      toast.info('自定义模式要填利率值')
      return
    }
    setBusy(true)
    try {
      const res = await calculateInterest({
        principal: p,
        startDate: start,
        endDate: end,
        rateMode: mode,
        rateType,
        customRateValue: mode === 'custom' ? Number(customRate) : undefined,
        customRateUnit: customUnit,
      })
      setResult(res)
      if (!res.success) toast.warning(res.message || '后端未能计算利息')
    } catch (e) {
      toast.error(errMessage(e, '利息计算失败'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <ToolShell icon={<Calculator className="h-3.5 w-3.5" />} title="LPR 利息" endpoint={TOOL_ENDPOINT.lpr}>
      <div className="flex flex-1 flex-col gap-[7px]">
        <input
          className={FIELD}
          type="number"
          min="0"
          inputMode="decimal"
          value={principal}
          onChange={(e) => setPrincipal(e.target.value)}
          placeholder="本金 ¥"
        />
        <div className="grid grid-cols-2 gap-[7px]">
          <input className={FIELD} type="date" value={start} onChange={(e) => setStart(e.target.value)} title="起算日" />
          <input className={FIELD} type="date" value={end} onChange={(e) => setEnd(e.target.value)} title="截止日" />
        </div>

        <select className={FIELD} value={mode} onChange={(e) => setMode(e.target.value as 'lpr' | 'custom')}>
          <option value="lpr">LPR 自动（央行报价）</option>
          <option value="custom">自定义利率</option>
        </select>

        {mode === 'lpr' ? (
          <select className={FIELD} value={rateType} onChange={(e) => setRateType(e.target.value as '1y' | '5y')}>
            <option value="1y">1 年期 LPR</option>
            <option value="5y">5 年期以上 LPR</option>
          </select>
        ) : (
          <div className="grid grid-cols-2 gap-[7px]">
            <input
              className={FIELD}
              type="number"
              step="0.01"
              min="0"
              value={customRate}
              onChange={(e) => setCustomRate(e.target.value)}
              placeholder="利率值"
            />
            <select className={FIELD} value={customUnit} onChange={(e) => setCustomUnit(e.target.value as RateUnit)}>
              <option value="percent">%</option>
              <option value="permille">‰</option>
              <option value="permyriad">‱</option>
            </select>
          </div>
        )}

        <div className="mt-auto flex flex-col gap-[7px] pt-[2px]">
          <div className="flex items-center gap-2">
            <button type="button" className={BTN_PRIMARY} onClick={submit} disabled={busy}>
              {busy && <Spinner />}
              计算利息
            </button>
            <span className="flex-1 truncate text-right text-[9.5px] text-muted-foreground">按时段 LPR 分档 · 360 天基准</span>
          </div>
          {result?.success && result.totalInterest && (
            <div className="rounded-[8px] border border-status-red/30 bg-status-red-bg px-2.5 py-2">
              <div className="text-[16px] font-bold tabular-nums tracking-[-0.01em] text-status-red">
                ¥{Number(result.totalInterest).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
              <div className="mt-[2px] text-[10px] leading-[1.4] text-secondary-foreground">
                {result.totalDays != null ? `${result.totalDays} 天` : ''}
                {result.summary ? ` · ${result.summary}` : ''}
              </div>
            </div>
          )}
        </div>
      </div>
    </ToolShell>
  )
}
