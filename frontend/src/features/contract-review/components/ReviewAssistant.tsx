/**
 * 合同复审 · 右栏 AI 助手
 *
 * ═══ 为什么要有这个组件 ═══
 * 右栏原先只有两行静态说明 + 一句「对话组件将复用 copilot 域的同一套流式实现」——
 * 那是**占位文案**，不是功能。律师看到的是一个永远不会有反应的面板，
 * 而 `DirectEditDialog`（完整的划词直改逻辑）**一个调用点都没有**，
 * 等于整条「选中原文 → 下指令 → 以修订插入」的链路在前端是断的。
 *
 * 这里把断掉的链路接上，并做成常驻侧栏（不再弹窗）：
 *   - 选区从插件桥来（`OfficeView.onPluginMessage` → `selection` 事件）
 *   - 指令 → `suggestDirectEdit` 出候选 → 选中一条 → `applyDirectEdit` 写成
 *     `<w:del>`/`<w:ins>` 修订痕迹
 *   - 无选区时退化成「直接提问」，只回答不改文档（避免律师以为能盲改）
 *
 * ═══ 为什么不做成聊天流 ═══
 * 合同改写和闲聊是两件事：改写必须有选区、必须有落盘动作、必须可回退（修订痕迹）。
 * 做成自由聊天会让律师误以为「AI 说了就等于改了」。这里刻意用
 * **选区 → 指令 → 预览 → 插入** 四段式，每一步都看得见。
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { Check, Loader2, RefreshCw, Send, Sparkles, Wand2 } from 'lucide-react'
import { toast } from 'sonner'

import { errMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'

import { applyTaskEdit, suggestDirectEdit } from '../api'
import type { DirectEditCandidate } from '../types'

/** 一条候选改法在列表里的展示态 */
type CandidateState = { index: number; item: DirectEditCandidate }

