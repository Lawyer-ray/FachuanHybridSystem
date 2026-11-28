import { useCallback, useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ExternalLink, Loader2 } from 'lucide-react'
import { toast } from 'sonner'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Sheet, SheetBody, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { errMessage } from '@/lib/errors'

import {
  archiveContract,
  getArchiveChecklist,
  getFilingInfo,
  getFilingSession,
  getGuaranteeInfo,
  getGuaranteeSession,
  getOaFilingSession,
  listOaFilingConfigs,
  startFiling,
  startGuarantee,
  startOaFiling,
  type CourtSessionOut,
} from '../../api'
import { refetchContractAndCases } from './refetch-contract'

/**
 * 案件「办理」抽屉：一张网立案 / 申请担保 / OA 立案 / 项目归档。
 *
 * ═══ 为什么是一个抽屉、不是四个按钮 ═══
 * 这四件事都不是高频动作（一件案子一辈子各做一两次），各自摆一个按钮会把案件卡
 * 变成工具栏。所以案件卡上只有一个「办理」，点开是四行：每行**一句就绪状态 +
 * 一个主按钮**，没有二级菜单、没有历史列表。
 *
 * ═══ 三件必须诚实的事 ═══
 * 1. **点下去是真的提交**（法院 / OA / 保险公司），不是演练——所以按钮旁写明，且
 *    缺凭证时直接禁用并说明原因，不让人点了才失败。
 * 2. **执行是异步会话**：后台跑浏览器自动化，几十秒到几分钟。这里轮询 `session`，
 *    把后端原话（status / message / error_message）贴出来，不假装秒完成。
 * 3. **归档会连带结案**：该项目下所有在办案件一并结案、且改回「在办」不会重开，
 *    所以单独一次确认。
 */
