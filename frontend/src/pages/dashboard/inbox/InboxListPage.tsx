import { InboxList } from '@/features/inbox'

export default function InboxListPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">收件箱</h1>
        <p className="text-muted-foreground text-sm">查看来自各数据源的消息</p>
      </div>
      <InboxList />
    </div>
  )
}
