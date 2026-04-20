/**
 * CaseDetail - 案件详情主组件（Tab 布局）
 *
 * Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.11, 3.12, 3.13, 3.14, 3.15, 10.2, 10.4
 */

import { useCallback, useState } from 'react'
import { useNavigate } from 'react-router'
import {
  ArrowLeft,
  Edit,
  Trash2,
  Briefcase,
  FileWarning,
  Calendar,
  Scale,
  DollarSign,
  FileText,
  Link as LinkIcon,
} from 'lucide-react'
import { format } from 'date-fns'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { PATHS, generatePath } from '@/routes/paths'

import { useCase } from '../hooks/use-case'
import { useCaseMutations } from '../hooks/use-case-mutations'
import { CasePartySection } from './CasePartySection'
import { CaseAssignmentSection } from './CaseAssignmentSection'
import { CaseLogSection } from './CaseLogSection'
import { CaseNumberSection } from './CaseNumberSection'
import { AuthoritySection } from './AuthoritySection'

import {
  type CaseStatus,
  type CaseStage,
  type Case,
  SIMPLE_CASE_TYPE_LABELS,
  CASE_STATUS_LABELS,
  CASE_STAGE_LABELS,
} from '../types'

// ============================================================================
// Props
// ============================================================================

export interface CaseDetailProps {
  caseId: string
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

function formatAmount(amount: number | null | undefined): string {
  if (amount == null) return '-'
  return `¥ ${amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`
}

// ============================================================================
// Info item helper
// ============================================================================

function InfoItem({
  icon: Icon,
  label,
  value,
  mono,
}: {
  icon: React.ElementType
  label: string
  value: string | null | undefined
  mono?: boolean
}) {
  const display = value || '未填写'
  const isEmpty = !value || value === '-'
  return (
    <div className="space-y-1.5">
      <div className="text-muted-foreground flex items-center gap-1.5 text-sm">
        <Icon className="size-4" />
        <span>{label}</span>
      </div>
      <p className={`text-sm ${isEmpty ? 'text-muted-foreground' : 'text-foreground'} ${mono && !isEmpty ? 'font-mono' : ''}`}>
        {display}
      </p>
    </div>
  )
}

// ============================================================================
// Loading skeleton
// ============================================================================

function DetailSkeleton() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="bg-muted size-10 animate-pulse rounded-full" />
          <div className="space-y-2">
            <div className="bg-muted h-6 w-40 animate-pulse rounded" />
            <div className="bg-muted h-4 w-24 animate-pulse rounded" />
          </div>
        </div>
        <div className="flex gap-2">
          <div className="bg-muted h-9 w-20 animate-pulse rounded" />
          <div className="bg-muted h-9 w-20 animate-pulse rounded" />
        </div>
      </div>
      <div className="bg-muted h-10 w-full max-w-md animate-pulse rounded" />
      <div className="bg-muted h-64 w-full animate-pulse rounded-lg" />
    </div>
  )
}

// ============================================================================
// 404 state
// ============================================================================

function NotFoundState({ onBack }: { onBack: () => void }) {
  return (
    <div className="flex min-h-[400px] flex-col items-center justify-center">
      <FileWarning className="text-muted-foreground mb-4 size-16 opacity-50" />
      <h2 className="mb-2 text-xl font-semibold">案件不存在</h2>
      <p className="text-muted-foreground mb-6">您访问的案件可能已被删除或不存在</p>
      <Button onClick={onBack} variant="outline">
        <ArrowLeft className="mr-2 size-4" />
        返回列表
      </Button>
    </div>
  )
}

// ============================================================================
// 基本信息 Tab
// ============================================================================

function BasicInfoTab({ caseData }: { caseData: Case }) {
  const stageKey = caseData.current_stage as CaseStage | null
  const stageLabel = stageKey ? (CASE_STAGE_LABELS[stageKey]?.zh ?? caseData.current_stage) : null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">基本信息</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          <InfoItem icon={Briefcase} label="案件名称" value={caseData.name} />
          <InfoItem icon={Scale} label="案件类型" value={caseData.case_type ? SIMPLE_CASE_TYPE_LABELS[caseData.case_type]?.zh : null} />
          <InfoItem icon={FileText} label="状态" value={caseData.status ? CASE_STATUS_LABELS[caseData.status as CaseStatus]?.zh ?? caseData.status : null} />
          <InfoItem icon={Calendar} label="立案日期" value={formatDate(caseData.start_date)} mono />
          <InfoItem icon={Calendar} label="生效日期" value={formatDate(caseData.effective_date)} mono />
          <InfoItem icon={Scale} label="案由" value={caseData.cause_of_action} />
          <InfoItem icon={FileText} label="当前阶段" value={stageLabel} />
          <InfoItem icon={DollarSign} label="标的金额" value={formatAmount(caseData.target_amount)} mono />
          <InfoItem icon={DollarSign} label="保全金额" value={formatAmount(caseData.preservation_amount)} mono />
          {caseData.contract_id && (
            <InfoItem icon={LinkIcon} label="关联合同" value={`合同 #${caseData.contract_id}`} />
          )}
        </div>
      </CardContent>
    </Card>
  )
}

