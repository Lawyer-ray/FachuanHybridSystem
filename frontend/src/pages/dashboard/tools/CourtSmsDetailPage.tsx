import { useParams } from 'react-router'
import { CourtSmsDetail } from '@/features/tools/components/CourtSmsDetail'

export default function CourtSmsDetailPage() {
  const { id } = useParams<{ id: string }>()
  return <CourtSmsDetail smsId={Number(id)} />
}
