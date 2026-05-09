import { useState } from 'react'
import { useNavigate } from 'react-router'
import { RefreshCw, Settings2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PATHS } from '@/routes/paths'
import { PageFooter } from '@/components/shared/PageFooter'
import { usePaginatedList } from '@/hooks/use-paginated-list'
import { inboxApi } from '../api'
import type { InboxMessage } from '../types'
import { InboxFilters } from './InboxFilters'
import { InboxTable } from './InboxTable'

const PAGE_SIZE = 20

export function InboxList() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [hasAttachments, setHasAttachments] = useState('all')

  const filters = {
    search: search || undefined,
    has_attachments: hasAttachments === 'all' ? undefined : hasAttachments === 'true',
  }

  const { data, isLoading, page, setPage, withPageReset } = usePaginatedList<InboxMessage, typeof filters>({
    queryKey: 'inbox-messages',
    fetchAll: (f) => inboxApi.list(f),
    filters,
    pageSize: PAGE_SIZE,
  })

  const handleSearchChange = withPageReset(setSearch)
  const handleAttachmentsChange = withPageReset(setHasAttachments)

  return (
    <div className="flex flex-col gap-4">
      {/* 页面标题 + 操作按钮 */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold">收件箱</h1>
          <p className="text-muted-foreground text-sm mt-1">查看来自各消息平台的来信</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => navigate(PATHS.ADMIN_MESSAGE_SOURCES)}>
            <Settings2 className="mr-1.5 size-4" />
            消息来源管理
          </Button>
          <Button size="sm">
            <RefreshCw className="mr-1.5 size-4" />
            立即同步
          </Button>
        </div>
      </div>

      <InboxFilters
        search={search}
        onSearchChange={handleSearchChange}
        hasAttachments={hasAttachments}
        onHasAttachmentsChange={handleAttachmentsChange}
      />

      <InboxTable messages={data.items} isLoading={isLoading} />

      <PageFooter
        stats={[{ label: '共', value: `${data.total} 条` }]}
        page={page}
        total={data.total}
        pageSize={PAGE_SIZE}
        onPageChange={setPage}
      />
    </div>
  )
}
