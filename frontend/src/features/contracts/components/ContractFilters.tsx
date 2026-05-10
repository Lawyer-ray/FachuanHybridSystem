import { useRef, useState } from 'react'
import { Search, SlidersHorizontal } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Separator } from '@/components/ui/separator'
import { CASE_TYPE_LABELS, CONTRACT_STATUS_LABELS, FEE_MODE_LABELS, type CaseType, type ContractStatus, type FeeMode } from '../types'

interface Props {
  caseType?: CaseType
  onCaseTypeChange: (v: CaseType | undefined) => void
  status?: ContractStatus
  onStatusChange: (v: ContractStatus | undefined) => void
  search?: string
  onSearchChange: (v: string) => void
  feeMode?: FeeMode
  onFeeModeChange: (v: FeeMode | undefined) => void
  isFiled?: boolean
  onIsFiledChange: (v: boolean | undefined) => void
}

export function ContractFilters({
  caseType, onCaseTypeChange,
  status, onStatusChange,
  search, onSearchChange,
  feeMode, onFeeModeChange,
  isFiled, onIsFiledChange,
}: Props) {
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined)
  const [open, setOpen] = useState(false)

  const handleSearchInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => onSearchChange(e.target.value), 300)
  }

  const activeFilterCount = [caseType, status, feeMode, isFiled !== undefined ? isFiled : null].filter(Boolean).length

  const clearAll = () => {
    onCaseTypeChange(undefined)
    onStatusChange(undefined)
    onFeeModeChange(undefined)
    onIsFiledChange(undefined)
  }

  return (
    <div className="flex items-center gap-3">
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="搜索合同名称..."
          defaultValue={search}
          onChange={handleSearchInput}
          className="w-[200px] pl-8"
        />
      </div>

      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button variant="outline" className="gap-2">
            <SlidersHorizontal className="size-4" />
            筛选
            {activeFilterCount > 0 && (
              <Badge variant="secondary" className="ml-1 size-5 justify-center rounded-full p-0 text-xs">
                {activeFilterCount}
              </Badge>
            )}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[280px] p-4" align="start">
          <div className="space-y-4">
            {/* 案件类型 */}
            <div className="space-y-2">
              <h4 className="text-sm font-medium">案件类型</h4>
              <div className="flex flex-wrap gap-1.5">
                <FilterChip
                  label="全部"
                  active={!caseType}
                  onClick={() => onCaseTypeChange(undefined)}
                />
                {Object.entries(CASE_TYPE_LABELS).map(([k, v]) => (
                  <FilterChip
                    key={k}
                    label={v}
                    active={caseType === k}
                    onClick={() => onCaseTypeChange(caseType === k ? undefined : k as CaseType)}
                  />
                ))}
              </div>
            </div>

            <Separator />

            {/* 状态 */}
            <div className="space-y-2">
              <h4 className="text-sm font-medium">状态</h4>
              <div className="flex flex-wrap gap-1.5">
                <FilterChip
                  label="全部"
                  active={!status}
                  onClick={() => onStatusChange(undefined)}
                />
                {Object.entries(CONTRACT_STATUS_LABELS).map(([k, v]) => (
                  <FilterChip
                    key={k}
                    label={v}
                    active={status === k}
                    onClick={() => onStatusChange(status === k ? undefined : k as ContractStatus)}
                  />
                ))}
              </div>
            </div>

            <Separator />

            {/* 收费模式 */}
            <div className="space-y-2">
              <h4 className="text-sm font-medium">收费模式</h4>
              <div className="flex flex-wrap gap-1.5">
                <FilterChip
                  label="全部"
                  active={!feeMode}
                  onClick={() => onFeeModeChange(undefined)}
                />
                {Object.entries(FEE_MODE_LABELS).map(([k, v]) => (
                  <FilterChip
                    key={k}
                    label={v}
                    active={feeMode === k}
                    onClick={() => onFeeModeChange(feeMode === k ? undefined : k as FeeMode)}
                  />
                ))}
              </div>
            </div>

            <Separator />

            {/* 建档 */}
            <div className="space-y-2">
              <h4 className="text-sm font-medium">建档</h4>
              <div className="flex flex-wrap gap-1.5">
                <FilterChip
                  label="全部"
                  active={isFiled === undefined}
                  onClick={() => onIsFiledChange(undefined)}
                />
                <FilterChip
                  label="已建档"
                  active={isFiled === true}
                  onClick={() => onIsFiledChange(isFiled === true ? undefined : true)}
                />
                <FilterChip
                  label="未建档"
                  active={isFiled === false}
                  onClick={() => onIsFiledChange(isFiled === false ? undefined : false)}
                />
              </div>
            </div>

            {activeFilterCount > 0 && (
              <>
                <Separator />
                <Button variant="ghost" size="sm" className="w-full" onClick={clearAll}>
                  清除所有筛选
                </Button>
              </>
            )}
          </div>
        </PopoverContent>
      </Popover>
    </div>
  )
}

function FilterChip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
        active
          ? 'bg-primary text-primary-foreground'
          : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
      }`}
    >
      {label}
    </button>
  )
}
