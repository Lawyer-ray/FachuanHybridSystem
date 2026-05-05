import { useRef } from 'react'
import { Search } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
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

  const handleSearchInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => onSearchChange(e.target.value), 300)
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="搜索合同名称..."
          defaultValue={search}
          onChange={handleSearchInput}
          className="w-[200px] pl-8"
        />
      </div>

      <Select value={caseType ?? 'all'} onValueChange={(v) => onCaseTypeChange(v === 'all' ? undefined : v as CaseType)}>
        <SelectTrigger className="w-[140px]">
          <SelectValue placeholder="案件类型" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">全部类型</SelectItem>
          {Object.entries(CASE_TYPE_LABELS).map(([k, v]) => (
            <SelectItem key={k} value={k}>{v}</SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select value={status ?? 'all'} onValueChange={(v) => onStatusChange(v === 'all' ? undefined : v as ContractStatus)}>
        <SelectTrigger className="w-[120px]">
          <SelectValue placeholder="状态" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">全部状态</SelectItem>
          {Object.entries(CONTRACT_STATUS_LABELS).map(([k, v]) => (
            <SelectItem key={k} value={k}>{v}</SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select value={feeMode ?? 'all'} onValueChange={(v) => onFeeModeChange(v === 'all' ? undefined : v as FeeMode)}>
        <SelectTrigger className="w-[140px]">
          <SelectValue placeholder="收费模式" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">全部收费</SelectItem>
          {Object.entries(FEE_MODE_LABELS).map(([k, v]) => (
            <SelectItem key={k} value={k}>{v}</SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select value={isFiled === undefined ? 'all' : isFiled ? 'yes' : 'no'} onValueChange={(v) => onIsFiledChange(v === 'all' ? undefined : v === 'yes')}>
        <SelectTrigger className="w-[120px]">
          <SelectValue placeholder="建档" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">全部</SelectItem>
          <SelectItem value="yes">已建档</SelectItem>
          <SelectItem value="no">未建档</SelectItem>
        </SelectContent>
      </Select>
    </div>
  )
}
