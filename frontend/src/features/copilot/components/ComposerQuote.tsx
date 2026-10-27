/**
 * 输入框上方的「框选引用区」（豆包式）：引用条 + 快捷指令 pills。
 *
 * 从 Composer 拆出（后者超软红线）：本组件只管展示与点击分发，
 * 文本操作（填指令、聚焦输入框）通过 onPickPrompt 回调交还 Composer——
 * 输入框草稿是 Composer 的本地 state，不该在这里反向伸进去。
 */

import type { SelectionQuote } from '../types'
import { SelectionQuoteBar } from './RefQuote'

/**
 * 快捷指令 pills：点击把指令填进输入框（可改可补），不是直接发送——
 * 误触不该烧一轮模型调用。改写类的 prompt 结尾留白，光标已落在末尾，
 * 律师接着打要求即可。
 */
const QUOTE_PROMPTS: ReadonlyArray<readonly [string, string]> = [
  ['解释一下', '请解释这段条款的含义与作用。'],
  ['详细展开', '请详细展开分析这段条款。'],
  ['风险提示', '这段条款对我方有什么风险？'],
  ['帮我改写', '请按我的要求改写这段引用的条款（保持法律文书语体，只改这段）：'],
]

export function ComposerQuote({
  quote,
  onRemove,
  onPickPrompt,
}: {
  quote: SelectionQuote
  onRemove: () => void
  /** pill 点击：把指令文本交给 Composer 填入输入框并聚焦 */
  onPickPrompt: (prompt: string) => void
}) {
  return (
    <div className="mb-1.5">
      <SelectionQuoteBar quote={quote} onRemove={onRemove} />
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {QUOTE_PROMPTS.map(([label, prompt]) => (
          <button
            key={label}
            type="button"
            className="rounded-full border border-border bg-card px-2.5 py-[3px] text-[11.5px] text-secondary-foreground transition-colors hover:border-foreground/40 hover:text-foreground"
            onClick={() => onPickPrompt(prompt)}
          >
            {label} →
          </button>
        ))}
      </div>
    </div>
  )
}
