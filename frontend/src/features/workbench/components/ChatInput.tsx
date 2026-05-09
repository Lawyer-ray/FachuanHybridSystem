/** 对话输入框组件（含 Agent 选择器） */

import React, { useState, useRef, useEffect, useCallback } from 'react'
import { Send, Square, Bot, Briefcase, FileText, Search, X } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { useSpeechRecognition } from '@/hooks/use-speech-recognition'
import { useWorkbenchStore } from '../stores/workbench-store'
import type { AgentType } from '../types'
import { AGENT_OPTIONS } from '../types'
import { VoiceButton } from './VoiceButton'
import { ContextAttachments } from './ContextAttachments'

const AGENT_ICONS: Record<AgentType, typeof Bot> = {
  triage: Bot,
  case: Briefcase,
  contract: FileText,
  research: Search,
}

interface ChatInputProps {
  onSend: (content: string) => void
  disabled?: boolean
}

export const ChatInput = React.memo(function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [content, setContent] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const sendAfterSpeechRef = useRef(false)
  const { isStreaming, selectedAgent, setSelectedAgent, abortStream, quotedContent, setQuotedContent } = useWorkbenchStore()

  const speech = useSpeechRecognition({ lang: 'zh-CN', continuous: true, interimResults: true })

  useEffect(() => {
    if (!disabled) textareaRef.current?.focus()
  }, [disabled])

  // 语音转写结果追加到 content
  useEffect(() => {
    if (speech.finalTranscript) {
      setContent((prev) => prev + speech.finalTranscript)
      speech.reset()
      if (sendAfterSpeechRef.current) {
        sendAfterSpeechRef.current = false
        requestAnimationFrame(() => handleSubmitRef.current?.())
      }
    }
  }, [speech.finalTranscript]) // eslint-disable-line react-hooks/exhaustive-deps

  // 语音错误提示
  useEffect(() => {
    if (speech.error) toast.error(speech.error)
  }, [speech.error])

  const handleSubmit = useCallback(() => {
    if (speech.isListening) {
      sendAfterSpeechRef.current = true
      speech.stop()
      return
    }
    const trimmed = content.trim()
    if (!trimmed || disabled || isStreaming) return
    const fullContent = quotedContent
      ? `> ${quotedContent.replace(/\n/g, '\n> ')}\n\n${trimmed}`
      : trimmed
    onSend(fullContent)
    setContent('')
    setQuotedContent(null)
    requestAnimationFrame(() => textareaRef.current?.focus())
  }, [content, disabled, isStreaming, onSend, speech, quotedContent, setQuotedContent])

  const handleSubmitRef = useRef(handleSubmit)
  handleSubmitRef.current = handleSubmit

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const displayContent = speech.isListening ? content + speech.interimTranscript : content

  return (
    <div className="border-t p-3 md:p-4 space-y-2">
      {/* 上下文附件 */}
      <ContextAttachments />

      {/* Agent 选择器 */}
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="text-xs text-muted-foreground mr-1">助手:</span>
        {AGENT_OPTIONS.map((agent) => {
          const Icon = AGENT_ICONS[agent.type]
          return (
            <Badge
              key={agent.type}
              variant={selectedAgent === agent.type ? 'default' : 'outline'}
              className={cn(
                'cursor-pointer text-[11px] gap-1 transition-colors',
                selectedAgent !== agent.type && 'hover:bg-accent',
              )}
              onClick={() => setSelectedAgent(agent.type)}
              title={agent.description}
            >
              <Icon className="size-3" />
              {agent.name}
            </Badge>
          )
        })}
      </div>

      {/* 引用内容 */}
      {quotedContent && (
        <div className="flex items-start gap-2 rounded-md border-l-2 border-primary/50 bg-muted/50 px-3 py-2 text-xs text-muted-foreground">
          <span className="flex-1 line-clamp-2">{quotedContent}</span>
          <button
            type="button"
            onClick={() => setQuotedContent(null)}
            className="shrink-0 text-muted-foreground hover:text-foreground"
          >
            <X className="size-3" />
          </button>
        </div>
      )}

      {/* 输入框 */}
      <div className="flex items-end gap-2">
        <Textarea
          ref={textareaRef}
          value={displayContent}
          onChange={(e) => setContent(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入消息... (Enter 发送，Shift+Enter 换行)"
          disabled={disabled}
          readOnly={speech.isListening}
          className={cn(
            'min-h-[44px] max-h-[160px] resize-none',
            speech.isListening && 'border-primary/50 bg-primary/5',
          )}
          rows={1}
        />
        <VoiceButton
          isSupported={speech.isSupported}
          isListening={speech.isListening}
          onStart={speech.start}
          onStop={speech.stop}
          disabled={disabled || isStreaming}
        />
        {isStreaming ? (
          <Button
            size="icon"
            variant="destructive"
            onClick={() => abortStream()}
            className="shrink-0"
          >
            <Square className="size-4" />
          </Button>
        ) : (
          <Button
            size="icon"
            onClick={handleSubmit}
            disabled={!content.trim() || disabled}
            className="shrink-0"
          >
            <Send className="size-4" />
          </Button>
        )}
      </div>
    </div>
  )
})
