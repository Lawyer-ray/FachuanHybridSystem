import { useCallback, useState } from 'react'
import { useNavigate } from 'react-router'
import { AnimatePresence, motion } from 'framer-motion'
import {
  ArrowLeft, Edit, Trash2, FileWarning, Hash, Building2, MessageSquare,
  FileText, FolderOpen, Landmark, Paperclip, Users,
} from 'lucide-react'
import { formatDateOnly } from '@/lib/date'
import { formatAmount } from '@/lib/format'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { PATHS, generatePath } from '@/routes/paths'

import { useCase } from '../hooks/use-case'
import { useCaseMutations } from '../hooks/use-case-mutations'
import { useMaterialCandidates } from '../hooks/use-material-candidates'
import { useTemplateBindings } from '../hooks/use-template-bindings'
import { useFolderBinding } from '../hooks/use-folder-binding'
import { useAccessGrants } from '../hooks/use-access-grants'
import { CaseLogSection } from './CaseLogSection'
import { CaseNumberSection } from './CaseNumberSection'
import { CaseAccessGrantSection } from './CaseAccessGrantSection'
import { CaseMaterialSection } from './CaseMaterialSection'
import { CaseTemplateSection } from './CaseTemplateSection'
import { CaseFolderSection } from './CaseFolderSection'
import { AuthoritySection } from './AuthoritySection'
import { CaseContactSection } from '@/features/contacts'

import {
  type CaseStatus, type CaseStage,
  SIMPLE_CASE_TYPE_LABELS, CASE_STATUS_LABELS, CASE_STAGE_LABELS,
  LEGAL_STATUS_LABELS,
} from '../types'

export interface CaseDetailProps { caseId: string }

/* ── Shared helpers ── */

function DetailField({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div>
      <div className="text-muted-foreground mb-0.5 text-xs">{label}</div>
      <div className={`text-[13px] ${mono ? 'font-mono' : ''}`}>{value || '—'}</div>
    </div>
  )
}

function DetailCard({ title, children, extra }: { title: string; children: React.ReactNode; extra?: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border/60 p-[18px] mb-4 bg-card">
      {extra ? (
        <div className="flex items-center justify-between mb-3.5">
          <h3 className="text-sm font-semibold text-foreground">{title}</h3>
          {extra}
        </div>
      ) : (
        <h3 className="text-sm font-semibold text-foreground mb-3.5">{title}</h3>
      )}
      {children}
    </div>
  )
}

