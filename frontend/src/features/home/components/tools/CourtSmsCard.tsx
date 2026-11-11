import { useState } from 'react'
import { History, MessageSquare } from 'lucide-react'
import { toast } from 'sonner'

import { cn } from '@/lib/utils'

import { BTN_PRIMARY, FIELD } from '../../ui'
import { Spinner, ToolShell } from './shared'
import { CourtSmsFlowDialog } from './court-sms/CourtSmsFlowDialog'
import { CourtSmsHistoryDialog } from './court-sms/CourtSmsHistoryDialog'
import { MaterialDropZone } from './court-sms/MaterialDropZone'
import { useCourtSms } from './court-sms/use-court-sms'

/** 两个来源（法院短信 / 客户转交材料）共用一张卡，切换用顶部分段控件 */
type CardMode = 'sms' | 'material'

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

/** 分段控件：两种入口切换（法院短信 / 客户材料） */
function ModeTabs({ mode, onChange, disabled }: { mode: CardMode; onChange: (m: CardMode) => void; disabled: boolean }) {
  const tabs: { key: CardMode; label: string }[] = [
    { key: 'sms', label: '法院短信' },
    { key: 'material', label: '客户材料' },
  ]
  return (
    <div role="tablist" aria-label="材料来源" className="flex gap-1 rounded-[7px] bg-secondary/60 p-[3px]">
      {tabs.map((t) => (
        <button
          key={t.key}
          type="button"
          role="tab"
          aria-selected={mode === t.key}
          disabled={disabled}
          onClick={() => onChange(t.key)}
          className={cn(
            'flex-1 rounded-[5px] px-2 py-[3px] text-[10.5px] font-medium transition-colors',
            mode === t.key ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground',
            disabled && 'cursor-not-allowed opacity-60',
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}

/**
 * 收法院短信 / 客户转交材料：提交后弹窗接管全流程——动画步进跟踪后端处理，
 * 匹配不到案件可在线人工分配，完成后直接下载已重命名文书。
 *
 * 两个入口共用同一套后端链路与弹窗（解析 → 匹配 → 重命名归档 → 通知）：
 * - 法院短信：粘贴短信原文，后端解析下载链接并抓取文书；
 * - 客户材料：客户先收到材料再微信转给律师的场景，拖入多个文件直接走后续流程
 *   （无下载链接时后端自动跳过下载阶段）。
 */
export function CourtSmsCard() {
  const [mode, setMode] = useState<CardMode>('sms')
  const [text, setText] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [note, setNote] = useState('')
  const [dialogOpen, setDialogOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const flow = useCourtSms()

  const busy = flow.phase === 'submitting' || flow.phase === 'processing'
  const flowActive = flow.phase !== 'idle'

  const submitSms = async () => {
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

  const submitMaterials = async () => {
    if (files.length === 0) {
      toast.info('先拖入或选择案件材料')
      return
    }
    const ok = await flow.submitFiles(files, note)
    if (ok) {
      setFiles([])
      setNote('')
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
        <ModeTabs mode={mode} onChange={setMode} disabled={busy} />

        {mode === 'sms' ? (
          <textarea
            className={FIELD + ' resize-none leading-[1.5]'}
            rows={3}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="粘贴短信全文，如：某某区人民法院：张某诉李某民间借贷纠纷案定于9月29日9时30分开庭…"
          />
        ) : (
          <>
            <MaterialDropZone files={files} onFilesChange={setFiles} disabled={busy} />
            <input
              className={FIELD}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="备注（可选），如：客户微信转来的判决书"
              disabled={busy}
            />
          </>
        )}

        <div className="mt-auto flex flex-wrap items-center gap-2">
          <button
            type="button"
            className={BTN_PRIMARY}
            onClick={() => { void (mode === 'sms' ? submitSms() : submitMaterials()) }}
            disabled={busy}
          >
            {busy && <Spinner />}
            {busy ? '处理中' : mode === 'sms' ? '提交短信' : '提交材料'}
          </button>
          {flowActive && !dialogOpen && (
            <button type="button" className={BTN_REOPEN} onClick={openFlow}>
              <span className="truncate">{reopenLabel(flow.phase, flow.outcome)}</span>
            </button>
          )}
          {!flowActive && (
            <span className="flex-1 truncate text-right text-[10.5px] text-muted-foreground">
              {mode === 'sms' ? '提交后弹窗跟进全流程' : '与短信同一套归档流程'}
            </span>
          )}
        </div>
      </div>

      <CourtSmsFlowDialog open={dialogOpen} onOpenChange={setDialogOpen} flow={flow} />
      <CourtSmsHistoryDialog open={historyOpen} onOpenChange={setHistoryOpen} onPick={pickHistory} />
    </ToolShell>
  )
}
