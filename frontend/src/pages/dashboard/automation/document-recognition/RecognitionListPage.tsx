import { RecognitionList } from '@/features/automation/document-recognition'

/**
 * 文书智能识别列表页
 * @validates Requirements 1.5 - THE System SHALL 在 `/admin/automation/document-recognition` 路径显示文书识别列表页
 */
export default function RecognitionListPage() {
  return <RecognitionList />
}
