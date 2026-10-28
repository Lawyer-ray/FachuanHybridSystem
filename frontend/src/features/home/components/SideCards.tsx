import { Suspense, useRef, useState } from 'react'
import { ChevronDown, Landmark, Loader2, Mail, Paperclip, Sparkles, X } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'

import { createReminder, listInbox, parseReminder, HOME_INBOX_KEY } from '../api'
import type { InboxItem } from '../types'
import { BTN_PRIMARY, PANEL } from '../ui'
import { InboxMessageContent } from '@/features/material-prep'
import { fileFromClipboard } from './clipboard-file'
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
import { inboxPath } from '@/app/paths'

/* ============================================================ 收件箱流入 */

interface InboxProps {
  /** 点击行：材料包/已转过的直接进阅读器（由页面决定怎么走） */
  onOpen: (item: InboxItem) => void
  /** 就地展开里的「转材料包并打开」走同一条路 */
  onOpenPack: (packId: number) => void
}

/**
 * 右栏「收件箱」：最近流入的消息（法院短信 / 一张网通知书 / 邮件 / 材料包）。
 *
 * 这里刻意**不**叫「待处理」、也不给每条配一排动作按钮。原因（实测数据）：
 * 收件箱 338 条里 court_inbox 121 条、imap 215 条、manual_upload 仅 2 条；
 * 而 status（todo/done/filed）只对 manual_upload 有意义——它是写在
 * draft_state 里的、由材料预处理页维护。也就是说其余 336 条的 status 恒为
 * todo，「待处理 N 条」这个计数没有信息量。
 *
 * **点击行为（2026-10 修正）**：点一行就地展开读正文/附件，**不再跳**到
 * 收件箱列表。此前非材料包类一律 navigate 到 /material-prep，用户以为在看
 * 详情，落地却是一屏 300+ 条同质消息、还得靠标题文本自己再找一遍——而法院
 * 送达里五条标题都叫「Attached Image」时根本无法肉眼区分。真正要横向浏览时
 * 走右上「查看全部」。只有材料包（或已转过的消息）才直接进阅读器。
 */
export function InboxCard({ onOpen, onOpenPack }: InboxProps) {
  const { data = [], isLoading, isError, error, refetch } = useQuery({
    queryKey: HOME_INBOX_KEY,
    queryFn: () => listInbox(6),
    staleTime: 30_000,
  })

  // 手风琴：同时只展开一条（侧栏空间窄，多条展开会把下面几行顶出视口）
  const [expandedId, setExpandedId] = useState<number | null>(null)

  return (
    <section className={`${PANEL} overflow-hidden`}>
      <CardHead
        title="收件箱"
        count={isError ? '' : data.length ? `${data.length} 条` : ''}
        moreHref={inboxPath()}
      />
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
        {data.map((x) => {
          const expanded = expandedId === x.id
          return (
            <div key={x.id}>
              <button
                type="button"
                aria-expanded={expanded}
                onClick={() => {
                  // 材料包 / 已转过的消息：进去就是要看阅读器，展开再点一次是多余一层
                  if (x.packId != null) {
                    onOpen(x)
                    return
                  }
                  setExpandedId(expanded ? null : x.id)
                }}
                className={cn(
                  'flex w-full items-center gap-[11px] rounded-[10px] px-2 py-[10px] text-left transition-colors hover:bg-secondary/50',
                  expanded && 'bg-secondary/40',
                )}
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
                {/* 可展开的才给指示器：材料包可直接进阅读器，画个三角反而暗示有东西展开却打不开 */}
                {x.packId == null && (
                  <ChevronDown
                    aria-hidden
                    className={cn(
                      'h-3.5 w-3.5 flex-none text-muted-foreground transition-transform',
                      expanded && 'rotate-180',
                    )}
                  />
                )}
              </button>
              {expanded && (
                <div className="mb-1 ml-[43px] mr-2 rounded-[10px] border border-border bg-card px-3 py-2.5">
                  {/* 消息行就是 InboxMessageOut，与收件箱页抽屉同形，直接喂给它 */}
                  <InboxMessageContent row={x.row} onConverted={onOpenPack} onOpenPack={onOpenPack} />
                </div>
              )}
            </div>
          )
        })}
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
 * - 文件：📎 选择 / 拖到输入行 / ⌘V 粘贴截图（剪贴板文件经 clipboard-file
 *   按泛名补扩展名）→ 识别弹窗（案件绑定 + 日期候选确认），确认后写入
 *   重要日期提醒。文件校验在打开弹窗前完成，错误就地提示。
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
      toast.info('先写一句，比如「2026-09-28 09:30 开庭 张某诉李某 借贷纠纷」；也可以粘贴截图或点 📎 上传文书')
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
    const failedKeys = new Set<string>()
    for (const r of rows) {
      try {
        await createReminder({
          reminder_type: r.reminderType,
          content: r.content || r.contextText || r.label,
          due_at: r.dueLocal,
        })
        created++
      } catch {
        failedKeys.add(r.key)
      }
    }
    // 部分成功：只移除已建好的行，失败行留在原地供用户重试。
    // 否则调用方 catch 后弹窗仍开着、行全仍是 pending，再点一次会把
    // 已成功的那些重复建一遍（D-P2-3 / H-P1-2）
    setTextRows((prev) => {
      if (!prev) return prev
      const remain = prev.filter((r) => failedKeys.has(r.key))
      return remain.length > 0 ? remain : undefined
    })
    if (failedKeys.size === 0) setText('')
    if (failedKeys.size > 0) {
      toast.warning(
        `${created} 条已加入日历，${failedKeys.size} 条未写入，可直接重试（不会重复创建）`,
      )
    }
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
          'flex h-[42px] min-w-[320px] max-w-[480px] flex-1 items-center gap-[7px] rounded-[11px] border border-input bg-card py-0 pr-[5px] pl-[13px] shadow-[0_1px_2px_rgba(0,0,0,.03)] transition-colors focus-within:border-ring/40 @min-[700px]:ml-auto',
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
        onPaste={(e) => {
          const f = fileFromClipboard(e.clipboardData)
          if (!f) return // 纯文字粘贴：交给输入框默认行为
          e.preventDefault()
          pickFile(f)
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
            placeholder="快速记一笔：2026-09-28 09:30 开庭 张某诉李某 借贷纠纷，可粘贴截图或点 📎 传文书"
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
