import { useParams } from 'react-router'
import { QuoteDetail } from '@/features/automation/preservation-quotes'

/**
 * 财产保全询价详情页
 * @validates Requirements 1.4 - THE System SHALL 在 `/admin/automation/preservation-quotes/:id` 路径显示询价任务详情页
 */
export default function QuoteDetailPage() {
  const { id } = useParams<{ id: string }>()

  if (!id) {
    return (
      <div className="flex items-center justify-center p-8">
        <p className="text-muted-foreground">无效的询价任务 ID</p>
      </div>
    )
  }

  return <QuoteDetail quoteId={Number(id)} />
}
