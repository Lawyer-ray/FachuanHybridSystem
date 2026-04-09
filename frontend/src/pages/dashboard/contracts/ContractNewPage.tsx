import { ArrowLeft } from 'lucide-react'
import { useNavigate } from 'react-router'
import { Button } from '@/components/ui/button'
import { PATHS } from '@/routes/paths'
import { ContractForm } from '@/features/contracts/components/ContractForm'

export default function ContractNewPage() {
  const navigate = useNavigate()
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate(PATHS.ADMIN_CONTRACTS)}>
          <ArrowLeft className="size-5" />
        </Button>
        <h1 className="text-xl font-semibold">新建合同</h1>
      </div>
      <ContractForm mode="create" />
    </div>
  )
}
