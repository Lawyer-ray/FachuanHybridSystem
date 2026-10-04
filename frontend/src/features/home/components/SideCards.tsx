import { Suspense, useRef, useState } from 'react'
import { Landmark, Loader2, Mail, Paperclip, Sparkles, X } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'

import { createReminder, listInbox, parseReminder, HOME_INBOX_KEY } from '../api'
import type { InboxItem } from '../types'
import { BTN_PRIMARY, PANEL } from '../ui'
import {
  fileRejectReason,
  preloadRecognizeDialog,
  rowsFromParsed,
  RecognizeDialogLazy,
  type CandidateRow,
} from '@/features/document-recognition'
import { errMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'
import { CardHead } from './CardHead'

/* ============================================================ 收件箱流入 */

interface InboxProps {
  onOpen: (item: InboxItem) => void
}

/**
 * 右栏「收件箱」：最近流入的消息（法院短信 / 一张网通知书 / 邮件 / 材料包）。
 *
 * 这里刻意**不**叫「待处理」、也不给每条配一个动作按钮。原因（实测数据）：
 * 收件箱 338 条里 court_inbox 121 条、imap 215 条、manual_upload 仅 2 条；
 * 而 status（todo/done/filed）只对 manual_upload 有意义——它是写在
 * draft_state 里的、由材料预处理页维护。也就是说其余 336 条的 status 恒为
 * todo，「待处理 N 条」这个计数没有信息量。
 * 更何况「归案 / 解析」这些动作目前都还没实现，摆一排点不动的按钮只是噪音。
 *
 * 所以：只做「最近流入」的信息展示，点整行进材料预处理（材料包）或提示
 * （其他来源）。等后台真做了收件箱处理流，再把状态和动作加回来。
 */
export function InboxCard({ onOpen }: InboxProps) {
  const { data = [], isLoading, isError, error, refetch } = useQuery({
    queryKey: HOME_INBOX_KEY,
    queryFn: () => listInbox(6),
    staleTime: 30_000,
  })

  return (
    <section className={`${PANEL} overflow-hidden`}>
      <CardHead title="收件箱" count={isError ? '' : data.length ? `${data.length} 条` : ''} />
      <div className="px-2.5 pt-1.5 pb-2.5">
        {isError && (
          /* 失败与空收件箱必须分得开：否则服务端故障会被读成「没有新消息」 */
          <div className="px-2 py-6 text-center text-[12.5px] text-destructive">
            {errMessage(error, '收件箱加载失败')}
            <button
              type="button"
              className="ml-1.5 cursor-pointer underline underline-offset-3"
              onClick={() => void refetch()}
            >
              重试
            </button>
          </div>
        )}
        {!isError && isLoading && <div className="px-2 py-6 text-center text-[12.5px] text-muted-foreground">正在载入…</div>}
        {!isError && !isLoading && data.length === 0 && (
          <div className="px-2 py-6 text-center text-[12.5px] text-muted-foreground">收件箱是空的</div>
        )}
        {data.map((x) => (
          <button
            key={x.id}
            type="button"
            onClick={() => onOpen(x)}
            className="flex w-full items-center gap-[11px] rounded-[10px] px-2 py-[10px] text-left transition-colors hover:bg-secondary/50"
          >
            <div
              className={cn(
                'flex h-8 w-8 flex-none items-center justify-center rounded-[9px] border',
                x.hot
                  ? 'border-status-red/30 bg-status-red-bg text-status-red'
                  : 'border-border bg-secondary text-secondary-foreground',
              )}
            >
              <KindIcon kind={x.kind} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-[12.5px] leading-[1.4] font-semibold">{x.title}</div>
              <div className="mt-[1px] truncate text-[10.5px] text-muted-foreground">
                {x.sourceLabel} · {x.who}
              </div>
            </div>
            <span className="flex-none text-[10.5px] whitespace-nowrap text-muted-foreground">{x.at}</span>
          </button>
        ))}
      </div>
    </section>
  )
}

function KindIcon({ kind }: { kind: InboxItem['kind'] }) {
  if (kind === 'sms') return <Landmark className="h-4 w-4" />
  if (kind === 'mail') return <Mail className="h-4 w-4" />
  return <Paperclip className="h-4 w-4" />
}

/* ============================================================ 快速记一笔 */

interface QuickAddProps {
  onAdded: () => void
}

/**
 * 快速记一笔：支持文字与文书文件两种输入。
 *
 * - 文字：调 /reminders/parse 抽取日期与类型，**全部**候选进确认弹窗
 *   （多日期不再只取第一个），逐条勾选后创建。
 * - 文件：📎 选择 / 拖到输入行 → 识别弹窗（案件绑定 + 日期候选确认），
 *   确认后写入重要日期提醒。文件校验在打开弹窗前完成，错误就地提示。
 */
export function QuickAdd({ onAdded }: QuickAddProps) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [textRows, setTextRows] = useState<CandidateRow[] | undefined>(undefined)
  const fileRef = useRef<HTMLInputElement>(null)

  const pickFile = (f: File | null | undefined) => {
    if (!f) return
    preloadRecognizeDialog()
    const reason = fileRejectReason(f)
    if (reason) {
      toast.warning(reason)
      return
    }
    setFile(f)
    setDialogOpen(true)
  }

  const submitText = async () => {
    if (busy) return // 回车与按钮共用防重入闸：按钮 disabled 拦不住回车
    const v = text.trim()
    if (!v) {
      toast.info('先写一句，比如「2026-09-28 09:30 开庭 张某诉李某 借贷纠纷」；也可以点 📎 上传文书')
      return
    }
    setBusy(true)
    preloadRecognizeDialog() // 解析请求期间并行下载弹窗 chunk
    try {
      const parsed = await parseReminder(v)
      if (parsed.length === 0) {
        toast.warning('没能识别出日期——请写具体日期，如「2026-09-28 09:30 开庭 …」')
        return
      }
      setTextRows(rowsFromParsed(parsed))
      setDialogOpen(true)
    } catch (e) {
      toast.error(errMessage(e, '记一笔失败，请稍后重试'))
    } finally {
      setBusy(false)
    }
  }

  // 文字路径的确认回调：逐条创建独立提醒（在 home 域内闭环，不反向依赖识别域）
  const confirmTextReminders = async (rows: CandidateRow[]): Promise<number> => {
    let created = 0
    for (const r of rows) {
      await createReminder({
        reminder_type: r.reminderType,
        content: r.content || r.contextText || r.label,
        due_at: r.dueLocal,
      })
      created++
    }
    setText('')
    setTextRows(undefined)
    return created
  }

  const closeDialog = () => {
    setDialogOpen(false)
    setFile(null)
    setTextRows(undefined)
    if (fileRef.current) fileRef.current.value = ''
  }

  const showFileChip = file !== null

  return (
    <>
      <div
        className={cn(
          'flex h-[42px] min-w-[320px] max-w-[480px] flex-1 items-center gap-[7px] rounded-[11px] border border-input bg-card py-0 pr-[5px] pl-[13px] shadow-[0_1px_2px_rgba(0,0,0,.03)] transition-colors focus-within:border-ring/40 md:ml-auto',
          dragOver && 'border-ring/60 bg-secondary/60',
        )}
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragOver(false)
          pickFile(e.dataTransfer.files?.[0])
        }}
      >
        {busy ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
        ) : showFileChip ? (
          <Paperclip className="h-3.5 w-3.5 flex-none text-muted-foreground" />
        ) : (
          <Sparkles className="h-3.5 w-3.5 text-muted-foreground" />
        )}

        {showFileChip && file ? (
          <>
            <span className="min-w-0 flex-1 truncate text-[13px]">{file.name}</span>
            <button
              type="button"
              title="移除文件"
              aria-label="移除文件"
              className="flex h-5 w-5 flex-none items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
              onClick={() => setFile(null)}
            >
              <X className="h-3 w-3" />
            </button>
          </>
        ) : (
          <input
            className="min-w-0 flex-1 border-none bg-transparent text-[13px] text-foreground outline-none placeholder:text-muted-foreground"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void submitText()
            }}
            placeholder="快速记一笔：2026-09-28 09:30 开庭 张某诉李某 借贷纠纷，或点 📎 传文书"
          />
        )}

        <input
          ref={fileRef}
          type="file"
          accept=".pdf,.jpg,.jpeg,.png"
          className="hidden"
          onChange={(e) => pickFile(e.target.files?.[0])}
        />
        <button
          type="button"
          title="上传文书识别"
          aria-label="上传文书识别"
          className="flex h-[30px] w-[30px] flex-none items-center justify-center rounded-[8px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          onClick={() => fileRef.current?.click()}
        >
          <Paperclip className="h-3.5 w-3.5" />
        </button>
        <button type="button" className={BTN_PRIMARY} onClick={showFileChip ? closeDialog : submitText} disabled={busy}>
          {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          {showFileChip ? '识别并确认' : '记一笔'}
        </button>
      </div>

      {/* 懒加载域：仅弹窗打开时挂载（open=false 常驻渲染会让首屏就拉下整个识别域） */}
      {dialogOpen && (
        <Suspense fallback={null}>
          <RecognizeDialogLazy
            open={dialogOpen}
            onClose={closeDialog}
            onSaved={onAdded}
            file={file}
            textRows={textRows}
            onConfirmText={confirmTextReminders}
          />
        </Suspense>
      )}
    </>
  )
}
