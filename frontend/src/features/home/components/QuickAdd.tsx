import { Suspense, useRef, useState } from 'react'
import { Loader2, Paperclip, Sparkles, X } from 'lucide-react'
import { toast } from 'sonner'

import { createReminder, parseReminder } from '../api'
import { BTN_PRIMARY } from '../ui'
import { fileFromClipboard } from '@/lib/clipboard-file'
import {
  fileRejectReason,
  preloadRecognizeDialog,
  rowsFromParsed,
  RecognizeDialogLazy,
  type CandidateRow,
} from '@/features/document-recognition'
import { errMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'

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
          // min-w 用 min(320px,100%)：宽度够时保住 320px 让它整行占位（父级 flex-wrap 会把它
          // 折到第二行），净宽不足 320px 时（AI 助手并排拉宽、分屏）就缩到容器宽——
          // 写死 320px 会让整行溢出到容器外，行尾的「记一笔」被右下方的助手面板盖住看不见。
          'flex h-[42px] min-w-[min(320px,100%)] max-w-[480px] flex-1 items-center gap-[7px] rounded-[11px] border border-input bg-card py-0 pr-[5px] pl-[13px] shadow-[0_1px_2px_rgba(0,0,0,.03)] transition-colors focus-within:border-ring/40 @min-[700px]:ml-auto',
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
