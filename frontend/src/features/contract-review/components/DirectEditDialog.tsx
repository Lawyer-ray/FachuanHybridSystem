import { useCallback, useState } from 'react'
import { Loader2, Sparkles, X } from 'lucide-react'
import { toast } from 'sonner'

import { applyDirectEdit, suggestDirectEdit } from '../api'
import type { DirectEditCandidate } from '../types'
import { DirectEditCandidates } from './DirectEditCandidates'

/**
 * 划词直改对话框：框选条款 → 说一句怎么改 → 挑一个改法 → 以修订痕迹写入。
 *
 * **与「AI 审查」的区别**（这是产品上最容易混淆的两件事）：
 * - AI 审查：整份合同跑流水线，AI 自己找问题、询立场、出风险清单与评估报告；
 * - 这里：**律师已经框定了范围、已经说出了意图**，AI 只负责按指令改写这一段。
 *
 * 所以本组件不询问立场、不显示风险等级、不生成报告——多一个环节都是多余的。
 *
 * **为什么选区不能在这里拿**：选区只存在于 OnlyOffice 内核上下文，外面拿不到
 * （`OfficeView` 注释里有实测结论）。选区由插件桥送来，这里只负责消费。
 */
export function DirectEditDialog({
  selection,
  contractId,
  subpath,
  onClose,
  onApplied,
}: {
  selection: string
  contractId: number
  subpath: string
  onClose: () => void
  /** 落盘成功：父级据此让编辑器重载内容（DS 画布需重新取文件才看得到修订） */
  onApplied: () => void
}) {
  const [instruction, setInstruction] = useState('')
  const [candidates, setCandidates] = useState<DirectEditCandidate[]>([])
  const [suggesting, setSuggesting] = useState(false)
  const [busyIndex, setBusyIndex] = useState<number | null>(null)

  const suggest = useCallback(async () => {
    const inst = instruction.trim()
    if (!inst) {
      toast.error('请说明要怎么改这一段')
      return
    }
    setSuggesting(true)
    setCandidates([])
    try {
      const res = await suggestDirectEdit({
        contract_id: contractId,
        subpath,
        selection,
        instruction: inst,
      })
      setCandidates(res.candidates)
      if (!res.candidates.length) toast.error('AI 没有给出可用的改法，换个说法再试')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '生成改法失败')
    } finally {
      setSuggesting(false)
    }
  }, [contractId, instruction, selection, subpath])

  const accept = useCallback(
    async (index: number, candidate: DirectEditCandidate) => {
      setBusyIndex(index)
      try {
        const res = await applyDirectEdit({ contract_id: contractId, subpath, selection, suggested: candidate.suggested })
        if (!res.applied) {
          // 不是异常：选区原文在文档里已找不到（多是被上一次改动破坏了）
          toast.error(res.reason || '没能写入，请重新框选')
          return
        }
        toast.success('已写入修订痕迹', { description: '在编辑器「审阅」里可逐条接受或拒绝' })
        onApplied()
        onClose()
      } catch (err) {
        toast.error(err instanceof Error ? err.message : '写入失败')
      } finally {
        setBusyIndex(null)
      }
    },
    [contractId, onApplied, onClose, selection, subpath],
  )

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/25 p-6" onClick={onClose}>
      <div
        className="flex max-h-[80vh] w-full max-w-[560px] flex-col overflow-hidden rounded-[12px] border border-border bg-card shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 border-b border-border-light px-4 py-2.5">
          <Sparkles className="size-3.5 text-muted-foreground" />
          <span className="flex-1 text-[13px] font-[620]">AI 改写这一段</span>
          <button
            type="button"
            aria-label="关闭"
            onClick={onClose}
            className="grid size-6 place-items-center rounded-[6px] text-muted-foreground hover:bg-secondary hover:text-foreground"
          >
            <X className="size-3.5" />
          </button>
        </div>

        <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 py-3">
          <div>
            <div className="mb-1 text-[11px] text-muted-foreground">已选中的条款</div>
            <p className="max-h-[120px] overflow-y-auto whitespace-pre-wrap rounded-[8px] bg-secondary/60 p-2 text-[12px] leading-relaxed">
              {selection}
            </p>
          </div>

          <div>
            <div className="mb-1 text-[11px] text-muted-foreground">要怎么改</div>
            <textarea
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              rows={2}
              placeholder="例如：违约金降到合同总额的 10%；或：把付款节点改到验收后 30 天"
              className="w-full resize-none rounded-[8px] border border-border bg-background px-2.5 py-2 text-[12.5px] outline-none focus:border-foreground/30"
              onKeyDown={(e) => {
                if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') void suggest()
              }}
            />
            <div className="mt-1.5 flex items-center gap-2">
              <button
                type="button"
                disabled={suggesting}
                onClick={() => void suggest()}
                className="inline-flex h-[28px] items-center gap-1 rounded-[7px] border border-foreground bg-foreground px-3 text-[11.5px] font-semibold text-background transition-opacity hover:opacity-85 disabled:opacity-50"
              >
                {suggesting ? <Loader2 className="size-3 animate-spin" /> : <Sparkles className="size-3" />}
                {suggesting ? '生成中…' : '生成改法'}
              </button>
              <span className="text-[11px] text-muted-foreground">⌘↵ 生成 · 生成多个改法由你挑</span>
            </div>
          </div>

          {candidates.length > 0 && (
            <DirectEditCandidates
              selection={selection}
              candidates={candidates}
              busyIndex={busyIndex}
              onAccept={(i, c) => void accept(i, c)}
            />
          )}
        </div>
      </div>
    </div>
  )
}