function StatusBadge({ status, label }: { status: string | null; label?: string | null }) {
  if (!status) return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-muted text-muted-foreground">未设置</span>
  const cls = status === 'active'
    ? 'bg-green-50 text-green-700'
    : status === 'closed'
      ? 'bg-muted text-muted-foreground'
      : 'bg-amber-50 text-amber-700'
  return <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium ${cls}`}>{label || status}</span>
}

const PLATFORM_LABELS: Record<string, string> = {
  feishu: '飞书',
  wechat: '微信',
  dingtalk: '钉钉',
}

/* ── Tabs config ── */

const TABS = [
  { value: 'basic', label: '基本信息' },
  { value: 'parties', label: '当事人与律师' },
  { value: 'contacts', label: '工作人员' },
  { value: 'progress', label: '案件进展' },
  { value: 'documents', label: '文书模板' },
  { value: 'materials', label: '材料管理' },
  { value: 'folder', label: '文件夹' },
  { value: 'court_filing', label: '一张网立案' },
]

const tabVariants = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -6 },
}

const tabTransition = { duration: 0.2, ease: 'easeInOut' as const }

/* ── Main component ── */

export function CaseDetail({ caseId }: CaseDetailProps) {
  const navigate = useNavigate()
  const { data: caseData, isLoading, error } = useCase(caseId)
  const { data: materialCandidates } = useMaterialCandidates(caseId)
  const { data: templateBindings } = useTemplateBindings(caseId)
  const { data: folderBinding } = useFolderBinding(caseId)
  const { data: accessGrants } = useAccessGrants(caseId)
  const { deleteCase } = useCaseMutations()
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [activeTab, setActiveTab] = useState('basic')

  const handleBack = useCallback(() => navigate(PATHS.ADMIN_CASES), [navigate])
  const handleEdit = useCallback(() => navigate(generatePath.caseEdit(caseId)), [navigate, caseId])

  const handleDelete = useCallback(async () => {
    try {
      await deleteCase.mutateAsync(caseId)
      toast.success('案件已删除')
      navigate(PATHS.ADMIN_CASES)
    } catch { toast.error('删除失败') }
  }, [deleteCase, caseId, navigate])

  if (isLoading) return <DetailSkeleton />

  if (error || !caseData) return (
    <div className="flex min-h-[400px] flex-col items-center justify-center">
      <FileWarning className="text-muted-foreground mb-4 size-16 opacity-50" />
      <h2 className="mb-2 text-xl font-semibold">案件不存在</h2>
      <p className="text-muted-foreground mb-6">您访问的案件可能已被删除或不存在</p>
      <Button onClick={handleBack} variant="outline"><ArrowLeft className="mr-2 size-4" />返回列表</Button>
    </div>
  )

  const statusKey = caseData.status as CaseStatus | null
  const statusLabel = statusKey ? (CASE_STATUS_LABELS[statusKey]?.zh ?? caseData.status) : null
  const typeLabel = caseData.case_type ? (SIMPLE_CASE_TYPE_LABELS[caseData.case_type]?.zh ?? caseData.case_type) : null
  const stageKey = caseData.current_stage as CaseStage | null
  const stageLabel = stageKey ? (CASE_STAGE_LABELS[stageKey]?.zh ?? caseData.current_stage) : null

  const primaryLawyer = caseData.assignments?.[0]

  return (
    <div className="space-y-0">
      {/* ── Page Header ── */}
      <div className="flex items-start justify-between flex-wrap gap-3 mb-5">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2.5 flex-wrap">
            <h1 className="text-lg font-semibold truncate">{caseData.name}</h1>
            <StatusBadge status={statusKey} label={statusLabel} />
            {typeLabel && <Badge variant="outline" className="text-[11px] px-2 py-0.5">{typeLabel}</Badge>}
            {stageLabel && <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-blue-50 text-blue-700">{stageLabel}</span>}
          </div>
          <div className="mt-1.5 flex items-center gap-4 text-[13px] text-muted-foreground flex-wrap">
            <span>主办律师：<span className="font-medium text-foreground">{primaryLawyer ? (primaryLawyer.lawyer_detail?.real_name || primaryLawyer.lawyer_detail?.username) : '未指派'}</span></span>
            <span>
              {caseData.is_filed ? (
                <span className="inline-flex items-center gap-1">
                  <span className="inline-block size-1.5 rounded-full bg-green-500" />
                  已建档{caseData.filing_number ? `：${caseData.filing_number}` : ''}
                </span>
              ) : (
                <span className="inline-flex items-center gap-1">
                  <span className="inline-block size-1.5 rounded-full bg-muted-foreground/40" />
                  未建档
                </span>
              )}
            </span>
          </div>
        </div>
        <div className="flex gap-2 shrink-0">
          <Button variant="outline" size="sm" className="h-8 text-xs" onClick={handleBack}>
            <ArrowLeft className="mr-1 size-3.5" />返回列表
          </Button>
          <Button variant="outline" size="sm" className="h-8 text-xs text-destructive hover:text-destructive hover:bg-destructive/10" onClick={() => setDeleteOpen(true)}>
            <Trash2 className="mr-1 size-3.5" />删除
          </Button>
          <Button size="sm" className="h-8 text-xs" onClick={handleEdit}>
            <Edit className="mr-1 size-3.5" />编辑
          </Button>
        </div>
      </div>

      {/* ── Tabs ── */}
      <div className="border-b border-border mb-5">
        <div className="flex gap-0 -mb-px overflow-x-auto">
          {TABS.map(tab => (
            <button
              key={tab.value}
              onClick={() => setActiveTab(tab.value)}
              className={`px-4 py-2.5 text-[13px] font-medium whitespace-nowrap border-b-2 transition-colors ${
                activeTab === tab.value
                  ? 'border-foreground text-foreground'
                  : 'border-transparent text-muted-foreground hover:text-foreground hover:bg-muted/50'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <AnimatePresence mode="wait">
        {/* ════════════════════════════════════════════ */}
        {/*  Tab: 基本信息                                */}
        {/* ════════════════════════════════════════════ */}
        {activeTab === 'basic' && (
          <motion.div key="basic" {...tabVariants} transition={tabTransition}>
            <div className="grid gap-4 lg:grid-cols-2">
              <DetailCard title="案件信息">
                <div className="grid gap-[14px] sm:grid-cols-2">
                  <DetailField label="案件名称" value={caseData.name} />
                  <DetailField label="案件类型" value={typeLabel} />
                  <DetailField label="案件状态" value={<StatusBadge status={statusKey} label={statusLabel} />} />
                  <DetailField label="案由" value={caseData.cause_of_action} />
                  <DetailField label="当前阶段" value={stageLabel} />
                  <DetailField label="标的金额" value={formatAmount(caseData.target_amount)} />
                  <DetailField label="保全金额" value={formatAmount(caseData.preservation_amount)} />
                  <DetailField label="关联合同" value={caseData.contract_id ? `合同 #${caseData.contract_id}` : '—'} />
                </div>
              </DetailCard>
              <DetailCard title="日期信息">
                <div className="grid gap-[14px] sm:grid-cols-2">
                  <DetailField label="收案日期" value={formatDateOnly(caseData.start_date)} mono />
                  <DetailField label="生效日期" value={formatDateOnly(caseData.effective_date)} mono />
                  <DetailField label="指定日期" value={formatDateOnly(caseData.specified_date)} mono />
                </div>
              </DetailCard>
            </div>

            <DetailCard title="案号" extra={<Hash className="text-muted-foreground size-4" />}>
              <CaseNumberSection
                caseNumbers={caseData.case_numbers ?? []}
                editable={false}
              />
            </DetailCard>

            <DetailCard title="主管机关" extra={<Building2 className="text-muted-foreground size-4" />}>
              <AuthoritySection authorities={caseData.supervising_authorities ?? []} editable={false} />
            </DetailCard>
          </motion.div>
        )}

        {/* ════════════════════════════════════════════ */}
        {/*  Tab: 当事人与律师                             */}
        {/* ════════════════════════════════════════════ */}
        {activeTab === 'parties' && (
          <motion.div key="parties" {...tabVariants} transition={tabTransition}>
            <DetailCard title="案件当事人">
              {caseData.parties?.length ? (
                <div className="flex flex-col gap-2">
                  {caseData.parties.map(party => {
                    const name = party.client_detail?.name ?? '未知当事人'
                    const legalStatusLabel = party.legal_status
                      ? (LEGAL_STATUS_LABELS[party.legal_status as keyof typeof LEGAL_STATUS_LABELS]?.zh ?? party.legal_status)
                      : null
                    const isOur = party.client_detail?.is_our_client
                    const roleColor = isOur ? 'bg-blue-50 text-blue-700' : 'bg-amber-50 text-amber-700'
                    return (
                      <div key={party.id} className="flex items-center gap-3 rounded-md border border-border/60 bg-muted/30 px-3 py-3 text-[13px]">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium ${roleColor}`}>
                          {isOur ? '我方' : '对方'}
                        </span>
                        <span className="font-semibold flex-1">{name}</span>
                        {legalStatusLabel && (
                          <Badge variant="outline" className="text-[11px] px-2 py-0.5">{legalStatusLabel}</Badge>
                        )}
                        <span className="text-muted-foreground text-xs">{party.client_detail?.client_type === 'natural' ? '自然人' : '法人/组织'}</span>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <p className="text-muted-foreground text-[13px]">暂无当事人</p>
              )}
            </DetailCard>

            <DetailCard title="律师指派">
              {caseData.assignments?.length ? (
                <div className="flex flex-col gap-2">
                  {caseData.assignments.map(a => (
                    <div key={a.id} className="flex items-center gap-3 rounded-md border border-border/60 bg-muted/30 px-3 py-3 text-[13px]">
                      <span className="font-semibold flex-1">{a.lawyer_detail?.real_name || a.lawyer_detail?.username || '未知'}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-muted-foreground text-[13px]">暂无指派律师</p>
              )}
            </DetailCard>

            <DetailCard title="案件授权">
              <CaseAccessGrantSection
                grants={accessGrants ?? []}
                editable={false}
              />
            </DetailCard>
          </motion.div>
        )}

        {/* ════════════════════════════════════════════ */}
        {/*  Tab: 工作人员                                */}
        {/* ════════════════════════════════════════════ */}
        {activeTab === 'contacts' && (
          <motion.div key="contacts" {...tabVariants} transition={tabTransition}>
            <DetailCard title="案件工作人员" extra={<Users className="text-muted-foreground size-4" />}>
              <CaseContactSection
                contacts={caseData.contacts ?? []}
                caseId={Number(caseId)}
                editable={true}
              />
            </DetailCard>
          </motion.div>
        )}

        {/* ════════════════════════════════════════════ */}
        {/*  Tab: 案件进展                                */}
        {/* ════════════════════════════════════════════ */}
        {activeTab === 'progress' && (
          <motion.div key="progress" {...tabVariants} transition={tabTransition}>
            <DetailCard title="案件日志">
              <CaseLogSection logs={caseData.logs ?? []} editable={false} />
            </DetailCard>

            <DetailCard title="案件群聊" extra={<MessageSquare className="text-muted-foreground size-4" />}>
              {caseData.chats?.length ? (
                <div className="flex flex-col gap-2">
                  {caseData.chats.map(chat => (
                    <div key={chat.id} className="flex items-center gap-3 rounded-md border border-border/60 bg-muted/30 px-3 py-2.5 text-[13px]">
                      <MessageSquare className="text-muted-foreground size-3.5 shrink-0" />
                      <span className="text-muted-foreground text-xs">{PLATFORM_LABELS[chat.platform] || chat.platform}</span>
                      <span className="font-medium flex-1">{chat.name}</span>
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium ${
                        chat.is_active ? 'bg-green-50 text-green-700' : 'bg-muted text-muted-foreground'
                      }`}>
                        {chat.is_active ? '有效' : '已失效'}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-muted-foreground text-[13px]">暂无关联群聊</p>
              )}
            </DetailCard>
          </motion.div>
        )}

        {/* ════════════════════════════════════════════ */}
        {/*  Tab: 文书模板                                */}
        {/* ════════════════════════════════════════════ */}
        {activeTab === 'documents' && (
          <motion.div key="documents" {...tabVariants} transition={tabTransition}>
            <DetailCard title="文书模板" extra={<FileText className="text-muted-foreground size-4" />}>
              <CaseTemplateSection
                categories={templateBindings?.categories ?? []}
                parties={caseData.parties ?? []}
                caseId={Number(caseId)}
              />
            </DetailCard>
          </motion.div>
        )}

        {/* ════════════════════════════════════════════ */}
        {/*  Tab: 材料管理                                */}
        {/* ════════════════════════════════════════════ */}
        {activeTab === 'materials' && (
          <motion.div key="materials" {...tabVariants} transition={tabTransition}>
            <DetailCard title="材料管理" extra={<Paperclip className="text-muted-foreground size-4" />}>
              <CaseMaterialSection
                candidates={materialCandidates ?? []}
                caseId={Number(caseId)}
              />
            </DetailCard>
          </motion.div>
        )}

        {/* ════════════════════════════════════════════ */}
        {/*  Tab: 文件夹                                  */}
        {/* ════════════════════════════════════════════ */}
        {activeTab === 'folder' && (
          <motion.div key="folder" {...tabVariants} transition={tabTransition}>
            <DetailCard title="文件夹管理" extra={<FolderOpen className="text-muted-foreground size-4" />}>
              <CaseFolderSection
                binding={folderBinding}
                caseId={Number(caseId)}
              />
            </DetailCard>
          </motion.div>
        )}

        {/* ════════════════════════════════════════════ */}
        {/*  Tab: 一张网立案                               */}
        {/* ════════════════════════════════════════════ */}
        {activeTab === 'court_filing' && (
          <motion.div key="court_filing" {...tabVariants} transition={tabTransition}>
            <DetailCard title="法院一张网在线立案" extra={<Landmark className="text-muted-foreground size-4" />}>
              <div className="rounded-md border border-border/60 bg-muted/30 px-4 py-3 mb-4">
                <div className="grid gap-3 sm:grid-cols-3 text-[13px]">
                  <div>
                    <span className="text-muted-foreground">案由：</span>
                    <span className="font-medium">{caseData.cause_of_action || '—'}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">管辖法院：</span>
                    <span className="font-medium">
                      {caseData.supervising_authorities?.find(a => a.authority_type === 'trial')?.name || '未设置'}
                    </span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">标的额：</span>
                    <span className="font-medium">{formatAmount(caseData.target_amount)}</span>
                  </div>
                </div>
              </div>

              <Button variant="outline" size="sm" className="h-8 text-xs" disabled>
                🚀 开始一张网立案
              </Button>
              <p className="text-muted-foreground text-xs mt-2">请先设置管辖法院（案件管辖机关）</p>
            </DetailCard>

            <DetailCard title="诉讼保全担保" extra={<FileText className="text-muted-foreground size-4" />}>
              <p className="text-muted-foreground text-[13px]">暂无保全担保信息</p>
            </DetailCard>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Delete Dialog ── */}
      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除案件</AlertDialogTitle>
            <AlertDialogDescription>删除「{caseData.name}」后，其关联数据将一并删除，且无法恢复。</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">确认删除</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

/* ── Skeleton ── */

function DetailSkeleton() {
  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between">
        <div className="space-y-3">
          <div className="bg-muted h-6 w-56 animate-pulse rounded" />
          <div className="bg-muted h-4 w-40 animate-pulse rounded" />
        </div>
        <div className="flex gap-2">
          <div className="bg-muted h-8 w-20 animate-pulse rounded-md" />
          <div className="bg-muted h-8 w-20 animate-pulse rounded-md" />
        </div>
      </div>
      <div className="bg-muted h-9 w-full max-w-lg animate-pulse rounded" />
      <div className="bg-muted h-64 w-full animate-pulse rounded-lg" />
    </div>
  )
}

export default CaseDetail
