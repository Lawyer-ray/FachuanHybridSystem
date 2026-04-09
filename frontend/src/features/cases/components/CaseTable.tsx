/**
 * CaseTable - 案件列表表格组件
 *
 * Requirements: 2.6, 2.7, 2.9, 2.10, 9.6
 */

import { useNavigate } from 'react-router'
import { Briefcase, FolderOpen } from 'lucide-react'
import { format } from 'date-fns'

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { generatePath } from '@/routes/paths'
import {
  type Case,
  type SimpleCaseType,
  type CaseStatus,
  SIMPLE_CASE_TYPE_LABELS,
  CASE_STATUS_LABELS,
  CASE_STAGE_LABELS,
  type CaseStage,
} from '../types'

export interface CaseTableProps {
  cases: Case[]
  isLoading: boolean
}

// ============================================================================
// Skeleton & Empty
// ============================================================================

function TableSkeleton() {
  return (
    <>{Array.from({ length: 5 }).map((_, i) => (
      <TableRow key={i}>
        {[12, 48, 20, 20, 24, 20, 24].map((w, j) => (
          <TableCell key={j}><div className={`bg-muted h-4 w-${w} animate-pulse rounded`} /></TableCell>
        ))}
      </TableRow>
    ))}</>
  )
}

function EmptyState() {
  return (
    <TableRow>
      <TableCell colSpan={7} className="h-48">
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

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '-'
  try {
    return format(new Date(dateStr), 'yyyy-MM-dd')
  } catch {
    return dateStr
  }
}

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

export function CaseTable({ cases, isLoading }: CaseTableProps) {
  const navigate = useNavigate()

  return (
    <div className="overflow-x-auto rounded-md border">
      <Table className="min-w-[700px]">
        <TableHeader>
          <TableRow>
            <TableHead className="w-[60px]">ID</TableHead>
            <TableHead>案件名称</TableHead>
            <TableHead className="w-[100px]">案件类型</TableHead>
            <TableHead className="w-[80px]">状态</TableHead>
            <TableHead className="w-[100px]">负责律师</TableHead>
            <TableHead className="w-[100px]">当前阶段</TableHead>
            <TableHead className="w-[110px]">立案日期</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading ? <TableSkeleton /> : cases.length === 0 ? <EmptyState /> : (
            cases.map((c) => {
              const stageKey = c.current_stage as CaseStage | null
              const stageLabel = stageKey ? (CASE_STAGE_LABELS[stageKey]?.zh ?? c.current_stage) : '-'
              const statusKey = c.status as CaseStatus | null
              const statusLabel = statusKey ? (CASE_STATUS_LABELS[statusKey]?.zh ?? c.status) : '-'
              const typeLabel = c.case_type ? (SIMPLE_CASE_TYPE_LABELS[c.case_type]?.zh ?? c.case_type) : null

              return (
                <TableRow
                  key={c.id}
                  onClick={() => navigate(generatePath.caseDetail(String(c.id)))}
                  className="cursor-pointer hover:bg-muted/50 transition-colors"
                >
                  <TableCell className="text-muted-foreground text-sm">{c.id}</TableCell>
                  <TableCell className="max-w-[260px]">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium line-clamp-2">{c.name}</span>
                      {c.is_archived && <Badge variant="secondary" className="shrink-0 text-xs">已归档</Badge>}
                    </div>
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
                  <TableCell className="text-muted-foreground font-mono text-sm">{formatDate(c.start_date)}</TableCell>
                </TableRow>
              )
            })
          )}
        </TableBody>
      </Table>
    </div>
  )
}
