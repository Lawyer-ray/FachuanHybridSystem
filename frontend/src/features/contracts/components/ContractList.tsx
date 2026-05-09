import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router'
import { Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PATHS } from '@/routes/paths'
import { PageFooter } from '@/components/shared/PageFooter'
import { usePaginatedList } from '@/hooks/use-paginated-list'
import { contractApi } from '../api'
import type { Contract, CaseType, ContractStatus, FeeMode } from '../types'
import { ContractFilters } from './ContractFilters'
import { ContractTable } from './ContractTable'

const PAGE_SIZE = 20

export function ContractList() {
  const navigate = useNavigate()
  const [caseType, setCaseType] = useState<CaseType | undefined>()
  const [status, setStatus] = useState<ContractStatus | undefined>('active')
  const [search, setSearch] = useState('')
  const [feeMode, setFeeMode] = useState<FeeMode | undefined>()
  const [isFiled, setIsFiled] = useState<boolean | undefined>()

  const filters = useMemo(() => ({
    case_type: caseType,
    status,
    search: search || undefined,
    fee_mode: feeMode,
    is_filed: isFiled,
  }), [caseType, status, search, feeMode, isFiled])

  const { data, isLoading, page, setPage, withPageReset } = usePaginatedList<Contract, typeof filters>({
    queryKey: 'contracts',
    fetchAll: (f) => contractApi.list(f),
    filters,
    pageSize: PAGE_SIZE,
    staleTime: 5 * 60 * 1000,
  })

  const handleCaseTypeChange = withPageReset(setCaseType)
  const handleStatusChange = withPageReset(setStatus)
  const handleSearchChange = withPageReset(setSearch)
  const handleFeeModeChange = withPageReset(setFeeMode)
  const handleIsFiledChange = withPageReset(setIsFiled)

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

      <ContractTable contracts={data.items} isLoading={isLoading} />

      <PageFooter
        stats={[{ label: '共', value: `${data.total} 条` }]}
        page={page}
        total={data.total}
        pageSize={PAGE_SIZE}
        onPageChange={setPage}
      />
    </div>
  )
}