// ============================================================================
// Main Component
// ============================================================================

export function CaseDetail({ caseId }: CaseDetailProps) {
  const navigate = useNavigate()
  const { data: caseData, isLoading, error } = useCase(caseId)
  const { deleteCase } = useCaseMutations()
  const [deleteOpen, setDeleteOpen] = useState(false)

  const handleBack = useCallback(() => navigate(PATHS.ADMIN_CASES), [navigate])
  const handleEdit = useCallback(() => navigate(generatePath.caseEdit(caseId)), [navigate, caseId])

  const handleDelete = useCallback(async () => {
    try {
      await deleteCase.mutateAsync(caseId)
      toast.success('案件已删除')
      navigate(PATHS.ADMIN_CASES)
    } catch {
      toast.error('删除失败')
    }
  }, [deleteCase, caseId, navigate])

  // Loading
  if (isLoading) return <DetailSkeleton />

  // 404
  if (error || !caseData) return <NotFoundState onBack={handleBack} />

  const statusKey = caseData.status as CaseStatus | null
  const statusLabel = statusKey ? (CASE_STATUS_LABELS[statusKey]?.zh ?? caseData.status) : null
  const typeLabel = caseData.case_type ? (SIMPLE_CASE_TYPE_LABELS[caseData.case_type]?.zh ?? caseData.case_type) : null

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <nav className="text-sm" aria-label="Breadcrumb">
        <ol className="flex items-center gap-1.5">
          <li>
            <span
              className="text-muted-foreground hover:text-foreground cursor-pointer transition-colors"
              onClick={handleBack}
            >
              案件
            </span>
          </li>
          <li className="text-muted-foreground">/</li>
          <li className="text-foreground truncate max-w-[300px]">{caseData.name}</li>
        </ol>
      </nav>

      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3 min-w-0">
          <div className="bg-primary/10 flex size-10 items-center justify-center rounded-full shrink-0">
            <Briefcase className="text-primary size-5" />
          </div>
          <div className="min-w-0">
            <h1 className="text-xl font-semibold truncate">{caseData.name}</h1>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              {statusKey && (
                <Badge variant={statusKey === 'active' ? 'default' : 'secondary'} className="text-xs">
                  {statusLabel}
                </Badge>
              )}
              {typeLabel && (
                <Badge variant="outline" className="text-xs">{typeLabel}</Badge>
              )}
              {caseData.is_filed && caseData.filing_number && (
                <Badge variant="outline" className="text-xs">
                  建档号: {caseData.filing_number}
                </Badge>
              )}
            </div>
          </div>
        </div>
        <div className="flex gap-2 shrink-0">
          <Button variant="outline" onClick={handleBack}>
            <ArrowLeft className="mr-2 size-4" />
            返回
          </Button>
          <Button
            variant="outline"
            onClick={() => setDeleteOpen(true)}
            className="text-destructive hover:text-destructive hover:bg-destructive/10 transition-colors"
          >
            <Trash2 className="mr-2 size-4" />
            删除
          </Button>
          <Button onClick={handleEdit} className="transition-colors">
            <Edit className="mr-2 size-4" />
            编辑
          </Button>
        </div>
      </div>

      <Separator />

      {/* Tabs */}
      <Tabs defaultValue="basic" className="w-full">
        <TabsList className="w-full justify-start overflow-x-auto" variant="line">
          <TabsTrigger value="basic">基本信息</TabsTrigger>
          <TabsTrigger value="parties">当事人</TabsTrigger>
          <TabsTrigger value="assignments">指派律师</TabsTrigger>
          <TabsTrigger value="logs">案件日志</TabsTrigger>
          <TabsTrigger value="numbers">案号</TabsTrigger>
          <TabsTrigger value="authorities">主管机关</TabsTrigger>
        </TabsList>

        <TabsContent value="basic" className="mt-4">
          <BasicInfoTab caseData={caseData} />
        </TabsContent>

        <TabsContent value="parties" className="mt-4">
          <CasePartySection parties={caseData.parties ?? []} editable={false} />
        </TabsContent>

        <TabsContent value="assignments" className="mt-4">
          <CaseAssignmentSection assignments={caseData.assignments ?? []} editable={false} />
        </TabsContent>

        <TabsContent value="logs" className="mt-4">
          <CaseLogSection logs={caseData.logs ?? []} editable={false} />
        </TabsContent>

        <TabsContent value="numbers" className="mt-4">
          <CaseNumberSection caseNumbers={caseData.case_numbers ?? []} editable={false} />
        </TabsContent>

        <TabsContent value="authorities" className="mt-4">
          <AuthoritySection authorities={caseData.supervising_authorities ?? []} editable={false} />
        </TabsContent>
      </Tabs>

      {/* Delete confirmation */}
      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除案件</AlertDialogTitle>
            <AlertDialogDescription>
              删除「{caseData.name}」后，其关联的当事人、日志、案号等数据将一并删除，且无法恢复。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              确认删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

export default CaseDetail