export function CaseActionsSheet({
  open,
  onClose,
  caseId,
  caseLabel,
  contractId,
  onChanged,
}: {
  open: boolean
  onClose: () => void
  caseId: number
  caseLabel: string
  contractId: number
  /** 归档成功后刷新合同与案件（状态变了，左栏与列表都要重取） */
  onChanged: () => void
}) {
  const qc = useQueryClient()
  const filingQ = useQuery({
    queryKey: ['workbench', 'filing-info', caseId],
    queryFn: () => getFilingInfo(caseId),
    enabled: open,
    staleTime: 60_000,
  })
  const guaranteeQ = useQuery({
    queryKey: ['workbench', 'guarantee-info', caseId],
    queryFn: () => getGuaranteeInfo(caseId),
    enabled: open,
    staleTime: 60_000,
  })
  const oaQ = useQuery({
    queryKey: ['workbench', 'oa-filing-configs'],
    queryFn: listOaFilingConfigs,
    enabled: open,
    staleTime: 10 * 60_000,
  })
  const archiveQ = useQuery({
    queryKey: ['workbench', 'archive-checklist', contractId],
    queryFn: () => getArchiveChecklist(contractId),
    enabled: open,
    staleTime: 60_000,
  })

  /** 每行的运行态：一个会话一个（同一时间只跑一件，够用且不让人看串） */
  const [session, setSession] = useState<{ key: string; text: string; running: boolean } | null>(null)
  const timerRef = useRef<number | null>(null)
  useEffect(() => () => { if (timerRef.current) window.clearInterval(timerRef.current) }, [])

  /**
   * 轮询一个异步会话直到终态。
   *
   * 终态判据刻意宽松：后端各链路的 status 词表不完全一致（running/in_progress/
   * completed/failed…），这里「成功 或 出现失败/完成字样」就停；另外给 3 分钟上限，
   * 免得一个卡死的会话把抽屉钉在那里一直转。
   */
  const poll = useCallback(
    (key: string, sessionId: number, read: (id: number) => Promise<CourtSessionOut | { status: string; error_message?: string }>) => {
      let ticks = 0
      const stop = () => {
        if (timerRef.current) window.clearInterval(timerRef.current)
        timerRef.current = null
      }
      stop()
      timerRef.current = window.setInterval(() => {
        ticks += 1
        void read(sessionId)
          .then((s) => {
            const status = String((s as { status?: string }).status ?? '')
            const message = String((s as { message?: string }).message ?? (s as { error_message?: string }).error_message ?? '')
            const done = (s as CourtSessionOut).success === true || /fail|error|cancel|complet|done|success/i.test(status)
            setSession({ key, text: [status, message].filter(Boolean).join(' · ') || '运行中…', running: !done })
            if (done || ticks > 90) stop()
          })
          .catch((e) => {
            setSession({ key, text: errMessage(e, '查询进度失败'), running: false })
            stop()
          })
      }, 2000)
    },
    [],
  )

  const run = async (key: string, start: () => Promise<CourtSessionOut>, read: (id: number) => Promise<CourtSessionOut>) => {
    setSession({ key, text: '正在提交…', running: true })
    try {
      const res = await start()
      if (res.session_id != null) {
        setSession({ key, text: [res.status, res.message].filter(Boolean).join(' · ') || '已提交，正在执行…', running: true })
        poll(key, res.session_id, read)
      } else {
        setSession({ key, text: res.message || (res.success ? '已完成' : '未启动'), running: false })
      }
    } catch (e) {
      setSession({ key, text: errMessage(e, '提交失败'), running: false })
    }
  }

  const [archiveAsk, setArchiveAsk] = useState(false)
  const [archiving, setArchiving] = useState(false)

  const filing = filingQ.data
  const guarantee = guaranteeQ.data
  const oaConfig = oaQ.data?.[0]
  const checklist = archiveQ.data
  const required = checklist?.items.filter((i) => i.required) ?? []
  const missing = required.filter((i) => !i.completed)
  const archiveReady = checklist != null && missing.length === 0

  const statusOf = (key: string) => (session?.key === key ? session : null)

  return (
    <Sheet open={open} onOpenChange={(v) => !v && onClose()}>
      <SheetContent className="w-[520px] max-w-[94vw]">
        <SheetHeader>
          <SheetTitle>办理 · {caseLabel}</SheetTitle>
        </SheetHeader>
        <SheetBody>
          <p className="mb-3 text-[11.5px] leading-relaxed text-muted-foreground">
            下面四项都会真的提交到法院 / OA / 保险公司，不是演练。缺凭证或材料不齐时按钮会禁用，原因写在旁边。
          </p>

          <div className="flex flex-col divide-y divide-border-light">
            {/* ① 一张网立案 */}
            <ActionRow
              title="一张网立案"
              status={
                filingQ.isPending
                  ? '读取中…'
                  : filingQ.isError
                    ? '立案信息读取失败'
                    : filing
                      ? [
                          filing.has_court_credential ? '法院账号已配' : '缺法院账号',
                          filing.court_name,
                          filing.has_http_plugin ? '插件可用' : '仅浏览器自动化',
                        ].filter(Boolean).join(' · ')
                      : ''
              }
              disabled={!filing?.has_court_credential || filingQ.isError}
              hint={!filing?.has_court_credential && filing ? '先去设置里配一张网法院账号' : undefined}
              actionText="开始立案"
              run={statusOf('filing')}
              onRun={() =>
                void run('filing', () => startFiling({ caseId }), (id) => getFilingSession(id))
              }
            />

            {/* ② 申请担保 */}
            <ActionRow
              title="申请担保"
              status={
                guaranteeQ.isPending
                  ? '读取中…'
                  : guaranteeQ.isError
                    ? '担保信息读取失败'
                    : guarantee
                      ? [
                          guarantee.preserve_category,
                          guarantee.has_case_number ? '已有案号' : '无案号（诉前保全）',
                          guarantee.insurance_company_name,
                        ].filter(Boolean).join(' · ')
                      : ''
              }
              disabled={!guarantee?.has_court_credential || guaranteeQ.isError}
              hint={!guarantee?.has_court_credential && guarantee ? '缺法院账号' : undefined}
              actionText="申请担保"
              run={statusOf('guarantee')}
              onRun={() =>
                void run('guarantee', () => startGuarantee({ caseId }), (id) => getGuaranteeSession(id))
              }
            />

            {/* ③ OA 立案（合同级） */}
            <ActionRow
              title="OA 立案"
              status={
                oaQ.isPending
                  ? '读取中…'
                  : oaQ.isError
                    ? 'OA 配置读取失败'
                    : oaConfig
                      ? [oaConfig.oa_system_name, oaConfig.has_credential ? '凭证已配' : '缺凭证'].join(' · ')
                      : '没有可用的 OA'
              }
              disabled={!oaConfig?.has_credential}
              hint={oaConfig && !oaConfig.has_credential ? '先去设置里配 OA 凭证' : undefined}
              actionText="提交 OA"
              run={statusOf('oa')}
              onRun={() =>
                void (async () => {
                  if (!oaConfig) return
                  setSession({ key: 'oa', text: '正在提交…', running: true })
                  try {
                    const res = await startOaFiling({ siteName: oaConfig.id, contractId, caseId })
                    setSession({ key: 'oa', text: res.status + (res.error_message ? ' · ' + res.error_message : ''), running: true })
                    poll('oa', res.id, (id) => getOaFilingSession(id))
                  } catch (e) {
                    setSession({ key: 'oa', text: errMessage(e, '提交失败'), running: false })
                  }
                })()
              }
            />

            {/* ④ 项目归档（合同级） */}
            <ActionRow
              title="项目归档"
              status={
                archiveQ.isPending
                  ? '读取中…'
                  : archiveQ.isError
                    ? '归档清单读取失败'
                    : checklist
                      ? `案卷清单 ${required.length - missing.length}/${required.length} 齐备` +
                        (missing.length ? `（缺：${missing.slice(0, 3).map((m) => m.name).join('、')}${missing.length > 3 ? '…' : ''}）` : '')
                      : ''
              }
              disabled={!archiveReady || archiving}
              hint={
                checklist && !archiveReady
                  ? '必填案卷没齐；归档会连同该项目所有在办案件一起结案'
                  : '归档 = 项目状态改为已归档，在办案件一并结案（不可逆）'
              }
              actionText="归档项目"
              run={archiving ? { text: '正在归档…', running: true } : null}
              onRun={() => setArchiveAsk(true)}
            />
          </div>

          <p className="mt-4 flex items-center gap-1 text-[11px] text-muted-foreground/70">
            <ExternalLink className="size-3" />
            立案 / 担保在后台开浏览器跑，几十秒到几分钟；可以关掉抽屉，回来在这里看结果。
          </p>
        </SheetBody>
      </SheetContent>

      <AlertDialog open={archiveAsk} onOpenChange={(v) => !v && setArchiveAsk(false)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认归档这个项目？</AlertDialogTitle>
            <AlertDialogDescription>
              归档会把项目状态改成「已归档」，该项目下所有在办案件会一并结案；改回「在办」不会自动重开。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                setArchiveAsk(false)
                setArchiving(true)
                void archiveContract(contractId)
                  .then(() => {
                    toast.success('项目已归档')
                    refetchContractAndCases(qc, contractId)
                    void qc.invalidateQueries({ queryKey: ['workbench', 'archive-checklist', contractId] })
                    onChanged()
                    onClose()
                  })
                  .catch((e) => toast.error(errMessage(e, '归档失败'), { duration: 8000 }))
                  .finally(() => setArchiving(false))
              }}
            >
              确认归档
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Sheet>
  )
}

/** 一行：标题 + 就绪状态 + 一个主按钮；运行中就地把后端原话贴出来 */
function ActionRow({
  title,
  status,
  hint,
  actionText,
  disabled,
  run,
  onRun,
}: {
  title: string
  status: string
  hint?: string
  actionText: string
  disabled?: boolean
  run: { text: string; running: boolean } | null
  onRun: () => void
}) {
  return (
    <div className="flex flex-col gap-1.5 py-3">
      <div className="flex items-center gap-2">
        <span className="text-[13px] font-[640]">{title}</span>
        <Button
          size="sm"
          className="ml-auto h-[26px] px-2.5 text-[11.5px]"
          disabled={disabled || run?.running}
          onClick={onRun}
        >
          {run?.running && <Loader2 className="mr-1 size-3 animate-spin" />}
          {actionText}
        </Button>
      </div>
      {status && <span className="text-[11.5px] text-muted-foreground">{status}</span>}
      {hint && <span className="text-[11px] text-muted-foreground/70">{hint}</span>}
      {run && (
        <span className={run.running ? 'text-[11.5px] text-status-blue' : 'text-[11.5px] text-secondary-foreground'}>
          {run.text}
        </span>
      )}
    </div>
  )
}
