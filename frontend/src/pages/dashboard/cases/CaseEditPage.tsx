import { useParams } from 'react-router'
import { CaseForm } from '@/features/cases/components/CaseForm'

export function CaseEditPage() {
  const { id } = useParams<{ id: string }>()
  return <CaseForm caseId={id} mode="edit" />
}

export default CaseEditPage
