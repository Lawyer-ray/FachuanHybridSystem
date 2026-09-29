import { Copy, Loader2, MessageSquare } from 'lucide-react'
import { useState } from 'react'
import type { ReactNode } from 'react'

import { courtSmsDownloadAllUrl, triggerDownload } from '../../../api'
import { BTN, BTN_PRIMARY } from '../../../ui'
import { FlowNotice, TaskFlowDialog, type FlowTone } from '../dialog/TaskFlowDialog'
import { StageSteps } from '../dialog/StageSteps'
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
  const docs = detail?.documents ?? []
  const [copyAllBusy, setCopyAllBusy] = useState(false)

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
    timeout: '法院文书下载可能较慢；可关闭弹窗稍后在收件箱查看，或点击「继续等待」',
  }

  let body: ReactNode = null
  if (tone === 'running' || tone === 'timeout') {
    body = <StageSteps steps={SMS_STAGES} current={steps.current} failedAt={steps.failedAt} />
  } else if (tone === 'success' && detail) {
    body = <SmsSuccessBody detail={detail} />
  } else if (tone === 'error') {
    body = (
      <div className="flex flex-col gap-2.5">
        <StageSteps steps={SMS_STAGES} current={steps.current} failedAt={steps.failedAt} />
        <FlowNotice kind="error">{flow.submitError || detail?.error_message || '处理失败，可重试或稍后到后台查看'}</FlowNotice>
      </div>
    )
  } else if (tone === 'manual' && detail) {
    body = (
      <div className="flex flex-col gap-2.5">
        <StageSteps steps={SMS_STAGES} current={steps.current} failedAt={steps.failedAt} />
        {detail.case_numbers.length > 0 && (
          <div className="text-[11.5px] text-muted-foreground">
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
        <FlowNotice kind="warn">文书已下载并完成预重命名，指定案件后将自动归档并发送通知。</FlowNotice>
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
      wide={tone === 'success'}
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