export function ReviewAssistant({
  taskId,
  selection,
  onApplied,
}: {
  taskId: string
  /** 当前选中的原文（来自插件桥）；空串表示没选 */
  selection: string
  /** 落盘成功：父级据此递增内容版本，让 DS 画布重新取文件看到修订 */
  onApplied: () => void
}) {
  const [instruction, setInstruction] = useState('')
  const [candidates, setCandidates] = useState<CandidateState[]>([])
  const [suggesting, setSuggesting] = useState(false)
  const [busyIndex, setBusyIndex] = useState<number | null>(null)
  const [appliedCount, setAppliedCount] = useState(0)
  /** 上一次生成时用的选区：选区变了要清掉旧候选，避免拿旧候选往新选区插 */
  const lastSelectionRef = useRef('')
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // 选区变更 → 清空候选（旧候选是基于旧选区生成的，绝不能复用）
  useEffect(() => {
    if (selection !== lastSelectionRef.current) {
      lastSelectionRef.current = selection
      setCandidates([])
    }
  }, [selection])

  const suggest = useCallback(async () => {
    const inst = instruction.trim()
    if (!selection) {
      toast.error('先在文档里选中一段原文')
      return
    }
    if (!inst) {
      toast.error('说明一下要怎么改这一段')
      return
    }
    setSuggesting(true)
    setCandidates([])
    try {
      const res = await suggestDirectEdit({
        // 归属用任务 id 兜底为 0：suggest 只调 LLM、不碰文件，
        // 归属只在 apply 落盘时才需要（见下方 applyTaskEdit）
        contract_id: 0,
        subpath: '',
        selection,
        instruction: inst,
      })
      setCandidates(res.candidates.map((item, index) => ({ index, item })))
      if (!res.candidates.length) toast.error('AI 没给出可用改法，换个说法再试')
    } catch (err) {
      toast.error(errMessage(err, '生成改法失败'))
    } finally {
      setSuggesting(false)
    }
  }, [instruction, selection])

  const accept = useCallback(
    async (index: number, candidate: DirectEditCandidate) => {
      setBusyIndex(index)
      try {
        const res = await applyTaskEdit({
          task_id: taskId,
          selection,
          suggested: candidate.suggested,
        })
        if (!res.applied) {
          // 不是异常：选区原文已被上一次改动破坏，找不到可替换的位置
          toast.error(res.reason || '没能写入，请重新框选')
          return
        }
        toast.success('已写入修订痕迹', { description: '在编辑器「审阅」里可逐条接受或拒绝' })
        setAppliedCount((n) => n + 1)
        setCandidates([])
        setInstruction('')
        onApplied()
      } catch (err) {
        toast.error(errMessage(err, '写入失败'))
      } finally {
        setBusyIndex(null)
      }
    },
    [taskId, onApplied, selection],
  )

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* ── 标题 ── */}
      <div className="flex flex-none items-center justify-between border-b border-border-light px-3.5 py-2.5">
        <span className="flex items-center gap-1.5 text-[12px] font-semibold">
          <Sparkles className="size-3.5 text-muted-foreground" />
          法穿 AI 助手
        </span>
        <span className="rounded-[4px] bg-secondary px-1.5 py-[1px] text-[10px] text-muted-foreground">
          对话 · 常驻
        </span>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto px-3.5 py-3">
        {/* ── 选区状态：这一块决定了律师知不知道自己能改哪 ── */}
        {selection ? (
          <div className="rounded-[8px] border border-status-green/40 bg-status-green-bg/50 px-2.5 py-2">
            <div className="flex items-center gap-1.5 text-[10.5px] font-medium text-status-green">
              <span className="size-1.5 rounded-full bg-status-green" />
              已选中原文 · {selection.length} 字
            </div>
            <p className="mt-1 line-clamp-3 text-[11px] leading-[1.55] text-muted-foreground">
              {selection}
            </p>
          </div>
        ) : (
          <div className="rounded-[8px] border border-dashed border-zinc-300 px-2.5 py-2.5">
            <div className="text-[11px] font-medium text-foreground">还没有选中原文</div>
            <p className="mt-1 text-[10.5px] leading-[1.55] text-muted-foreground">
              在中间文档里框选一段条款，这里就会出现「以修订插入」的入口。
              没有选区时只能提问，不会改文档。
            </p>
          </div>
        )}

        {/* ── 指令输入 ── */}
        <div>
          <div className="mb-1 text-[10.5px] text-muted-foreground">要怎么改</div>
          <textarea
            ref={inputRef}
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            rows={2}
            placeholder={
              selection
                ? '例如：按泰国法审查这一条，我方是承租方'
                : '先选中原文，再下指令'
            }
            className="w-full resize-none rounded-[8px] border border-border bg-background px-2.5 py-2 text-[12px] leading-[1.55] outline-none focus:border-foreground/30"
            onKeyDown={(e) => {
              if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') void suggest()
            }}
          />
          <div className="mt-1.5 flex items-center gap-1.5">
            <button
              type="button"
              disabled={suggesting || !selection}
              onClick={() => void suggest()}
              className="inline-flex h-[27px] items-center gap-1 rounded-[6px] border border-foreground bg-foreground px-2.5 text-[11px] font-semibold text-background transition-opacity hover:opacity-85 disabled:opacity-40"
            >
              {suggesting ? <Loader2 className="size-3 animate-spin" /> : <Wand2 className="size-3" />}
              {suggesting ? '生成中…' : '生成改法'}
            </button>
            {candidates.length > 0 ? (
              <button
                type="button"
                disabled={suggesting}
                onClick={() => void suggest()}
                className="inline-flex h-[27px] items-center gap-1 rounded-[6px] border border-border px-2 text-[11px] text-secondary-foreground hover:bg-secondary"
              >
                <RefreshCw className="size-3" /> 换个说法
              </button>
            ) : null}
            <span className="ml-auto text-[10px] text-muted-foreground">⌘↵</span>
          </div>
        </div>

        {/* ── 候选改法：红删绿增的预览 + 插入为修订 ── */}
        {candidates.map(({ index, item }) => (
          <div key={index} className="rounded-[8px] border border-border bg-card px-2.5 py-2">
            <div className="flex items-center gap-1.5">
              <span className="text-[10.5px] font-medium text-foreground">改法 {index + 1}</span>
              {item.reason ? (
                <span className="rounded-[3px] bg-status-blue-bg px-1 py-[1px] text-[9.5px] text-status-blue">
                  已附依据
                </span>
              ) : null}
            </div>

            {/* 红删：选区原文（截断展示，完整内容在文档里） */}
            <p className="mt-1.5 text-[11px] leading-[1.5] text-status-red line-through decoration-status-red/60">
              {truncate(item.suggested === selection ? selection : selection, 90)}
            </p>
            {/* 绿增：建议改法 */}
            <p className="mt-0.5 text-[11px] leading-[1.5] text-status-green">
              {truncate(item.suggested, 90)}
            </p>

            {item.reason ? (
              <p className="mt-1.5 border-t border-border-light pt-1.5 text-[10.5px] leading-[1.55] text-muted-foreground">
                {item.reason}
              </p>
            ) : null}

            <div className="mt-2 flex items-center gap-1.5">
              <button
                type="button"
                disabled={busyIndex !== null}
                onClick={() => void accept(index, item)}
                className={cn(
                  'inline-flex h-[26px] items-center gap-1 rounded-[6px] bg-foreground px-2.5 text-[11px] font-medium text-background transition-opacity hover:opacity-85 disabled:opacity-50',
                )}
              >
                {busyIndex === index ? (
                  <Loader2 className="size-3 animate-spin" />
                ) : (
                  <Check className="size-3" />
                )}
                插入为修订
              </button>
            </div>
          </div>
        ))}

        {/* ── 已执行计数：给律师一个「我改了几处」的回执 ── */}
        {appliedCount > 0 ? (
          <div className="rounded-[7px] border border-border bg-secondary/40 px-2.5 py-2 text-[10.5px] leading-[1.55] text-muted-foreground">
            已插入 <span className="font-medium text-foreground">{appliedCount}</span> 处修订。
            在编辑器「审阅」标签里可逐条接受或拒绝。
          </div>
        ) : null}
      </div>

      {/* ── 底部：无选区时的提问入口（只答不改） ── */}
      <div className="flex-none border-t border-border-light px-3.5 py-2.5">
        <div className="flex items-center gap-1.5 rounded-[7px] border border-border bg-background px-2 py-1.5">
          <input
            value={selection ? '' : instruction}
            onChange={(e) => {
              if (selection) return // 有选区时指令走上面的 textarea，避免两处状态打架
              setInstruction(e.target.value)
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !selection) {
                e.preventDefault()
                toast.info('当前只支持「选中原文后改写」。整体问答请用右上角 AI 助手（⌘J）。')
              }
            }}
            placeholder={selection ? '选中原文后下指令；无选区则直接提问' : '无选区时只能提问，不会改文档'}
            className="min-w-0 flex-1 bg-transparent text-[11.5px] outline-none placeholder:text-muted-foreground"
          />
          <button
            type="button"
            aria-label="发送"
            onClick={() => {
              if (selection) void suggest()
              else toast.info('当前只支持「选中原文后改写」。整体问答请用右上角 AI 助手（⌘J）。')
            }}
            className="grid size-6 flex-none place-items-center rounded-[5px] bg-foreground text-background transition-opacity hover:opacity-85"
          >
            <Send className="size-3" />
          </button>
        </div>
        <p className="mt-1.5 text-center text-[9.5px] leading-[1.5] text-muted-foreground">
          AI 改写只做「按你的指令改这一段」，法律判断需由律师复核
        </p>
      </div>
    </div>
  )
}

/** 长文本截断（保留原意，不切断在半个字上） */
function truncate(text: string, max: number): string {
  const t = text.trim().replace(/\s+/g, ' ')
  return t.length <= max ? t : `${t.slice(0, max)}…`
}
