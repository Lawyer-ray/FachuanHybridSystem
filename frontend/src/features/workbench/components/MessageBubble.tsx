/** 消息气泡组件 */

import React from 'react'
import { Bot, User, AlertCircle } from 'lucide-react'
import { cn } from '@/lib/utils'
import { formatDate } from '@/lib/date'
import type { WorkbenchMessage } from '../types'
import { UserMessageContent } from './UserMessageContent'
import { BatchItemContent } from './BatchItemContent'
import { InlineToolCalls } from './InlineToolCalls'
import { MarkdownContent } from './MarkdownContent'
import { AssistantMeta } from './AssistantMeta'
import { FeedbackButtons, MessageActions } from './MessageActions'
import { BatchDownloadButton } from './BatchDownloadButton'
import { StreamingBubble } from './StreamingBubble'

interface MessageBubbleProps {
  message: WorkbenchMessage
  toolCalls?: WorkbenchMessage[]
}

export const MessageBubble = React.memo(function MessageBubble({ message, toolCalls }: MessageBubbleProps) {
  const isUser = message.role === 'user'
  const isSystem = message.role === 'system'

  return (
    <div className={cn('flex gap-2 md:gap-3', isUser ? 'justify-end' : 'justify-start')}>
      {!isUser && (
        <div
          className={cn(
            'flex size-6 md:size-8 shrink-0 items-center justify-center rounded-full',
            isSystem ? 'bg-destructive/10' : 'bg-primary/10',
          )}
        >
          {isSystem ? (
            <AlertCircle className="size-4 text-destructive" />
          ) : (
            <Bot className="size-4 text-primary" />
          )}
        </div>
      )}

      <div className={cn('flex flex-col gap-0.5', isUser ? 'items-end' : 'items-start')}>
        <div
          className={cn(
            'group relative max-w-[85%] md:max-w-[75%] min-w-0 rounded-lg px-4 py-2.5 text-sm',
            isUser
              ? 'bg-primary text-primary-foreground'
              : isSystem
                ? 'bg-destructive/10 text-destructive'
                : 'bg-muted',
          )}
        >
          {isUser ? (
            <UserMessageContent message={message} />
          ) : message.metadata?.source === 'batch_item' ? (
            <BatchItemContent content={message.content} />
          ) : (
            <MarkdownContent content={message.content} isSystem={isSystem} />
          )}

          {!isUser && !isSystem && message.metadata?.source === 'batch_analysis' && typeof message.metadata?.job_id === 'string' ? (
            <BatchDownloadButton jobId={message.metadata.job_id} />
          ) : null}

          {toolCalls && toolCalls.length > 0 && (
            <InlineToolCalls toolCalls={toolCalls} />
          )}

          {!isUser && !isSystem && (
            <AssistantMeta message={message} />
          )}

          {!isUser && !isSystem && message.role === 'assistant' && (
            <FeedbackButtons message={message} />
          )}

          {!isUser && !isSystem && (
            <MessageActions message={message} />
          )}
        </div>

        <span className="px-1 text-[10px] text-muted-foreground/60">
          {formatDate(message.created_at)}
        </span>
      </div>

      {isUser && (
        <div className="flex size-6 md:size-8 shrink-0 items-center justify-center rounded-full bg-primary">
          <User className="size-4 text-primary-foreground" />
        </div>
      )}
    </div>
  )
})

export { StreamingBubble }
