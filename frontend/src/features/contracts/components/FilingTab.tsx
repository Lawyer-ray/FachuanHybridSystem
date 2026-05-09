import { useState, useEffect, useCallback, useRef } from 'react'
import { Briefcase, Loader2, CheckCircle2, XCircle, AlertCircle } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { contractApi } from '../api'
import type { Contract, OAConfig, FilingSession } from '../types'
import { useNavigate } from 'react-router'
import { DetailCard } from '@/components/shared'

export function FilingTab({ contract: c }: { contract: Contract }) {
  const navigate = useNavigate()
  const [configs, setConfigs] = useState<OAConfig[]>([])
  const [selectedConfig, setSelectedConfig] = useState<string | null>(null)
  const [executing, setExecuting] = useState(false)
  const [session, setSession] = useState<FilingSession | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    contractApi.fetchOAConfigs().then(setConfigs).catch(() => setConfigs([]))
  }, [])

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  useEffect(() => () => stopPolling(), [stopPolling])

  const pollSession = useCallback((sessionId: number) => {
    stopPolling()
    pollRef.current = setInterval(async () => {
      try {
        const s = await contractApi.getFilingSession(sessionId)
        setSession(s)
        if (s.status !== 'in_progress' && s.status !== 'pending') {
          stopPolling()
          setExecuting(false)
          if (s.status === 'completed') {
            toast.success('立案完成')
          } else if (s.status === 'failed') {
            toast.error(`立案失败: ${s.error_message || '未知错误'}`)
          }
        }
      } catch {
        stopPolling()
        setExecuting(false)
      }
    }, 3000)
  }, [stopPolling])

  const handleExecute = useCallback(async () => {
    if (!selectedConfig) return
    setExecuting(true)
    setSession(null)
    try {
      const firstCaseId = c.cases.length > 0 ? c.cases[0].id : undefined
      const s = await contractApi.executeOAFiling(selectedConfig, c.id, firstCaseId)
      setSession(s)
      if (s.status === 'in_progress' || s.status === 'pending') {
        pollSession(s.id)
      } else {
        setExecuting(false)
      }
    } catch {
      toast.error('立案请求失败')
      setExecuting(false)
    }
  }, [selectedConfig, c.id, c.cases, pollSession])

  const selectedHasCredential = configs.find(cfg => cfg.id === selectedConfig)?.has_credential ?? false

  return (
    <div>
      {/* Related Cases */}
      <DetailCard title="关联案件">
        {c.cases.length > 0 ? (
          <div className="flex flex-col gap-2">
            {c.cases.map(cs => (
              <div
                key={cs.id}
                className="flex items-center gap-3 rounded-md border border-border/60 bg-muted/30 px-3 py-2.5 text-[13px] cursor-pointer hover:bg-muted/60 transition-colors"
                onClick={() => navigate(`/admin/cases/${cs.id}`)}
              >
                <Briefcase className="size-3.5 text-muted-foreground shrink-0" />
                <span className="font-medium flex-1 truncate">{cs.name}</span>
                {cs.status_label && <Badge variant="outline" className="text-[10px] px-1.5 py-0 shrink-0">{cs.status_label}</Badge>}
                {cs.current_stage_label && <span className="text-muted-foreground text-xs">{cs.current_stage_label}</span>}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-muted-foreground text-[13px]">暂无关联案件</p>
        )}
      </DetailCard>

      {/* OA System Filing */}
      <DetailCard title="OA 系统立案">
        <p className="text-muted-foreground text-[13px] mb-4">
          通过律所 OA 系统自动立案，系统将自动填写表单并同步至法院立案系统。
        </p>

        <div className="flex items-center gap-3 mb-4">
          <Select value={selectedConfig ?? ''} onValueChange={setSelectedConfig}>
            <SelectTrigger className="w-[240px] h-8 text-xs">
              <SelectValue placeholder="选择 OA 系统" />
            </SelectTrigger>
            <SelectContent>
              {configs.map(cfg => (
                <SelectItem key={cfg.id} value={cfg.id} className="text-xs">
                  {cfg.oa_system_name}
                  {!cfg.has_credential && ' (无凭证)'}
                </SelectItem>
              ))}
              {configs.length === 0 && (
                <SelectItem value="__none" disabled className="text-xs text-muted-foreground">
                  暂无可用 OA 系统
                </SelectItem>
              )}
            </SelectContent>
          </Select>

          <Button
            variant="outline" size="sm" className="h-8 text-xs"
            onClick={handleExecute}
            disabled={executing || !selectedConfig || !selectedHasCredential}
          >
            {executing ? <Loader2 className="mr-1.5 size-3.5 animate-spin" /> : null}
            开始立案
          </Button>
        </div>

        {selectedConfig && !selectedHasCredential && (
          <div className="flex items-center gap-2 text-xs text-amber-600 mb-3">
            <AlertCircle className="size-3.5" />
            <span>该 OA 系统未配置凭证，请先在设置中配置。</span>
          </div>
        )}

        {/* Session status */}
        {session && (
          <div className={`flex items-start gap-3 rounded-md border px-4 py-3 text-[13px] ${
            session.status === 'completed' ? 'border-green-200 bg-green-50' :
            session.status === 'failed' ? 'border-red-200 bg-red-50' :
            'border-blue-200 bg-blue-50'
          }`}>
            {session.status === 'completed' && <CheckCircle2 className="size-4 text-green-600 shrink-0 mt-0.5" />}
            {session.status === 'failed' && <XCircle className="size-4 text-red-600 shrink-0 mt-0.5" />}
            {(session.status === 'in_progress' || session.status === 'pending') && <Loader2 className="size-4 text-blue-600 animate-spin shrink-0 mt-0.5" />}
            <div>
              <div className="font-medium">
                {session.status === 'completed' && '立案完成'}
                {session.status === 'failed' && '立案失败'}
                {session.status === 'in_progress' && '立案执行中...'}
                {session.status === 'pending' && '等待执行...'}
              </div>
              {session.error_message && (
                <div className="text-red-600 mt-1">{session.error_message}</div>
              )}
            </div>
          </div>
        )}
      </DetailCard>
    </div>
  )
}
