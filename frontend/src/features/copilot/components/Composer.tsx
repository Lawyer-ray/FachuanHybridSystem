/**
 * 输入区：Enter 发送、Shift+Enter 换行；流式期间变为「停止」。
 * 主题：中性灰阶，无 emoji；发送成功静默，失败由 MessageList 的错误行兜底。
 */

import { useRef, useState } from 'react'
import { ArrowUp, Square } from 'lucide-react'

import { useCopilot } from '../store'
import { TurnStatsView } from './TurnStatsView'

export function Composer() {
  const [text, setText] = useState('')
  const streaming = useCopilot((s) => s.streaming)
  const send = useCopilot((s) => s.send)
  const stop = useCopilot((s) => s.stop)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const submit = () => {
    const value = text.trim()
    if (!value || streaming) return
    setText('')
    void send(value)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      submit()
    }
  }

  /** 跟随内容自适应高度（1–5 行） */
  const autoGrow = () => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`
  }

  return (
    <div className="flex-none border-t border-border p-2.5">
      <div className="flex items-end gap-2 rounded-[12px] border border-input bg-background px-2.5 py-1.5 focus-within:border-foreground/40">
        <textarea
          ref={textareaRef}
          value={text}
          rows={1}
          placeholder="问点什么…"
          className="max-h-30 min-h-6 flex-1 resize-none bg-transparent text-[13px] leading-relaxed text-foreground outline-none placeholder:text-muted-foreground"
          onChange={(e) => {
            setText(e.target.value)
            autoGrow()
          }}
          onKeyDown={handleKeyDown}
        />
        {streaming ? (
          <button
            type="button"
            className="flex h-7 w-7 flex-none items-center justify-center rounded-full bg-foreground text-background transition-opacity hover:opacity-85"
            onClick={stop}
            aria-label="停止生成"
          >
            <Square className="h-3 w-3 fill-current" />
          </button>
        ) : (
          <button
            type="button"
            className="flex h-7 w-7 flex-none items-center justify-center rounded-full bg-foreground text-background transition-opacity hover:opacity-85 disabled:opacity-30"
            onClick={submit}
            disabled={!text.trim()}
            aria-label="发送"
          >
            <ArrowUp className="h-3.5 w-3.5" strokeWidth={2.5} />
          </button>
        )}
      </div>
      <p className="mt-1.5 flex items-center gap-2 px-1 text-[11px] text-muted-foreground">
        <span className="min-w-0 flex-1 truncate">AI 回答仅供参考，法律判断需由律师复核。</span>
        <TurnStatsView />
      </p>
    </div>
  )
}
