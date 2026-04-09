import { useParams } from 'react-router'
import { useInboxMessage } from '@/features/inbox/hooks/use-inbox-message'
import { InboxMessageView, InboxMessageSkeleton } from '@/features/inbox/components/InboxMessageView'

export default function InboxDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { data: message, isLoading, error } = useInboxMessage(id)

  if (isLoading) return <InboxMessageSkeleton />
  if (error || !message) {
    return (
      <div className="flex h-48 items-center justify-center">
        <p className="text-muted-foreground">消息不存在或加载失败</p>
      </div>
    )
  }

  return <InboxMessageView message={message} />
}
