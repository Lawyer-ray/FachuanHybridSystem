import { useState, useCallback, useEffect, useRef } from 'react'
import { Landmark, Loader2, RefreshCw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { DetailCard } from '@/components/shared'
import { formatAmount } from '@/lib/format'
import { caseApi } from '../api'
import type { Case } from '../types'
import type { CourtFilingCaseInfo, CourtFilingSession } from '../api/court-filing'

interface Props {
  caseId: number
  caseData: Case
}

const FILING_TYPE_LABELS: Record<string, string> = {
  civil: '民事一审',
  execution: '申请执行',
}

function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return '-'
  if (seconds < 1) return '< 1s'
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`
}

export function CourtFilingSection({ caseId, caseData }: Props) {
  const [filingInfo, setFilingInfo] = useState<CourtFilingCaseInfo | null>(null)
  const [loadingInfo, setLoadingInfo] = useState(false)
  const [filingEngine, setFilingEngine] = useState<string>('playwright')
  const [executing, setExecuting] = useState(false)
  const [result, setResult] = useState<{ success: boolean; message: string } | null>(null)
  const [timing, setTiming] = useState<CourtFilingSession['timing']>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined)

  const courtName = caseData.supervising_authorities?.find(a => a.authority_type === 'trial')?.name

  const loadInfo = useCallback(async () => {
    setLoadingInfo(true)
    try {
      const info = await caseApi.getCourtFilingInfo(caseId)
      setFilingInfo(info)
      setFilingEngine(info.default_filing_engine || 'playwright')
    } catch {
      // silently fail
    } finally {
      setLoadingInfo(false)
    }
  }, [caseId])

  useEffect(() => { loadInfo() }, [loadInfo])

  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [])

  const pollSession = useCallback((sessionId: string) => {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const s = await caseApi.getCourtFilingSession(sessionId)
        setResult({ success: s.success, message: s.message })
        if (s.timing) setTiming(s.timing)
        if (s.status === 'completed' || s.status === 'failed') {
          if (pollRef.current) clearInterval(pollRef.current)
          setExecuting(false)
        }
      } catch {
        if (pollRef.current) clearInterval(pollRef.current)
        setExecuting(false)
      }
    }, 3000)
  }, [])

  const handleExecute = async () => {
    setExecuting(true)
    setResult(null)
    setTiming(null)
    try {
      const res = await caseApi.executeCourtFiling({
        case_id: caseId,
        filing_type: (filingInfo?.suggested_filing_type || 'civil') as 'civil' | 'execution',
        filing_engine: filingEngine as 'api' | 'playwright',
      })
      setResult({ success: res.success, message: res.message })
      if (res.timing) setTiming(res.timing)
      if (res.session_id && (res.status === 'in_progress' || res.status === 'running')) {
        pollSession(String(res.session_id))
      } else {
        setExecuting(false)
      }
    } catch {
      setResult({ success: false, message: '启动立案失败' })
      setExecuting(false)
    }
  }

  // 条件判断
  const noCourt = !filingInfo?.court_name && !courtName
  const notPlaintiff = filingInfo != null && !filingInfo.our_party_is_plaintiff_side
  const noCredential = filingInfo != null && !filingInfo.has_court_credential
  const canExecute = filingInfo && !noCourt && !notPlaintiff && !noCredential && !executing

  const showHint = filingInfo && !executing
  const hint = noCourt ? '请先设置管辖法院（案件管辖机关）'
    : notPlaintiff ? '我方当事人为被告/被申请人，无需立案'
    : noCredential ? '您没有一张网账号密码，请先在律师管理中添加'
    : null

  const filingTypeLabel = FILING_TYPE_LABELS[filingInfo?.suggested_filing_type ?? ''] ?? '民事一审'

  return (
    <DetailCard title="法院一张网在线立案" extra={<Landmark className="text-muted-foreground size-4" />}>
      {loadingInfo ? (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="size-5 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <div className="space-y-4">
          {/* 案件信息摘要 */}
          <div className="rounded-md border border-border/60 bg-muted/30 px-4 py-3 space-y-2">
            <div className="grid gap-2 sm:grid-cols-3 text-[13px]">
              <div>
                <span className="text-muted-foreground">案由：</span>
                <span className="font-medium">{filingInfo?.cause_of_action || caseData.cause_of_action || '—'}</span>
              </div>
              <div>
                <span className="text-muted-foreground">管辖法院：</span>
                <span className="font-medium">{filingInfo?.court_name || courtName || '未设置'}</span>
              </div>
              <div>
                <span className="text-muted-foreground">标的额：</span>
                <span className="font-medium">{formatAmount(filingInfo?.target_amount ? Number(filingInfo.target_amount) : caseData.target_amount)}</span>
              </div>
            </div>
            <div className="flex items-center gap-4 text-xs text-muted-foreground">
              <span>立案类型：<span className="font-medium text-foreground">{filingTypeLabel}</span></span>
              <span className="flex items-center gap-3">
                立案引擎：
                <label className="inline-flex items-center gap-1.5 cursor-pointer">
                  <input
                    type="radio"
                    name="filing_engine"
                    value="api"
                    checked={filingEngine === 'api'}
                    onChange={() => setFilingEngine('api')}
                    disabled={executing || !filingInfo?.has_http_plugin}
                    className="accent-primary"
                  />
                  <span>HTTP主链路{filingInfo?.has_http_plugin ? '（默认）' : ''}</span>
                </label>
                <label className="inline-flex items-center gap-1.5 cursor-pointer">
                  <input
                    type="radio"
                    name="filing_engine"
                    value="playwright"
                    checked={filingEngine === 'playwright'}
                    onChange={() => setFilingEngine('playwright')}
                    disabled={executing}
                    className="accent-primary"
                  />
                  <span>Playwright{!filingInfo?.has_http_plugin ? '（默认）' : ''}</span>
                </label>
              </span>
            </div>
          </div>

          {/* 材料匹配 */}
          {filingInfo?.material_slots && filingInfo.material_slots.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-xs font-medium text-muted-foreground">材料匹配</p>
              <div className="space-y-1">
                {filingInfo.material_slots.map((slot, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs">
                    <span className="text-muted-foreground">{slot.slot_name}</span>
                    {slot.matched_file ? (
                      <span className="text-green-700">{slot.matched_file}</span>
                    ) : (
                      <Badge variant="outline" className="text-[10px]">
                        {slot.required ? '未匹配（必需）' : '未匹配'}
                      </Badge>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 操作按钮 */}
          <div className="flex items-center gap-3">
            <Button
              size="sm"
              variant="outline"
              disabled={!canExecute}
              onClick={handleExecute}
            >
              {executing ? <Loader2 className="size-3.5 mr-1 animate-spin" /> : <span className="mr-1">🚀</span>}
              {executing ? '执行中...' : '开始一张网立案'}
            </Button>
            <Button size="sm" variant="ghost" disabled={loadingInfo} onClick={loadInfo}>
              <RefreshCw className={`size-3.5 ${loadingInfo ? 'animate-spin' : ''}`} />
            </Button>
            {showHint && hint && (
              <span className="text-xs text-red-600">{hint}</span>
            )}
          </div>

          {/* 执行结果 */}
          {result && (
            <div className={`rounded-md px-3 py-2 text-xs ${
              result.success
                ? 'bg-green-50 border border-green-200 text-green-700'
                : 'bg-red-50 border border-red-200 text-red-700'
            }`}>
              {result.success ? '✓' : '✗'} {result.message}
            </div>
          )}

          {/* 耗时统计 */}
          {timing && timing.overall_end && (
            <div className="rounded-md border border-border/60 bg-muted/30 px-3 py-2 text-xs space-y-1">
              <p className="font-medium text-muted-foreground mb-1">耗时统计</p>
              <div className="grid gap-1 sm:grid-cols-2">
                {timing.login_end && (
                  <div>
                    <span className="text-muted-foreground">登录：</span>
                    <span className="font-medium">{formatDuration(timing.login_end - timing.overall_start)}</span>
                  </div>
                )}
                {timing.http_start && timing.http_end && (
                  <div>
                    <span className="text-muted-foreground">HTTP主链路：</span>
                    <span className="font-medium">{formatDuration(timing.http_end - timing.http_start)}</span>
                  </div>
                )}
                {timing.playwright_start && timing.playwright_end && (
                  <div>
                    <span className="text-muted-foreground">Playwright：</span>
                    <span className="font-medium">{formatDuration(timing.playwright_end - timing.playwright_start)}</span>
                  </div>
                )}
                <div>
                  <span className="text-muted-foreground">总耗时：</span>
                  <span className="font-semibold">{formatDuration(timing.overall_end - timing.overall_start)}</span>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </DetailCard>
  )
}
