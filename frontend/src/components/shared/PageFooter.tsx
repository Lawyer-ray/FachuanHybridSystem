import { Button } from '@/components/ui/button'

interface PageStat {
  label: string
  value: React.ReactNode
}

interface PageFooterProps {
  stats?: PageStat[]
  page?: number
  total?: number
  pageSize?: number
  onPageChange?: (page: number) => void
}

export function PageFooter({
  stats = [],
  page = 1,
  total = 0,
  pageSize = 20,
  onPageChange,
}: PageFooterProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  return (
    <div className="sticky bottom-0 z-10 flex items-center justify-between px-6 py-3 bg-background">
      {/* 左侧统计 */}
      <div className="flex items-center gap-4 text-sm text-muted-foreground">
        {stats.map((s, i) => (
          <span key={i}>
            {s.label}：<span className="font-medium text-foreground">{s.value}</span>
          </span>
        ))}
      </div>

      {/* 右侧分页 + 版权 */}
      <div className="flex items-center gap-4">
        {total > pageSize && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <span>
              第 {page}/{totalPages} 页
            </span>
            {page > 1 && (
              <Button variant="outline" size="sm" onClick={() => onPageChange?.(page - 1)}>
                上一页
              </Button>
            )}
            {page < totalPages && (
              <Button variant="outline" size="sm" onClick={() => onPageChange?.(page + 1)}>
                下一页
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
