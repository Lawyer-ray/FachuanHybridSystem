import { useParams } from 'react-router'
import { RecognitionDetail } from '@/features/automation/document-recognition'

/**
 * 文书智能识别详情页
 * @validates Requirements 1.6 - THE System SHALL 在 `/admin/automation/document-recognition/:id` 路径显示识别任务详情页
 */
export default function RecognitionDetailPage() {
  const { id } = useParams<{ id: string }>()

  if (!id) {
    return (
      <div className="flex items-center justify-center p-8">
        <p className="text-muted-foreground">无效的识别任务 ID</p>
      </div>
    )
  }

  return <RecognitionDetail taskId={Number(id)} />
}
