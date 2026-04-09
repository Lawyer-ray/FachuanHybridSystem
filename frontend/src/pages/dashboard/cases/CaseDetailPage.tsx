import { useParams } from 'react-router'
import { CaseDetail } from '@/features/cases/components/CaseDetail'

export function CaseDetailPage() {
  const { id } = useParams<{ id: string }>()
  return <CaseDetail caseId={id!} />
}

export default CaseDetailPage
