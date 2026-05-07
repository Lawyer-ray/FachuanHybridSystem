/** 消息列表组件 */

import { useEffect, useRef, useMemo, useCallback } from 'react'
import { Virtuoso, type VirtuosoHandle } from 'react-virtuoso'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useWorkbenchStore } from '../stores/workbench-store'
import { MessageBubble, StreamingBubble } from './MessageBubble'

const VIRTUALIZE_THRESHOLD = 50

export function MessageList() {
  const scrollRef = useRef<HTMLDivElement>(null)
  const virtuosoRef = useRef<VirtuosoHandle>(null)
  const { messages, streamingMessage, isStreaming, messagesLoading, currentSession } = useWorkbenchStore()
  const prevCountRef = useRef(0)
  const prevSessionIdRef = useRef<number | null>(null)

  const isEmpty = messages.length === 0 && !isStreaming && !messagesLoading

  // 将 flat messages 分组：assistant 消息后的连续 tool 消息归入同一组
  const groupedMessages = useMemo(() => {
    const groups: { type: 'user' | 'system' | 'assistant'; message: typeof messages[0]; toolCalls?: typeof messages }[] = []
    let i = 0
    while (i < messages.length) {
      const msg = messages[i]
      if (msg.role === 'assistant') {
        // 收集后续连续的 tool 消息
        const toolCalls: typeof messages = []
        let j = i + 1
        while (j < messages.length && messages[j].role === 'tool') {
          toolCalls.push(messages[j])
          j++
        }
        groups.push({ type: 'assistant', message: msg, toolCalls })
        i = j
      } else {
        groups.push({ type: msg.role as 'user' | 'system', message: msg })
        i++
      }
    }
    return groups
  }, [messages])

  const useVirtualization = groupedMessages.length > VIRTUALIZE_THRESHOLD

  // Scroll to top when switching sessions
  useEffect(() => {
    if (currentSession?.id !== prevSessionIdRef.current) {
      prevSessionIdRef.current = currentSession?.id ?? null
      prevCountRef.current = 0
      if (useVirtualization) {
        virtuosoRef.current?.scrollToIndex({ index: 0, behavior: 'auto' })
      } else {
        const el = scrollRef.current
        if (el) el.scrollTop = 0
      }
    }
  }, [currentSession?.id, useVirtualization])

  // Scroll to bottom when messages first load or new messages arrive (non-virtualized)
  useEffect(() => {
    if (useVirtualization) return
    const el = scrollRef.current
    if (!el || isEmpty) return

    const prevCount = prevCountRef.current
    prevCountRef.current = messages.length

    const isFirstLoad = prevCount === 0 && messages.length > 0
    if (isFirstLoad) {
      setTimeout(() => {
        el.scrollTop = el.scrollHeight
      }, 50)
    } else {
      const threshold = 120
      const isAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight < threshold
      if (isAtBottom) {
        requestAnimationFrame(() => {
          el.scrollTop = el.scrollHeight
        })
      }
    }
  }, [messages, isEmpty, useVirtualization])

  // Auto-scroll during streaming (non-virtualized)
  useEffect(() => {
    if (useVirtualization) return
    if (!streamingMessage) return
    const el = scrollRef.current
    if (!el) return
    requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight
    })
  }, [streamingMessage, useVirtualization])

  // Virtuoso item renderer
  const renderGroup = useCallback((_index: number, group: typeof groupedMessages[0]) => (
    <div className="py-2 px-4">
      <MessageBubble message={group.message} toolCalls={group.toolCalls} />
    </div>
  ), [])

  // Virtuoso footer (streaming bubble)
  const VirtuosoFooter = useCallback(() => {
    if (!isStreaming || !streamingMessage) return null
    return (
      <div className="px-4 pb-2">
        <StreamingBubble message={streamingMessage} />
      </div>
    )
  }, [isStreaming, streamingMessage])

  // Virtuoso 需要自身作为滚动容器，不能嵌套在 ScrollArea 内
  if (useVirtualization) {
    return (
      <div ref={scrollRef} className="flex-1 overflow-hidden">
        <Virtuoso
          ref={virtuosoRef}
          data={groupedMessages}
          followOutput="smooth"
          itemContent={renderGroup}
          components={{ Footer: VirtuosoFooter }}
          style={{ height: '100%' }}
        />
      </div>
    )
  }

  return (
    <ScrollArea ref={scrollRef} className="flex-1 overflow-y-auto">
      {messagesLoading ? (
        <div className="space-y-4 p-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className={`flex gap-3 ${i % 2 === 0 ? 'justify-start' : 'justify-end'}`}>
              {i % 2 === 0 && <div className="size-8 shrink-0 rounded-full bg-muted animate-pulse" />}
              <div className="max-w-[60%] space-y-2">
                <div className="h-4 w-48 rounded bg-muted animate-pulse" />
                <div className="h-4 w-32 rounded bg-muted animate-pulse" />
              </div>
              {i % 2 !== 0 && <div className="size-8 shrink-0 rounded-full bg-muted animate-pulse" />}
            </div>
          ))}
        </div>
      ) : isEmpty ? (
        <div className="flex min-h-[60vh] items-center justify-center text-muted-foreground text-sm">
          <div className="text-center space-y-2">
            <div className="text-4xl">💬</div>
            <p>开始对话吧</p>
          </div>
        </div>
      ) : (
        <div className="space-y-4 p-4">
          {groupedMessages.map((group) => (
            <MessageBubble
              key={group.message.id}
              message={group.message}
              toolCalls={group.toolCalls}
            />
          ))}
          {isStreaming && streamingMessage && <StreamingBubble message={streamingMessage} />}
        </div>
      )}
    </ScrollArea>
  )
}
