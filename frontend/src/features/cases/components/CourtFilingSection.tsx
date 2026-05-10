import { useState, useCallback, useEffect, useRef } from 'react'
import { Landmark, Loader2, Play, RefreshCw } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { DetailCard } from '@/components/shared'
import { formatAmount } from '@/lib/format'
import { caseApi } from '../api'
import type { Case } from '../types'
import type { CourtFilingCaseInfo, CourtFilingSession } from '../api/court-filing'

interface Props {
  caseId: number
  caseData: Case
}

export function CourtFilingSection({ caseId, caseData }: Props) {
  const [filingInfo, setFilingInfo] = useState<CourtFilingCaseInfo | null>(null)
  const [loadingInfo, setLoadingInfo] = useState(false)
  const [filingType, setFilingType] = useState<string>('')
  const [executing, setExecuting] = useState(false)
  const [session, setSession] = useState<CourtFilingSession | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined)

  const courtName = caseData.supervising_authorities?.find(a => a.authority_type === 'trial')?.name

  const loadInfo = useCallback(async () => {
    setLoadingInfo(true)
    try {
      const info = await caseApi.getCourtFilingInfo(caseId)
      setFilingInfo(info)
      if (info.suggested_filing_type) setFilingType(info.suggested_filing_type)
    } catch {
      // silently fail - info is optional enhancement
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
        setSession(s)
        if (s.status === 'completed' || s.status === 'failed') {
          if (pollRef.current) clearInterval(pollRef.current)
          if (s.status === 'completed') toast.success('立案完成')
          else toast.error(`立案失败: ${s.error}`)
          setExecuting(false)
        }
      } catch {
        if (pollRef.current) clearInterval(pollRef.current)
        setExecuting(false)
      }
    }, 2000)
  }, [])

  const handleExecute = async () => {
    if (!filingType) {
      toast.error('请选择立案类型')
      return
    }
    setExecuting(true)
    try {
      const result = await caseApi.executeCourtFiling({
        case_id: caseId,
        filing_type: filingType as 'civil' | 'execution',
      })
      setSession(result)
      if (result.status === 'running' || result.status === 'pending') {
        pollSession(result.session_id)
      }
    } catch {
      toast.error('启动立案失败')
      setExecuting(false)
    }
  }

  const statusColor = session?.status === 'completed' ? 'bg-green-50 text-green-700'
    : session?.status === 'failed' ? 'bg-red-50 text-red-700'
    : session?.status === 'running' ? 'bg-blue-50 text-blue-700'
    : 'bg-muted text-muted-foreground'

  return (
    <DetailCard title="法院一张网在线立案" extra={<Landmark className="text-muted-foreground size-4" />}>
      <div className="space-y-4">
        <div key="case-info" className="rounded-md border border-border/60 bg-muted/30 px-4 py-3">
          <div className="grid gap-3 sm:grid-cols-3 text-[13px]">
            <div>
              <span className="text-muted-foreground">案由：</span>
              <span className="font-medium">{caseData.cause_of_action || '—'}</span>
            </div>
            <div>
              <span className="text-muted-foreground">管辖法院：</span>
              <span className="font-medium">{courtName || '未设置'}</span>
            </div>
            <div>
              <span className="text-muted-foreground">标的额：</span>
              <span className="font-medium">{formatAmount(caseData.target_amount)}</span>
            </div>
          </div>
        </div>

        {filingInfo && (
          <div key="filing-info" className="space-y-3">
            {filingInfo?.has_credentials === false && (
              <div key="credentials-warning" className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
                缺少法院登录凭证，请先在系统设置中配置
              </div>
            )}
            {filingInfo.material_slots && filingInfo.material_slots.length > 0 && (
              <div key="material-slots" className="space-y-1">
                <p className="text-xs font-medium text-muted-foreground">材料匹配</p>
                {filingInfo.material_slots.map((slot, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs">
                    <span className="text-muted-foreground">{slot.slot_name}</span>
                    {slot.matched_file ? (
                      <Badge variant="outline" className="text-[10px] bg-green-50 text-green-700">{slot.matched_file}</Badge>
                    ) : (
                      <Badge variant="outline" className="text-[10px]">{slot.required ? '未匹配（必需）' : '未匹配'}</Badge>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <div key="controls" className="flex items-center gap-3">
          <Select value={filingType} onValueChange={setFilingType}>
            <SelectTrigger className="w-[160px] h-8">
              <SelectValue placeholder="立案类型" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="civil">民事立案</SelectItem>
              <SelectItem value="execution">执行立案</SelectItem>
            </SelectContent>
          </Select>
          <Button
            size="sm"
            variant="outline"
            disabled={executing || !filingType}
            onClick={handleExecute}
          >
            {executing ? <Loader2 className="size-3.5 mr-1 animate-spin" /> : <Play className="size-3.5 mr-1" />}
            开始立案
          </Button>
          <Button size="sm" variant="ghost" disabled={loadingInfo} onClick={loadInfo}>
            <RefreshCw className={`size-3.5 ${loadingInfo ? 'animate-spin' : ''}`} />
          </Button>
        </div>

        {session && (
          <div key="session" className="rounded-md border border-border/60 bg-muted/30 px-4 py-3 space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">状态：</span>
              <Badge variant="outline" className={`text-[11px] ${statusColor}`}>
                {session.status === 'completed' ? '已完成' : session.status === 'failed' ? '失败' : session.status === 'running' ? '执行中' : session.status}
              </Badge>
              {session.progress > 0 && (
                <span className="text-xs text-muted-foreground">{session.progress}%</span>
              )}
            </div>
            {session.current_step && <p className="text-xs text-muted-foreground">{session.current_step}</p>}
            {session.error && <p className="text-xs text-red-600">{session.error}</p>}
          </div>
        )}
      </div>
    </DetailCard>
  )
}
