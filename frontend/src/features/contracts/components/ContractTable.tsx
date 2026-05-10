import { memo, useCallback } from 'react'
import { useNavigate } from 'react-router'
import { FileText } from 'lucide-react'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { generatePath } from '@/routes/paths'
import { FEE_MODE_LABELS, type Contract, type ContractStatus } from '../types'
import { formatAmountInt } from '@/lib/format'

const STATUS_VARIANT: Record<ContractStatus, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  active: 'default',
  closed: 'secondary',
  archived: 'secondary',
  unsigned: 'outline',
}

function TableSkeleton() {
  return (
    <>{Array.from({ length: 5 }).map((_, i) => (
      <TableRow key={i}>
        {[16, 48, 24, 24, 24, 20, 20, 24].map((w, j) => (
          <TableCell key={j}><div className={`bg-muted h-4 w-${w} animate-pulse rounded`} /></TableCell>
        ))}
      </TableRow>
    ))}</>
  )
}

function EmptyState() {
  return (
    <TableRow>
      <TableCell colSpan={8} className="h-48">
        <div className="flex flex-col items-center justify-center gap-3">
          <div className="bg-muted flex size-12 items-center justify-center rounded-full">
            <FileText className="text-muted-foreground size-6" />
          </div>
          <p className="text-muted-foreground text-sm">暂无合同数据</p>
        </div>
      </TableCell>
    </TableRow>
  )
}

const ContractRow = memo(function ContractRow({ contract, onRowClick }: { contract: Contract; onRowClick: (c: Contract) => void }) {
  return (
    <TableRow onClick={() => onRowClick(contract)} className="cursor-pointer hover:bg-muted/50 transition-colors">
      <TableCell className="text-muted-foreground text-sm">{contract.id}</TableCell>
      <TableCell><Badge variant="outline" className="text-xs">{contract.case_type_label}</Badge></TableCell>
      <TableCell className="max-w-[260px]">
        <div className="flex items-center gap-2">
          <span className="font-medium text-sm line-clamp-2">{contract.name}</span>
          {contract.is_filed && <Badge variant="secondary" className="shrink-0 text-xs">已建档</Badge>}
        </div>
      </TableCell>
      <TableCell>
        <Badge variant={STATUS_VARIANT[contract.status] ?? 'outline'} className="text-xs">
          {contract.status_label}
        </Badge>
      </TableCell>
      <TableCell className="text-xs text-muted-foreground">
        {FEE_MODE_LABELS[contract.fee_mode as keyof typeof FEE_MODE_LABELS] ?? contract.fee_mode ?? '-'}
      </TableCell>
      <TableCell className="text-sm">{contract.primary_lawyer?.real_name || contract.primary_lawyer?.username || '-'}</TableCell>
      <TableCell className="text-sm text-muted-foreground">{contract.start_date ?? '-'}</TableCell>
      <TableCell className="text-right font-mono text-sm">{formatAmountInt(contract.total_received)}</TableCell>
    </TableRow>
  )
})

export function ContractTable({ contracts, isLoading = false }: { contracts: Contract[]; isLoading?: boolean }) {
  const navigate = useNavigate()

  const handleRowClick = useCallback((c: Contract) => navigate(generatePath.contractDetail(c.id)), [navigate])

  return (
    <div className="overflow-x-auto rounded-md border">
      <Table className="min-w-[900px]">
        <TableHeader>
          <TableRow>
            <TableHead className="w-[60px]">ID</TableHead>
            <TableHead className="w-[100px]">类型</TableHead>
            <TableHead>合同名称</TableHead>
            <TableHead className="w-[80px]">状态</TableHead>
            <TableHead className="w-[110px]">收费模式</TableHead>
            <TableHead className="w-[100px]">主办律师</TableHead>
            <TableHead className="w-[100px]">开始日期</TableHead>
            <TableHead className="w-[120px] text-right">已收款(元)</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading ? <TableSkeleton /> : contracts.length === 0 ? <EmptyState /> : (
            contracts.map((c) => <ContractRow key={c.id} contract={c} onRowClick={handleRowClick} />)
          )}
        </TableBody>
      </Table>
    </div>
  )
}
