/**
 * CaseTable - 案件列表表格组件
 *
 * Requirements: 2.6, 2.7, 2.9, 2.10, 9.6
 */

import { useNavigate } from 'react-router'
import { FolderOpen } from 'lucide-react'
import { formatDateOnly } from '@/lib/date'

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { generatePath } from '@/routes/paths'
import {
  type Case,
  type CaseStatus,
  SIMPLE_CASE_TYPE_LABELS,
  CASE_STATUS_LABELS,
  CASE_STAGE_LABELS,
  type CaseStage,
} from '../types'

export interface CaseTableProps {
  cases: Case[]
  isLoading: boolean
  selectedIds?: Set<number>
  onSelectionChange?: (ids: Set<number>) => void
}

// ============================================================================
// Skeleton & Empty
// ============================================================================

function TableSkeleton({ colSpan }: { colSpan: number }) {
  const widths = colSpan === 9 ? [40, 12, 48, 24, 20, 20, 24, 20, 24] : [12, 48, 24, 20, 20, 24, 20, 24]
  return (
    <>{Array.from({ length: 5 }).map((_, i) => (
      <TableRow key={i}>
        {widths.map((w, j) => (
          <TableCell key={j}><div className={`bg-muted h-4 w-${w} animate-pulse rounded`} /></TableCell>
        ))}
      </TableRow>
    ))}</>
  )
}

function EmptyState({ colSpan }: { colSpan: number }) {
  return (
    <TableRow>
      <TableCell colSpan={colSpan} className="h-48">
        <div className="flex flex-col items-center justify-center gap-3">
          <div className="bg-muted flex size-12 items-center justify-center rounded-full">
            <FolderOpen className="text-muted-foreground size-6" />
          </div>
          <p className="text-muted-foreground text-sm">暂无案件数据</p>
        </div>
      </TableCell>
    </TableRow>
  )
}

// ============================================================================
// Helpers
// ============================================================================


function getLawyerDisplay(c: Case): string {
  const assignments = c.assignments ?? []
  if (assignments.length === 0) return '-'
  const first = assignments[0].lawyer_detail
  const name = first.real_name || first.username
  if (assignments.length === 1) return name
  return `${name} 等${assignments.length}人`
}

// ============================================================================
// Main Component
// ============================================================================

export function CaseTable({ cases, isLoading, selectedIds, onSelectionChange }: CaseTableProps) {
  const navigate = useNavigate()
  const selectable = !!onSelectionChange

  const toggleRow = (id: number, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!onSelectionChange || !selectedIds) return
    const next = new Set(selectedIds)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    onSelectionChange(next)
  }

  const toggleAll = () => {
    if (!onSelectionChange) return
    const allIds = cases.map((c) => c.id)
    const allSelected = allIds.length > 0 && allIds.every((id) => selectedIds?.has(id))
    onSelectionChange(allSelected ? new Set() : new Set(allIds))
  }

  const colSpan = selectable ? 9 : 8

  return (
    <div className="overflow-x-auto rounded-md border">
      <Table className="min-w-[700px]">
        <TableHeader>
          <TableRow>
            {selectable && (
              <TableHead className="w-[40px]">
                <Checkbox
                  checked={cases.length > 0 && cases.every((c) => selectedIds?.has(c.id))}
                  onCheckedChange={toggleAll}
                  aria-label="全选"
                />
              </TableHead>
            )}
            <TableHead className="w-[60px]">ID</TableHead>
            <TableHead>案件名称</TableHead>
            <TableHead className="w-[160px]">立案号</TableHead>
            <TableHead className="w-[100px]">案件类型</TableHead>
            <TableHead className="w-[80px]">状态</TableHead>
            <TableHead className="w-[100px]">负责律师</TableHead>
            <TableHead className="w-[100px]">当前阶段</TableHead>
            <TableHead className="w-[110px]">立案日期</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading ? <TableSkeleton colSpan={colSpan} /> : cases.length === 0 ? <EmptyState colSpan={colSpan} /> : (
            cases.map((c) => {
              const stageKey = c.current_stage as CaseStage | null
              const stageLabel = stageKey ? (CASE_STAGE_LABELS[stageKey]?.zh ?? c.current_stage) : '-'
              const statusKey = c.status as CaseStatus | null
              const statusLabel = statusKey ? (CASE_STATUS_LABELS[statusKey]?.zh ?? c.status) : '-'
              const typeLabel = c.case_type ? (SIMPLE_CASE_TYPE_LABELS[c.case_type]?.zh ?? c.case_type) : null
              const isSelected = selectedIds?.has(c.id) ?? false

              return (
                <TableRow
                  key={c.id}
                  onClick={() => navigate(generatePath.caseDetail(String(c.id)))}
                  className={`cursor-pointer hover:bg-muted/50 transition-colors ${isSelected ? 'bg-muted/40' : ''}`}
                >
                  {selectable && (
                    <TableCell onClick={(e) => toggleRow(c.id, e)}>
                      <Checkbox checked={isSelected} aria-label={`选择案件 ${c.name}`} />
                    </TableCell>
                  )}
                  <TableCell className="text-muted-foreground text-sm">{c.id}</TableCell>
                  <TableCell className="max-w-[260px]">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium line-clamp-2">{c.name}</span>
                      {c.is_filed && <Badge variant="secondary" className="shrink-0 text-xs">已建档</Badge>}
                    </div>
                  </TableCell>
                  <TableCell className="font-mono text-sm text-muted-foreground">
                    {c.filing_number || '-'}
                  </TableCell>
                  <TableCell>
                    {typeLabel
                      ? <Badge variant="outline" className="text-xs">{typeLabel}</Badge>
                      : <span className="text-muted-foreground text-sm">-</span>
                    }
                  </TableCell>
                  <TableCell>
                    {statusKey
                      ? <Badge variant={statusKey === 'active' ? 'default' : 'secondary'} className="text-xs">{statusLabel}</Badge>
                      : <span className="text-muted-foreground text-sm">-</span>
                    }
                  </TableCell>
                  <TableCell className="text-sm">{getLawyerDisplay(c)}</TableCell>
                  <TableCell className="text-muted-foreground text-sm">{stageLabel}</TableCell>
                  <TableCell className="text-muted-foreground font-mono text-sm">{formatDateOnly(c.start_date)}</TableCell>
                </TableRow>
              )
            })
          )}
        </TableBody>
      </Table>
    </div>
  )
}
