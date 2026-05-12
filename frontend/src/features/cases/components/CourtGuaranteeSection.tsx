import { useState, useCallback, useEffect, useRef } from 'react'
import { Shield, Loader2, Play, RefreshCw, Trash2, Link2, RotateCw, AlertCircle } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { DetailCard } from '@/components/shared'
import { formatAmount } from '@/lib/format'
import { caseApi } from '../api'
import type { CourtGuaranteeCaseInfo, CourtGuaranteeSession } from '../api/court-guarantee'


interface Props {
  caseId: number
}

export function CourtGuaranteeSection({ caseId }: Props) {
  const [guaranteeInfo, setGuaranteeInfo] = useState<CourtGuaranteeCaseInfo | null>(null)
  const [loadingInfo, setLoadingInfo] = useState(false)
  const [insurerId, setInsurerId] = useState<string>('')
  const [respondentId, setRespondentId] = useState<string>('')
  const [consultantCode, setConsultantCode] = useState('')
  const [executing, setExecuting] = useState(false)
  const [session, setSession] = useState<CourtGuaranteeSession | null>(null)
  const [quoteLoading, setQuoteLoading] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined)

  const loadInfo = useCallback(async () => {
    setLoadingInfo(true)
    try {
      const info = await caseApi.getCourtGuaranteeInfo(caseId)
      setGuaranteeInfo(info)
    } catch {
      // silently fail
    } finally {
      setLoadingInfo(false)
    }
  }, [caseId])

  useEffect(() => { loadInfo() }, [loadInfo])
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current) }, [])

  const pollSession = useCallback((sessionId: string) => {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const s = await caseApi.getCourtGuaranteeSession(sessionId)
        setSession(s)
        if (s.status === 'completed' || s.status === 'failed') {
          if (pollRef.current) clearInterval(pollRef.current)
          if (s.status === 'completed') toast.success('保全申请完成')
          else toast.error(`保全申请失败: ${s.error}`)
          setExecuting(false)
          loadInfo()
        }
      } catch {
        if (pollRef.current) clearInterval(pollRef.current)
        setExecuting(false)
      }
    }, 2000)
  }, [loadInfo])

  const handleEnsureQuote = async () => {
    setQuoteLoading(true)
    try {
      await caseApi.ensureGuaranteeQuote({
        case_id: caseId,
        insurer_id: insurerId || undefined,
        respondent_id: respondentId ? Number(respondentId) : undefined,
        consultant_code: consultantCode || undefined,
      })
      toast.success('询价已提交')
      loadInfo()
    } catch {
      toast.error('询价失败')
    } finally {
      setQuoteLoading(false)
    }
  }

  const handleExecute = async () => {
    setExecuting(true)
    try {
      const result = await caseApi.executeCourtGuarantee(caseId)
      setSession(result)
      if (result.status === 'running' || result.status === 'pending') {
        pollSession(result.session_id)
      }
    } catch {
      toast.error('申请保全失败')
      setExecuting(false)
    }
  }

  const quoteContext = guaranteeInfo?.quote_context
  const hasPreservationAmount = guaranteeInfo?.preservation_amount != null && guaranteeInfo.preservation_amount > 0
  const hasQuote = quoteContext?.quote_id != null
  const statusColor = session?.status === 'completed' ? 'bg-green-50 text-green-700'
    : session?.status === 'failed' ? 'bg-red-50 text-red-700'
    : session?.status === 'running' ? 'bg-blue-50 text-blue-700'
    : 'bg-muted text-muted-foreground'

  return (
    <DetailCard title="诉讼保全担保" extra={<Shield className="text-muted-foreground size-4" />}>
      <div className="space-y-4">
        {guaranteeInfo && (
          <div key="info" className="rounded-md border border-border/60 bg-muted/30 px-4 py-3 text-[13px]">
            <div className="grid gap-3 sm:grid-cols-3">
              <div key="court">
                <span className="text-muted-foreground">管辖法院：</span>
                <span className="font-medium">{guaranteeInfo.court_name || '—'}</span>
              </div>
              <div key="amount">
                <span className="text-muted-foreground">保全金额：</span>
                <span className={`font-medium ${!hasPreservationAmount ? 'text-destructive' : ''}`}>
                  {formatAmount(guaranteeInfo.preservation_amount)}
                </span>
              </div>
              <div key="category">
                <span className="text-muted-foreground">保全类型：</span>
                <span className="font-medium">{guaranteeInfo.category || '—'}</span>
              </div>
            </div>
          </div>
        )}

        {!hasPreservationAmount && (
          <div key="warning" className="rounded-md border border-destructive/30 bg-destructive/5 px-4 py-3 flex items-start gap-2">
            <AlertCircle className="size-4 text-destructive shrink-0 mt-0.5" />
            <div className="text-[13px]">
              <p className="font-medium text-destructive">未填写保全金额</p>
              <p className="text-muted-foreground mt-1">请先在案件信息中填写保全金额，才能进行询价和申请保全。</p>
            </div>
          </div>
        )}

        {/* Quote context */}
        {quoteContext && quoteContext.quote_id && (
          <div key="quote" className="rounded-md border border-border/60 bg-muted/30 px-4 py-3 space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">报价信息</span>
              <Badge variant="outline" className="text-[10px]">
                {quoteContext.status === 'completed' ? '已完成' : quoteContext.status === 'failed' ? '失败' : quoteContext.status}
              </Badge>
            </div>
            <div className="grid gap-2 sm:grid-cols-3 text-xs">
              {quoteContext.insurer && (
                <div key="insurer"><span className="text-muted-foreground">保险公司：</span><span className="font-medium">{quoteContext.insurer}</span></div>
              )}
              {quoteContext.amount != null && (
                <div key="amount"><span className="text-muted-foreground">保额：</span><span className="font-medium">{formatAmount(quoteContext.amount)}</span></div>
              )}
              {quoteContext.premium != null && (
                <div key="premium"><span className="text-muted-foreground">保费：</span><span className="font-medium">{formatAmount(quoteContext.premium)}</span></div>
              )}
            </div>
            <div className="flex items-center gap-2 pt-1">
              {quoteContext.binding_id ? (
                <Badge variant="outline" className="text-[10px] bg-green-50 text-green-700">已绑定</Badge>
              ) : (
                <Button size="sm" variant="outline" onClick={async () => {
                  try {
                    await caseApi.bindGuaranteeQuote(quoteContext.quote_id!)
                    toast.success('绑定成功')
                    loadInfo()
                  } catch { toast.error('绑定失败') }
                }}>
                  <Link2 className="size-3 mr-1" />绑定
                </Button>
              )}
              {quoteContext.status === 'failed' && (
                <Button size="sm" variant="outline" onClick={async () => {
                  try {
                    await caseApi.retryGuaranteeQuote(quoteContext.quote_id!)
                    toast.success('重试已提交')
                    loadInfo()
                  } catch { toast.error('重试失败') }
                }}>
                  <RotateCw className="size-3 mr-1" />重试
                </Button>
              )}
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button size="sm" variant="outline" className="text-destructive hover:text-destructive">
                    <Trash2 className="size-3 mr-1" />删除报价
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>确认删除报价</AlertDialogTitle>
                    <AlertDialogDescription>此操作不可撤销</AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>取消</AlertDialogCancel>
                    <AlertDialogAction onClick={async () => {
                      try {
                        await caseApi.deleteGuaranteeQuote(quoteContext.quote_id!)
                        toast.success('已删除')
                        loadInfo()
                      } catch { toast.error('删除失败') }
                    }}>确认</AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          </div>
        )}

        {/* Step 1: Quote */}
        <div key="step-quote" className="space-y-3">
          <div className="flex items-center gap-2">
            <span className="flex items-center justify-center size-5 rounded-full bg-primary text-primary-foreground text-[11px] font-medium">1</span>
            <span className="text-sm font-medium">询价</span>
          </div>
          <div className="grid gap-3 sm:grid-cols-3 pl-7">
            {guaranteeInfo?.insurance_options && guaranteeInfo.insurance_options.length > 0 && (
              <Select key="insurer" value={insurerId} onValueChange={setInsurerId}>
                <SelectTrigger className="h-8"><SelectValue placeholder="保险公司" /></SelectTrigger>
                <SelectContent>
                  {guaranteeInfo.insurance_options.map((opt, i) => (
                    <SelectItem key={opt.id ?? `insurer-${i}`} value={opt.id}>{opt.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            {guaranteeInfo?.respondent_options && guaranteeInfo.respondent_options.length > 0 && (
              <Select key="respondent" value={respondentId} onValueChange={setRespondentId}>
                <SelectTrigger className="h-8"><SelectValue placeholder="被申请人" /></SelectTrigger>
                <SelectContent>
                  {guaranteeInfo.respondent_options.map((opt, i) => (
                    <SelectItem key={opt.id ?? `respondent-${i}`} value={String(opt.id)}>{opt.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            <input
              type="text"
              className="border-input bg-background placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 h-8 rounded-md border px-3 text-sm shadow-xs outline-none focus-visible:ring-[3px]"
              placeholder="顾问代码（可选）"
              value={consultantCode}
              onChange={(e) => setConsultantCode(e.target.value)}
            />
          </div>
          <div className="flex items-center gap-2 pl-7">
            <Button
              size="sm"
              variant="outline"
              disabled={!hasPreservationAmount || quoteLoading}
              onClick={handleEnsureQuote}
            >
              {quoteLoading ? <Loader2 className="size-3.5 mr-1 animate-spin" /> : <RefreshCw className="size-3.5 mr-1" />}
              询价
            </Button>
            <Button size="sm" variant="ghost" disabled={loadingInfo} onClick={loadInfo}>
              <RefreshCw className={`size-3.5 ${loadingInfo ? 'animate-spin' : ''}`} />
            </Button>
          </div>
        </div>

        {/* Step 2: Apply */}
        <div key="step-apply" className="space-y-3">
          <div className="flex items-center gap-2">
            <span className={`flex items-center justify-center size-5 rounded-full text-[11px] font-medium ${hasQuote ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'}`}>2</span>
            <span className={`text-sm font-medium ${!hasQuote ? 'text-muted-foreground' : ''}`}>申请保全</span>
          </div>
          <div className="pl-7">
            <Button
              size="sm"
              disabled={!hasQuote || executing}
              onClick={handleExecute}
            >
              {executing ? <Loader2 className="size-3.5 mr-1 animate-spin" /> : <Play className="size-3.5 mr-1" />}
              申请保全
            </Button>
          </div>
        </div>

        {session && (
          <div key="session" className="rounded-md border border-border/60 bg-muted/30 px-4 py-3 space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">状态：</span>
              <Badge variant="outline" className={`text-[11px] ${statusColor}`}>
                {session.status === 'completed' ? '已完成' : session.status === 'failed' ? '失败' : session.status === 'running' ? '执行中' : session.status}
              </Badge>
              {session.progress > 0 && <span className="text-xs text-muted-foreground">{session.progress}%</span>}
            </div>
            {session.current_step && <p className="text-xs text-muted-foreground">{session.current_step}</p>}
            {session.error && <p className="text-xs text-red-600">{session.error}</p>}
          </div>
        )}
      </div>
    </DetailCard>
  )
}
