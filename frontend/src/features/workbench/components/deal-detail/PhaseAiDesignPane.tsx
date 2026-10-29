import { useEffect, useRef, useState } from 'react'

import { cn } from '@/lib/utils'
import { flattenTree, type PhaseNode } from './special-phase-tree'
import { DESIGN_GREETING, createRuleAssistant, type PhaseDesignAssistant } from './special-design-assistant'

/** 一条对话消息（AI 回复带「改了哪几处」） */
export interface AiDesignMessage {
  role: 'user' | 'ai'
  text: string
  changes: string[]
  unchanged: boolean
}

/**
 * 「✦ AI 设计（对话）」页签：左 = 活的阶段草稿，右 = 对话记录 + 输入框。
 *
 * 设计判断：阶段设计不是「AI 给一版，你接受或不要」，而是**多轮对话逐步逼近**。
 * 每一轮 AI 都要改草稿而不是重新给一份——所以左栏随每轮实时变，右栏逐条可回看，
 * 每条 AI 回复列出「改了哪几处」，让律师知道该看哪里。
 *
 * 对话历史由父级（PhaseDesignDialog）持有：关弹窗再打开能接着聊。
 * 建议器可注入：默认是确定性规则（special-design-assistant），将来换成 copilot 工具调用。
 */
export function PhaseAiDesignPane({
  draft,
  selKey,
  messages,
  onMessages,
  onChangeDraft,
  assistant = createRuleAssistant(),
}: {
  draft: PhaseNode[]
  selKey: string | null
  messages: AiDesignMessage[]
  onMessages: (next: AiDesignMessage[]) => void
  onChangeDraft: (next: PhaseNode[]) => void
  /** 可注入的设计建议器（默认确定性规则；将来接 copilot） */
  assistant?: PhaseDesignAssistant
}) {
  const [input, setInput] = useState('')
  const logRef = useRef<HTMLDivElement | null>(null)

  // 每轮/每次打开都滚到底：最后一句才是律师要看的
  useEffect(() => {
    const el = logRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages.length])

  const send = () => {
    const text = input.trim()
    if (!text) return
    const turn = assistant.suggest({ text, draft, selectedKey: selKey })
    onChangeDraft(turn.draft)
    onMessages([
      ...messages,
      { role: 'user', text, changes: [], unchanged: false },
      { role: 'ai', text: turn.reply, changes: turn.changes, unchanged: turn.unchanged },
    ])
    setInput('')
  }

  const flat = flattenTree(draft)

  return (
    <div className="grid h-[min(560px,calc(82vh-190px))] grid-cols-[260px_minmax(0,1fr)] gap-[22px] max-[780px]:h-auto max-[780px]:grid-cols-1">
      {/* 左：活的草稿 */}
      <div className="flex min-w-0 flex-col border-r border-border-light pr-[18px] max-[780px]:border-r-0 max-[780px]:border-b max-[780px]:pb-3">
        <div className="mb-2 flex items-baseline gap-2 text-[12px] font-[650] text-secondary-foreground">
          当前草稿
          <span className="text-[11px] font-[400] text-muted-foreground tabular-nums">{flat.length} 阶段</span>
        </div>
        <div className="mb-2.5 flex flex-col gap-[3px] overflow-y-auto">
          {flat.length === 0 ? (
            <div className="px-1 py-5 text-[12px] text-muted-foreground">还没有阶段</div>
          ) : (
            flat.map((item) => (
              <div
                key={item.node.key}
                className={cn(
                  'flex items-baseline gap-2 rounded-[8px] border border-border-light bg-secondary/35 px-2.5 py-[7px]',
                  item.depth === 2 && 'bg-secondary/25 pl-1.5',
                  item.depth === 3 && 'bg-secondary/45 pl-1.5',
                )}
              >
                <span className="block shrink-0" style={{ width: (item.depth - 1) * 12 }} />
                <span className="w-6 shrink-0 text-right text-[11px] text-muted-foreground tabular-nums">{item.no}</span>
                <span className="flex min-w-0 flex-1 flex-col gap-px">
                  <b className="text-[12.5px] font-[620]">{item.node.name || '未命名阶段'}</b>
                  <span className="text-[11px] text-muted-foreground tabular-nums">
                    {item.node.deliverables.length} 交付物
                    {item.node.acceptance ? ' · 有验收标准' : ' · 缺验收标准'}
                    {item.node.folders.length ? ` · ${item.node.folders.length} 子` : ''}
                  </span>
                </span>
              </div>
            ))
          )}
        </div>
        <div className="mt-auto border-t border-border-light pt-2.5 text-[11px] leading-[1.6] text-muted-foreground">
          对话每改一次，这里就变一次；满意了点右下「保存阶段」。
        </div>
      </div>

      {/* 右：对话 */}
      <div className="flex min-w-0 flex-col">
        <div ref={logRef} className="flex min-h-[240px] flex-1 flex-col gap-2.5 overflow-y-auto pr-1">
          <Bubble role="ai" text={DESIGN_GREETING} changes={[]} unchanged={false} />
          {messages.map((m, i) => (
            <Bubble key={i} {...m} />
          ))}
        </div>
        <div className="mt-3 flex flex-none items-center gap-2 rounded-[10px] border border-border bg-card py-[7px] pr-[7px] pl-3 focus-within:border-input">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                send()
              }
            }}
            placeholder="说出要改的地方，如「职工安置单独拆一步」"
            autoComplete="off"
            className="min-w-0 flex-1 border-none bg-transparent text-[12.5px] text-foreground outline-none"
          />
          <button
            type="button"
            onClick={send}
            title="发送（回车）"
            className="flex size-[26px] shrink-0 cursor-pointer items-center justify-center rounded-full bg-foreground text-[12px] text-background"
          >
            ↑
          </button>
        </div>
        <div className="mt-1.5 text-[11px] text-muted-foreground">
          多轮对话式设计：每句话直接改左边草稿，边聊边成形。
        </div>
      </div>
    </div>
  )
}

function Bubble({ role, text, changes, unchanged }: AiDesignMessage) {
  const isUser = role === 'user'
  return (
    <div className={cn('flex', isUser && 'justify-end')}>
      <div
        className={cn(
          'max-w-[92%] rounded-[10px] px-3 py-2 text-[12.5px] leading-[1.7] whitespace-pre-line',
          isUser ? 'bg-secondary text-secondary-foreground' : 'border border-border-light bg-card',
          !isUser && unchanged && 'border-dashed text-muted-foreground',
        )}
      >
        {text}
        {changes.length > 0 && (
          <ul className="mt-[7px] list-disc border-t border-border-light pt-[7px] pl-4 text-[11.5px] leading-[1.65] text-secondary-foreground">
            {changes.map((c, i) => (
              <li key={i} className="mb-0.5 marker:text-status-green">
                {c}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
