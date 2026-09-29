import { Copy, Loader2, MessageSquare, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { toast } from 'sonner'

import { courtSmsDownloadAllUrl, triggerDownload, type CourtSmsDetail } from '../../../api'
import { BTN, BTN_DANGER, BTN_PRIMARY } from '../../../ui'
import { FlowNotice, TaskFlowDialog, type FlowTone } from '../dialog/TaskFlowDialog'
import { StageSteps } from '../dialog/StageSteps'
import { StageStrip } from '../dialog/StageStrip'
import { CaseAssignPicker } from './CaseAssignPicker'
import { copyAllDocFiles } from './copy-files'
import { SMS_STAGES, SMS_STATUS_LABEL } from './stages'
import { SmsSuccessBody } from './SmsSuccessBody'
import { stageForDisplay, type UseCourtSmsResult } from './use-court-sms'

/** phase/outcome → 弹窗基调 */
function toneOf(flow: UseCourtSmsResult): FlowTone {
  if (flow.phase === 'done') {
    if (flow.outcome === 'completed') return 'success'
    if (flow.outcome === 'manual') return 'manual'
    return 'error'
  }
  if (flow.phase === 'timeout') return 'timeout'
  return 'running'
}

/** 处理中弹窗的错误提示：下载失败等待自动重试 / 爬虫层退避重试中带出的具体报错 */
function runningNotice(detail: CourtSmsDetail | null): { kind: 'warn' | 'error'; text: string } | null {
  if (!detail) return null
  if (detail.status === 'download_failed') {
    return {
      kind: 'warn',
      text: `文书下载失败：${detail.error_message || '未知原因'}。约 1 分钟后自动重试（第 ${Math.min(detail.retry_count + 1, 3)}/3 次），急用可停止并删除后重新提交。`,
    }
  }
  if (detail.status === 'downloading' && detail.download_task_error) {
    return {
      kind: 'warn',
      text: `下载进程出错，正在自动重试：${detail.download_task_error}`,
    }
  }
  return null
}

/** 等待超时弹窗的错误提示：卡住时把已知的报错亮出来，别让用户干等 */
function timeoutNotice(detail: CourtSmsDetail | null): { kind: 'error'; text: string } | null {
  const err = detail?.error_message || detail?.download_task_error
  return err ? { kind: 'error', text: `后台处理异常：${err}` } : null
}

/**
 * 法院短信处理弹窗：提交后打开，动画步进展示「解析→下载→匹配→重命名→通知」；
 * 走到终态给二次操作——成功可逐件/打包下载已重命名文书、查看详情；
 * 匹配不到案件时在线人工分配；失败可一键重试。
 */
export function CourtSmsFlowDialog({
  open,
  onOpenChange,
  flow,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  flow: UseCourtSmsResult
}) {
  const tone = toneOf(flow)
  const detail = flow.detail
  const steps = stageForDisplay(detail, flow.stage)
  const canRetry = flow.smsId !== null && !flow.submitError
  const canAbort = canRetry && (tone === 'running' || tone === 'timeout' || tone === 'error')
  const docs = detail?.documents ?? []
  const [copyAllBusy, setCopyAllBusy] = useState(false)
  const [abortArmed, setAbortArmed] = useState(false)
  const [abortBusy, setAbortBusy] = useState(false)

  // 弹窗关闭即解除「确认停止」的武装态，下次打开从头确认
  useEffect(() => {
    if (!open) setAbortArmed(false)
  }, [open])

  const onAbortClick = async () => {
    if (!abortArmed) {
      setAbortArmed(true)
      window.setTimeout(() => setAbortArmed(false), 4000)
      return
    }
    setAbortBusy(true)
    try {
      await flow.abortAndRemove()
      toast.success('已停止并删除该短信处理任务')
      onOpenChange(false)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '停止任务失败，请稍后重试')
    } finally {
      setAbortBusy(false)
      setAbortArmed(false)
    }
  }

  const copyAll = async () => {
    if (!flow.smsId || docs.length === 0) return
    setCopyAllBusy(true)
    try {
      await copyAllDocFiles(flow.smsId, docs.map((d) => d.name))
    } finally {
      setCopyAllBusy(false)
    }
  }

  const headline: Record<FlowTone, string> = {
    running: '正在处理法院短信…',
    success: '处理完成',
    error: flow.submitError ? '短信提交失败' : '处理失败',
    manual: '未匹配到案件，需要人工分配',
    timeout: '处理时间较长，后台仍在继续',
  }
  const subline: Record<FlowTone, string | undefined> = {
    running: detail ? `当前阶段：${SMS_STATUS_LABEL[detail.status] ?? detail.status}` : '已提交，正在排队解析',
    success: detail?.case ? '文书已自动重命名并归档到案件日志' : '短信已解析完成',
    error: undefined,
    manual: '短信已解析并下载文书，但无法确定所属案件——从在办案件中选择一个继续完成归档',
    timeout: '法院文书下载可能较慢；可继续等待，或停止并删除任务后重新提交',
  }

  let body: ReactNode = null
  if (tone === 'running' || tone === 'timeout') {
    const notice = tone === 'running' ? runningNotice(detail) : timeoutNotice(detail)
    body = (
      <div className="flex flex-col gap-2.5">
        <StageSteps steps={SMS_STAGES} current={steps.current} failedAt={steps.failedAt} />
        {notice && <FlowNotice kind={notice.kind}>{notice.text}</FlowNotice>}
      </div>
    )
  } else if (tone === 'success' && detail) {
    body = <SmsSuccessBody detail={detail} />
  } else if (tone === 'error') {
    body = (
      <div className="flex flex-col gap-2.5">
        <StageStrip steps={SMS_STAGES} current={steps.current} failedAt={steps.failedAt} />
        <FlowNotice kind="error">
          {flow.submitError || detail?.error_message || detail?.download_task_error || '处理失败，可重试或稍后到后台查看'}
        </FlowNotice>
      </div>
    )
  } else if (tone === 'manual' && detail) {
    body = (
      <div className="flex flex-col gap-3">
        {/* 横向紧凑进度条：竖版步进器太占高，会把案件选择区挤到折叠线以下 */}
        <StageStrip steps={SMS_STAGES} current={steps.current} failedAt={steps.failedAt} />
        {detail.case_numbers.length > 0 && (
          <div className="rounded-[10px] border border-border bg-secondary/40 px-3 py-2 text-[11.5px] leading-relaxed text-muted-foreground">
            短信中解析到案号：<span className="font-semibold text-foreground">{detail.case_numbers.join('、')}</span>
            {detail.party_names.length > 0 && <>（当事人：{detail.party_names.slice(0, 4).join('、')}）</>}
          </div>
        )}
        <CaseAssignPicker
          busy={flow.actionBusy}
          onAssign={async (caseId) => {
            // 失败时 CaseAssignPicker 维持原状可重试；成功后基调切回 running 继续跟进
            await flow.assignCase(caseId)
          }}
        />
        {/* 不再放提示条：subline 已说明「指定后自动归档并发送通知」，省下的高度给候选列表 */}
      </div>
    )
  }

  return (
    <TaskFlowDialog
      open={open}
      onOpenChange={onOpenChange}
      icon={<MessageSquare className="h-5 w-5" />}
      title="收法院短信"
      tone={tone}
      headline={headline[tone]}
      subline={subline[tone]}
      wide={tone === 'success' || tone === 'manual'}
      footer={
        <>
          {tone === 'success' && docs.length > 0 && flow.smsId !== null && (
            <button type="button" className={BTN + ' mr-auto'} disabled={copyAllBusy} onClick={() => void copyAll()}>
              {copyAllBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Copy className="h-3.5 w-3.5" />}
              全部复制
            </button>
          )}
          {tone === 'success' && docs.length > 1 && flow.smsId !== null && (
            <button type="button" className={BTN_PRIMARY} onClick={() => triggerDownload(courtSmsDownloadAllUrl(flow.smsId!))}>
              打包下载 {docs.length} 件
            </button>
          )}
          {tone === 'timeout' && (
            <button type="button" className={BTN} onClick={flow.resume}>
              继续等待
            </button>
          )}
          {(tone === 'error' || tone === 'manual') && canRetry && (
            <button type="button" className={BTN} disabled={flow.actionBusy} onClick={() => void flow.retry()}>
              {tone === 'manual' ? '重新自动匹配' : '重试处理'}
            </button>
          )}
          {canAbort && (
            <button
              type="button"
              className={BTN_DANGER + ' mr-auto'}
              disabled={flow.actionBusy || abortBusy}
              onClick={() => void onAbortClick()}
            >
              {abortBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
              {abortArmed ? '确认停止并删除？' : '停止并删除'}
            </button>
          )}
          <button type="button" className={tone === 'success' || tone === 'timeout' ? BTN : BTN_PRIMARY} onClick={() => onOpenChange(false)}>
            关闭
          </button>
        </>
      }
    >
      {body}
    </TaskFlowDialog>
  )
}
