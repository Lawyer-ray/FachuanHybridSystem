import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import { PhaseAiDesignPane, type AiDesignMessage } from './PhaseAiDesignPane'
import { PhaseDesignPane } from './PhaseDesignPane'
import type { PhaseDesignAssistant } from './special-design-assistant'
import type { PhaseNode } from './special-phase-tree'

/**
 * 设计阶段弹窗（54 号原型第十一～十二轮）：**两页签**的阶段编辑器。
 *
 * 律师设计阶段时真正在回答三个问题——分成几步（左栏主线）、每步交什么（右栏
 * 交付物 + 验收标准）、用哪个模板（模板 chip）。所以不是「改名清单」，而是
 * 左主线 / 右细节的编辑器；AI 设计页签则把整条主线交给对话。
 *
 * 尺寸：宽 960、高 82vh。620 宽会把交付物文书名截成前 8 个字（律师没法核对），
 * 左右两栏也都挤；960 刚好两侧完整可读。
 *
 * 取消 = 丢弃草稿（草稿是深拷贝）；保存 = 整树提交给调用方落库。
 */
export function PhaseDesignDialog({
  open,
  tree,
  onOpenChange,
  onSave,
  saving,
  assistant,
}: {
  open: boolean
  /** 打开时的阶段树（每次打开取最新；关弹窗再打开应接着谈，消息由调用方保留） */
  tree: PhaseNode[]
  onOpenChange: (open: boolean) => void
  onSave: (next: PhaseNode[]) => void
  saving?: boolean
  assistant?: PhaseDesignAssistant
}) {
  const [pane, setPane] = useState<'design' | 'ai'>('design')
  const [draft, setDraft] = useState<PhaseNode[]>(tree)
  const [selKey, setSelKey] = useState<string | null>(tree[0]?.key ?? null)
  const [messages, setMessages] = useState<AiDesignMessage[]>([])
  /** 本次打开是否已经把最新树 seed 进草稿（关弹窗再打开要重新起稿，但对话历史不清） */
  const [seeded, setSeeded] = useState(false)

  // 每次打开都从最新树重新起稿（草稿是副本，取消即丢弃）。effect 里 seed 而不是
  // 渲染期 —— Dialog 关闭时内容不渲染，首帧闪旧草稿的问题不存在。
  useEffect(() => {
    if (!open || seeded) return
    setDraft(tree)
    setSelKey(tree[0]?.key ?? null)
    setSeeded(true)
  }, [open, seeded, tree])

  const save = () => {
    // 剪掉没填名字的节点（加了行没填名字 = 不要这一行）
    const pruned = pruneUnnamed(draft)
    if (pruned.length === 0) {
      toast.error('至少要有一个阶段')
      return
    }
    onSave(pruned)
    setSeeded(false)
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        showCloseButton={false}
        className="flex w-[min(960px,calc(100vw-40px))] max-w-none flex-col gap-0 overflow-hidden p-0 sm:max-w-none max-[780px]:w-[calc(100vw-20px)]"
        style={{ maxHeight: '82vh' }}
      >
        <div className="flex items-baseline gap-2 px-[22px] pt-[18px] pb-3.5">
          <DialogTitle className="text-[15px] leading-none font-[680]">设计阶段</DialogTitle>
          <span className="text-[11.5px] text-muted-foreground/80">阶段即合同文件夹，改名/重排后目录名同步</span>
          <button
            type="button"
            onClick={() => {
              setSeeded(false)
              onOpenChange(false)
            }}
            title="关闭"
            className="ml-auto size-6 shrink-0 cursor-pointer rounded-[6px] text-[12px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          >
            ✕
          </button>
        </div>

        <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-[22px]">
          <div className="mb-3.5 flex items-center gap-1 border-b border-border-light pb-2.5">
            <PaneTab on={pane === 'design'} onClick={() => setPane('design')}>
              手工设计
            </PaneTab>
            <PaneTab on={pane === 'ai'} onClick={() => setPane('ai')}>
              ✦ AI 设计（对话）
            </PaneTab>
            <span className="ml-auto text-[11.5px] text-muted-foreground">
              {pane === 'ai' ? '聊一句改一处，左边草稿实时更新' : '双击阶段名可改 · →/← 调整层级'}
            </span>
          </div>

          {pane === 'design' ? (
            <PhaseDesignPane draft={draft} selKey={selKey} onChange={setDraft} onSelect={setSelKey} />
          ) : (
            <PhaseAiDesignPane
              draft={draft}
              selKey={selKey}
              messages={messages}
              onMessages={setMessages}
              onChangeDraft={setDraft}
              assistant={assistant}
            />
          )}
        </div>

        <div className="flex items-center gap-2.5 px-[22px] pt-3 pb-[18px]">
          <span className="text-[11.5px] leading-[1.6] text-muted-foreground/80">
            保存后回到阶段表：设计出的交付物是「计划」，在编辑器里起草或上传后才变成实际文件。
          </span>
          <button
            type="button"
            onClick={() => {
              setSeeded(false)
              onOpenChange(false)
            }}
            className="ml-auto inline-flex h-[27px] shrink-0 cursor-pointer items-center rounded-[7px] border border-border bg-card px-2.5 text-[11.5px] font-[550] text-secondary-foreground transition-colors hover:bg-secondary"
          >
            取消
          </button>
          <button
            type="button"
            onClick={save}
            disabled={saving}
            className="inline-flex h-[27px] shrink-0 cursor-pointer items-center rounded-[7px] border border-foreground bg-foreground px-3 text-[11.5px] font-[600] text-background transition-opacity hover:opacity-85 disabled:opacity-50"
          >
            {saving ? '保存中…' : '保存阶段'}
          </button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function PaneTab({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'h-7 cursor-pointer rounded-[7px] border px-3 text-[12.5px] font-[550] transition-colors',
        on ? 'border-border bg-card text-foreground shadow-sm' : 'border-transparent text-muted-foreground hover:bg-secondary hover:text-foreground',
      )}
    >
      {children}
    </button>
  )
}

/** 剪掉名字为空的节点（递归），保住其余结构 */
function pruneUnnamed(list: PhaseNode[]): PhaseNode[] {
  return list
    .map((n) => ({ ...n, folders: pruneUnnamed(n.folders) }))
    .filter((n) => n.name.trim().length > 0)
}
