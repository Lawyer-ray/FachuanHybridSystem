import { useState } from 'react'
import { History, MessageSquare } from 'lucide-react'
import { toast } from 'sonner'

import { TOOL_ENDPOINT } from '../../constants'
import { BTN_PRIMARY, FIELD } from '../../ui'
import { Spinner, ToolShell } from './shared'
import { CourtSmsFlowDialog } from './court-sms/CourtSmsFlowDialog'
import { CourtSmsHistoryDialog } from './court-sms/CourtSmsHistoryDialog'
import { useCourtSms } from './court-sms/use-court-sms'

/** 流程进行中/结束后，卡片上的「重开弹窗」入口文案（卡片窄，超长会被截断，别写长句） */
function reopenLabel(phase: string, outcome: string | null): string {
  if (phase === 'processing' || phase === 'submitting') return '处理中 · 查看'
  if (phase === 'timeout') return '后台运行 · 查看'
  if (outcome === 'completed') return '已完成 · 查看'
  if (outcome === 'manual') return '待分配案件 · 查看'
  return '处理失败 · 查看'
}

/** 重开入口按钮：占满剩余宽度、可收缩截断，绝不把卡片撑爆 */
const BTN_REOPEN =
  'flex h-[30px] min-w-0 flex-1 items-center justify-center rounded-[7px] border border-border bg-transparent px-[10px] text-[12px] font-medium text-secondary-foreground transition-colors hover:bg-secondary hover:text-foreground hover:border-zinc-300'

/**
 * 收法院短信：提交后弹窗接管全流程——动画步进跟踪后端处理，
 * 匹配不到案件可在线人工分配，完成后直接下载已重命名文书。
 * 关掉弹窗流程照跑（轮询挂在 hook 上），卡片入口可随时重开。
 */
export function CourtSmsCard() {
  const [text, setText] = useState('')
  const [dialogOpen, setDialogOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
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

  const openFlow = () => {
    setDialogOpen(true)
    // 弹窗关着时后端可能已推进（人工分配被处理 / 自动匹配成功），重开时刷新一次
    if (flow.phase === 'done' || flow.phase === 'timeout') void flow.refresh()
  }

  /** 历史列表点某条 → 关历史，处理弹窗直接跟进该记录（人工分配/重试/下载/复制都可用） */
  const pickHistory = (smsId: number) => {
    setHistoryOpen(false)
    flow.openExisting(smsId)
    setDialogOpen(true)
  }

  return (
    <ToolShell
      icon={<MessageSquare className="h-3.5 w-3.5" />}
      title="收法院短信"
      endpoint={TOOL_ENDPOINT.courtSms}
      headerExtra={
        <button
          type="button"
          title="历史短信记录"
          className="flex h-[26px] flex-none items-center gap-1 rounded-[7px] border border-border bg-card px-2 text-[10.5px] font-medium text-secondary-foreground transition-colors hover:bg-secondary hover:text-foreground"
          onClick={() => setHistoryOpen(true)}
        >
          <History className="h-3 w-3" />
          历史
        </button>
      }
    >
      <div className="flex flex-1 flex-col gap-[7px]">
        <textarea
          className={FIELD + ' resize-none leading-[1.5]'}
          rows={3}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="粘贴短信全文，如：某某区人民法院：张某诉李某民间借贷纠纷案定于9月29日9时30分开庭…"
        />
        <div className="mt-auto flex flex-wrap items-center gap-2">
          <button type="button" className={BTN_PRIMARY} onClick={submit} disabled={busy}>
            {busy && <Spinner />}
            {busy ? '处理中' : '提交短信'}
          </button>
          {flowActive && !dialogOpen && (
            <button type="button" className={BTN_REOPEN} onClick={openFlow}>
              <span className="truncate">{reopenLabel(flow.phase, flow.outcome)}</span>
            </button>
          )}
          {!flowActive && (
            <span className="flex-1 truncate text-right text-[10.5px] text-muted-foreground">提交后弹窗跟进全流程</span>
          )}
        </div>
      </div>

      <CourtSmsFlowDialog open={dialogOpen} onOpenChange={setDialogOpen} flow={flow} />
      <CourtSmsHistoryDialog open={historyOpen} onOpenChange={setHistoryOpen} onPick={pickHistory} />
    </ToolShell>
  )
}
