import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router'
import { Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PATHS } from '@/routes/paths'
import { PageFooter } from '@/components/shared/PageFooter'
import { ContractFilters } from './ContractFilters'
import { ContractTable } from './ContractTable'
import { useContracts } from '../hooks/use-contracts'
import type { CaseType, ContractStatus, FeeMode } from '../types'

const PAGE_SIZE = 20

export function ContractList() {
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const [caseType, setCaseType] = useState<CaseType | undefined>()
  const [status, setStatus] = useState<ContractStatus | undefined>()
  const [search, setSearch] = useState('')
  const [feeMode, setFeeMode] = useState<FeeMode | undefined>()
  const [isFiled, setIsFiled] = useState<boolean | undefined>()

  const { data, isLoading } = useContracts({
    page, page_size: PAGE_SIZE, case_type: caseType, status,
    search: search || undefined, fee_mode: feeMode, is_filed: isFiled,
  })

  const handleCaseTypeChange = useCallback((v: CaseType | undefined) => { setCaseType(v); setPage(1) }, [])
  const handleStatusChange = useCallback((v: ContractStatus | undefined) => { setStatus(v); setPage(1) }, [])
  const handleSearchChange = useCallback((v: string) => { setSearch(v); setPage(1) }, [])
  const handleFeeModeChange = useCallback((v: FeeMode | undefined) => { setFeeMode(v); setPage(1) }, [])
  const handleIsFiledChange = useCallback((v: boolean | undefined) => { setIsFiled(v); setPage(1) }, [])

  const contracts = data?.items ?? []
  const total = data?.total ?? 0

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <ContractFilters
          caseType={caseType} onCaseTypeChange={handleCaseTypeChange}
          status={status} onStatusChange={handleStatusChange}
          search={search} onSearchChange={handleSearchChange}
          feeMode={feeMode} onFeeModeChange={handleFeeModeChange}
          isFiled={isFiled} onIsFiledChange={handleIsFiledChange}
        />
        <Button onClick={() => navigate(PATHS.ADMIN_CONTRACT_NEW)} className="w-full sm:w-auto">
          <Plus className="mr-2 size-4" />新建合同
        </Button>
      </div>

      <ContractTable contracts={contracts} isLoading={isLoading} />

      <PageFooter
        stats={[{ label: '共', value: `${total} 条` }]}
        page={page}
        total={total}
        pageSize={PAGE_SIZE}
        onPageChange={setPage}
      />
    </div>
  )
}
