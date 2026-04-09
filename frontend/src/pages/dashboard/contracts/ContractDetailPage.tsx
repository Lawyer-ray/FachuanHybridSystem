import { useParams } from 'react-router'
import { ContractDetail } from '@/features/contracts/components/ContractDetail'

export default function ContractDetailPage() {
  const { id } = useParams<{ id: string }>()
  if (!id) return null
  return <ContractDetail contractId={id} />
}
