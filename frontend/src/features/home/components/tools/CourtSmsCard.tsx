import { useState } from 'react'
import { MessageSquare } from 'lucide-react'
import { toast } from 'sonner'

import { TOOL_ENDPOINT } from '../../constants'
import { BTN, BTN_PRIMARY, FIELD } from '../../ui'
import { Spinner, ToolShell } from './shared'
import { CourtSmsFlowDialog } from './court-sms/CourtSmsFlowDialog'
import { useCourtSms } from './court-sms/use-court-sms'

/** 流程进行中/结束后，卡片上的「重开弹窗」入口文案 */
function reopenLabel(phase: string, outcome: string | null): string {
  if (phase === 'processing' || phase === 'submitting') return '处理中 · 查看进度'
  if (phase === 'timeout') return '仍在后台 · 查看'
  if (outcome === 'completed') return '已完成 · 查看结果'
  if (outcome === 'manual') return '待人工分配案件 · 查看'
  return '处理失败 · 查看'
}

/**
 * 收法院短信：提交后弹窗接管全流程——动画步进跟踪后端处理，
 * 匹配不到案件可在线人工分配，完成后直接下载已重命名文书。
 * 关掉弹窗流程照跑（轮询挂在 hook 上），卡片入口可随时重开。
 */
export function CourtSmsCard() {
  const [text, setText] = useState('')
  const [dialogOpen, setDialogOpen] = useState(false)
  const flow = useCourtSms()

  const busy = flow.phase === 'submitting' || flow.phase === 'processing'
  const flowActive = flow.phase !== 'idle'

  const submit = async () => {
    const v = text.trim()
    if (!v) {
      toast.info('先粘贴一条法院短信')
      return
    }
    const ok = await flow.submit(v)
    if (ok) {
      setText('')
      setDialogOpen(true)
    }
  }

  return (
    <ToolShell icon={<MessageSquare className="h-3.5 w-3.5" />} title="收法院短信" endpoint={TOOL_ENDPOINT.courtSms}>
      <div className="flex flex-1 flex-col gap-[7px]">
        <textarea
          className={FIELD + ' resize-none leading-[1.5]'}
          rows={3}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="粘贴短信全文，如：某某区人民法院：张某诉李某民间借贷纠纷案定于9月29日9时30分开庭…"
        />
        <div className="mt-auto flex items-center gap-2">
          <button type="button" className={BTN_PRIMARY} onClick={submit} disabled={busy}>
            {busy && <Spinner />}
            {busy ? '处理中' : '提交短信'}
          </button>
          {flowActive && !dialogOpen && (
            <button type="button" className={BTN} onClick={() => setDialogOpen(true)}>
              {reopenLabel(flow.phase, flow.outcome)}
            </button>
          )}
          {!flowActive && <span className="flex-1 truncate text-right text-[10.5px] text-muted-foreground">提交后弹窗跟进全流程</span>}
        </div>
      </div>

      <CourtSmsFlowDialog open={dialogOpen} onOpenChange={setDialogOpen} flow={flow} />
    </ToolShell>
  )
}
