import { useState, useCallback } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { InboxFilters } from './InboxFilters'
import { InboxTable } from './InboxTable'
import { useInboxMessages } from '../hooks/use-inbox-messages'

const PAGE_SIZE = 20

export function InboxList() {
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [hasAttachments, setHasAttachments] = useState('all')

  const { data, isLoading, isFetching } = useInboxMessages({
    page,
    page_size: PAGE_SIZE,
    search: search || undefined,
    has_attachments: hasAttachments === 'all' ? undefined : hasAttachments === 'true',
  })

  const handleSearchChange = useCallback((v: string) => { setSearch(v); setPage(1) }, [])
  const handleAttachmentsChange = useCallback((v: string) => { setHasAttachments(v); setPage(1) }, [])

  const messages = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = data?.total_pages ?? 1

  const startItem = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1
  const endItem = Math.min(page * PAGE_SIZE, total)

  return (
    <div className="flex flex-col gap-4">
      <InboxFilters
        search={search}
        onSearchChange={handleSearchChange}
        hasAttachments={hasAttachments}
        onHasAttachmentsChange={handleAttachmentsChange}
      />

      <InboxTable messages={messages} isLoading={isLoading} />

      {/* 分页 */}
      <div className="flex flex-col items-center justify-between gap-3 sm:flex-row">
        <p className="text-muted-foreground text-sm">
          {total === 0 ? '暂无数据' : (
            <>
              显示第 <span className="text-foreground font-medium">{startItem}</span> -{' '}
              <span className="text-foreground font-medium">{endItem}</span> 条，共{' '}
              <span className="text-foreground font-medium">{total}</span> 条
            </>
          )}
        </p>
        {totalPages > 1 && (
          <div className="flex items-center gap-2">
            <Button
              variant="outline" size="sm"
              onClick={() => setPage((p) => p - 1)}
              disabled={page <= 1 || isFetching}
              className="h-8 w-8 p-0"
            >
              <ChevronLeft className="size-4" />
            </Button>
            <span className="text-muted-foreground text-sm">
              {page} / {totalPages}
            </span>
            <Button
              variant="outline" size="sm"
              onClick={() => setPage((p) => p + 1)}
              disabled={page >= totalPages || isFetching}
              className="h-8 w-8 p-0"
            >
              <ChevronRight className="size-4" />
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
