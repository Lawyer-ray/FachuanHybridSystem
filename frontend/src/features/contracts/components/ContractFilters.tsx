import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { CASE_TYPE_LABELS, CASE_STATUS_LABELS, type CaseType, type CaseStatus } from '../types'

interface Props {
  caseType?: CaseType
  onCaseTypeChange: (v: CaseType | undefined) => void
  status?: CaseStatus
  onStatusChange: (v: CaseStatus | undefined) => void
}

export function ContractFilters({ caseType, onCaseTypeChange, status, onStatusChange }: Props) {
  return (
    <div className="flex flex-wrap items-center gap-3">
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

      <Select value={status ?? 'all'} onValueChange={(v) => onStatusChange(v === 'all' ? undefined : v as CaseStatus)}>
        <SelectTrigger className="w-[120px]">
          <SelectValue placeholder="状态" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">全部状态</SelectItem>
          {Object.entries(CASE_STATUS_LABELS).map(([k, v]) => (
            <SelectItem key={k} value={k}>{v}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
