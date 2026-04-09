import { ArrowLeft } from 'lucide-react'
import { useNavigate, useParams } from 'react-router'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { PATHS } from '@/routes/paths'
import { ContractForm } from '@/features/contracts/components/ContractForm'
import { useContract } from '@/features/contracts/hooks/use-contract'

export default function ContractEditPage() {
  const navigate = useNavigate()
  const { id } = useParams<{ id: string }>()
  const { data: contract, isLoading } = useContract(id!)

  if (isLoading) return <div className="space-y-4"><Skeleton className="h-8 w-48" /><Skeleton className="h-96 w-full" /></div>
  if (!contract) return <div className="text-center text-muted-foreground">合同不存在</div>

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate(PATHS.ADMIN_CONTRACTS)}>
          <ArrowLeft className="size-5" />
        </Button>
        <h1 className="text-xl font-semibold">编辑合同：{contract.name}</h1>
      </div>
      <ContractForm mode="edit" contract={contract} />
    </div>
  )
}
