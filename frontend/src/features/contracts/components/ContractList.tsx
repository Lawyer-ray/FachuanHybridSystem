import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router'
import { Plus, ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PATHS } from '@/routes/paths'
import { ContractFilters } from './ContractFilters'
import { ContractTable } from './ContractTable'
import { useContracts } from '../hooks/use-contracts'
import type { CaseType, ContractStatus } from '../types'

const PAGE_SIZE = 20

export function ContractList() {
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const [caseType, setCaseType] = useState<CaseType | undefined>()
  const [status, setStatus] = useState<ContractStatus | undefined>()

  const { data, isLoading, isFetching } = useContracts({
    page, page_size: PAGE_SIZE, case_type: caseType, status,
  })

  const handleCaseTypeChange = useCallback((v: CaseType | undefined) => { setCaseType(v); setPage(1) }, [])
  const handleStatusChange = useCallback((v: ContractStatus | undefined) => { setStatus(v); setPage(1) }, [])

  const contracts = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = data?.total_pages ?? 1

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <ContractFilters
          caseType={caseType} onCaseTypeChange={handleCaseTypeChange}
          status={status} onStatusChange={handleStatusChange}
        />
        <Button onClick={() => navigate(PATHS.ADMIN_CONTRACT_NEW)} className="w-full sm:w-auto">
          <Plus className="mr-2 size-4" />新建合同
        </Button>
      </div>

      <ContractTable contracts={contracts} isLoading={isLoading} />

      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-muted-foreground text-sm">
            共 <span className="text-foreground font-medium">{total}</span> 条
          </p>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => setPage(p => p - 1)} disabled={page <= 1 || isFetching} className="h-8 w-8 p-0">
              <ChevronLeft className="size-4" />
            </Button>
            <span className="text-sm">{page} / {totalPages}</span>
            <Button variant="outline" size="sm" onClick={() => setPage(p => p + 1)} disabled={page >= totalPages || isFetching} className="h-8 w-8 p-0">
              <ChevronRight className="size-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
