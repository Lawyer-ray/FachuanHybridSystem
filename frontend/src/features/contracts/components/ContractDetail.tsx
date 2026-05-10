import { useCallback, useState } from 'react'
import { copyToClipboard } from '@/lib/clipboard'
import { useNavigate } from 'react-router'
import { AnimatePresence, motion } from 'framer-motion'
import {
  ArrowLeft, Edit, Trash2, FileWarning,
  MoreHorizontal, FileText, Briefcase, Copy, RefreshCw, Loader2,
  User, Scale,
} from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from '@/components/ui/sheet'
import { PATHS, generatePath } from '@/routes/paths'
import { DetailField, DetailCard, StatusBadge } from '@/components/shared'
import { formatAmount, formatAmountInt } from '@/lib/format'
import { downloadBlob } from '@/lib/download'

import { useContract } from '../hooks/use-contract'
import { useContractMutations } from '../hooks/use-contract-mutations'
import { contractApi } from '../api'
import { SupplementaryAgreementList } from './SupplementaryAgreementList'
import { FeesTab } from './FeesTab'
import { FilingTab } from './FilingTab'
import { DocumentsTab } from './DocumentsTab'
import { ArchiveTab } from './ArchiveTab'
import {
  FEE_MODE_LABELS, CONTRACT_STATUS_LABELS, CASE_TYPE_LABELS,
  type FeeMode, type ContractStatus, type CaseType,
  type ContractParty, type ContractAssignment,
} from '../types'

export interface ContractDetailProps { contractId: string }

/* ── Shared helpers ── */

function ContractStatusBadge({ status, label }: { status: string | null; label?: string | null }) {
  if (!status) return <StatusBadge variant="closed">未设置</StatusBadge>
  const variant = status === 'active'
    ? 'active'
    : status === 'closed' || status === 'archived'
      ? 'closed'
      : 'pending'
  return <StatusBadge variant={variant}>{label || status}</StatusBadge>
}

/* ── Tabs config ── */

const TABS = [
  { value: 'basic', label: '基本信息' },
  { value: 'parties', label: '当事人与律师' },
  { value: 'fees', label: '收费与财务' },
  { value: 'filing', label: '立案' },
  { value: 'documents', label: '文档与提醒' },
  { value: 'archive', label: '归档' },
]

const tabVariants = {
  initial: { opacity: 0, y: 4 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -3 },
}

const tabTransition = { duration: 0.15, ease: 'easeOut' as const }

/* ── Main component ── */

export function ContractDetail({ contractId }: ContractDetailProps) {
  const navigate = useNavigate()
  const { data: contract, isLoading, error } = useContract(contractId)
  const { deleteContract, duplicateContract, createCaseFromContract } = useContractMutations()
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [activeTab, setActiveTab] = useState('basic')
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [selectedParty, setSelectedParty] = useState<ContractParty | null>(null)
  const [selectedLawyer, setSelectedLawyer] = useState<ContractAssignment | null>(null)

  const handleBack = useCallback(() => navigate(PATHS.ADMIN_CONTRACTS), [navigate])
  const handleEdit = useCallback(() => navigate(generatePath.contractEdit(contractId)), [navigate, contractId])

  const handleDelete = useCallback(async () => {
    try {
      await deleteContract.mutateAsync(contractId)
      toast.success('合同已删除')
      navigate(PATHS.ADMIN_CONTRACTS)
    } catch { toast.error('删除失败') }
  }, [deleteContract, contractId, navigate])

  const handleAction = useCallback(async (action: string) => {
    setActionLoading(action)
    try {
      switch (action) {
        case 'generate-doc': {
          const res = await contractApi.generateContract(contractId)
          const ct = res.headers.get('content-type')
          if (ct && ct.includes('application/json')) {
            const data = await res.json() as { message?: string }
            toast.success(data.message || '合同已生成并保存')
          } else {
            const blob = await res.blob()
            downloadBlob(blob, `合同_${contract?.name ?? contractId}.docx`)
            toast.success('合同生成成功，已开始下载')
          }
          break
        }
        case 'create-case': {
          const res = await createCaseFromContract.mutateAsync(contractId)
          toast.success(res.message || '案件已创建')
          break
        }
        case 'duplicate': {
          const newContract = await duplicateContract.mutateAsync(contractId)
          toast.success('合同已复制')
          navigate(generatePath.contractDetail(newContract.id))
          break
        }
        case 'renew': {
          navigate(generatePath.contractEdit(contractId) + '?renew=true')
          break
        }
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '操作失败'
      toast.error(msg)
    } finally {
      setActionLoading(null)
    }
  }, [contractId, contract, createCaseFromContract, duplicateContract, navigate])

  if (isLoading) return <DetailSkeleton />

  if (error || !contract) return (
    <div className="flex min-h-[400px] flex-col items-center justify-center">
      <FileWarning className="text-muted-foreground mb-4 size-16 opacity-50" />
      <h2 className="mb-2 text-xl font-semibold">合同不存在</h2>
      <p className="text-muted-foreground mb-6">您访问的合同可能已被删除或不存在</p>
      <Button onClick={handleBack} variant="outline"><ArrowLeft className="mr-2 size-4" />返回列表</Button>
    </div>
  )

  const statusKey = contract.status as ContractStatus
  const statusLabel = CONTRACT_STATUS_LABELS[statusKey] ?? contract.status
  const typeLabel = CASE_TYPE_LABELS[contract.case_type as CaseType] ?? contract.case_type
  const feeLabel = FEE_MODE_LABELS[contract.fee_mode as FeeMode] ?? contract.fee_mode

  const primaryLawyer = contract.assignments?.find(a => a.is_primary)

  return (
    <div className="space-y-0">
      {/* ── Page Header ── */}
      <div className="flex items-start justify-between flex-wrap gap-3 mb-5">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2.5 flex-wrap">
            <h1 className="text-lg font-semibold truncate">{contract.name}</h1>
            <ContractStatusBadge status={statusKey} label={statusLabel} />
            {typeLabel && <Badge variant="outline" className="text-[11px] px-2 py-0.5">{typeLabel}</Badge>}
            {contract.is_filed && <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-blue-50 text-blue-700">已建档</span>}
          </div>
          <div className="mt-1.5 flex items-center gap-4 text-[13px] text-muted-foreground flex-wrap">
            <span>主办律师：<span className="font-medium text-foreground">{primaryLawyer ? primaryLawyer.lawyer_name : '未指派'}</span></span>
            <span>
              {contract.is_filed ? (
                <span className="inline-flex items-center gap-1">
                  <span className="inline-block size-1.5 rounded-full bg-green-500" />
                  已建档
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

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" className="h-8 text-xs" disabled={!!actionLoading}>
                {actionLoading ? <Loader2 className="mr-1 size-3.5 animate-spin" /> : <MoreHorizontal className="mr-1 size-3.5" />}
                更多操作
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => handleAction('generate-doc')}>
                <FileText className="mr-2 size-4" />生成合同文档
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => handleAction('create-case')}>
                <Briefcase className="mr-2 size-4" />创建关联案件
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => handleAction('duplicate')}>
                <Copy className="mr-2 size-4" />复制合同
              </DropdownMenuItem>
              {contract.case_type === 'advisor' && (
                <DropdownMenuItem onClick={() => handleAction('renew')}>
                  <RefreshCw className="mr-2 size-4" />续签顾问合同
                </DropdownMenuItem>
              )}
            </DropdownMenuContent>
          </DropdownMenu>

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
              <DetailCard title="合同信息">
                <div className="grid gap-[14px] sm:grid-cols-2">
                  <DetailField label="合同名称" value={contract.name} />
                  <DetailField label="案件类型" value={typeLabel} />
                  <DetailField label="合同状态" value={<ContractStatusBadge status={statusKey} label={statusLabel} />} />
                  <DetailField label="收费模式" value={<Badge variant="outline" className="text-[11px] px-2 py-0.5">{feeLabel}</Badge>} />
                  <DetailField label="固定/前期金额" value={formatAmount(contract.fixed_amount)} />
                  <DetailField label="风险比例" value={contract.risk_rate != null ? `${contract.risk_rate}%` : '—'} />
                </div>
              </DetailCard>
              <DetailCard title="日期与期限">
                <div className="grid gap-[14px] sm:grid-cols-2">
                  <DetailField label="指定日期" value={contract.specified_date} mono />
                  <DetailField label="合同期限" value={`${contract.start_date || '—'} ~ ${contract.end_date || '—'}`} mono />
                  <DetailField label="代理阶段" value={contract.representation_stages.length > 0 ? contract.representation_stages.join('、') : '—'} />
                  <DetailField label="是否建档" value={contract.is_filed ? '是' : '否'} />
                  <DetailField label="自定义条款" value={contract.custom_terms} />
                </div>
              </DetailCard>
            </div>

            {contract.cases.length > 0 && (
              <DetailCard title="关联案件" extra={<Briefcase className="text-muted-foreground size-4" />}>
                <div className="flex flex-col gap-2">
                  {contract.cases.map((cs) => (
                    <div key={cs.id} className="flex items-center gap-3 rounded-md border border-border/60 bg-muted/30 px-3 py-3 text-[13px]">
                      <Briefcase className="text-muted-foreground size-3.5 shrink-0" />
                      <span className="font-medium flex-1 truncate">{cs.name}</span>
                      {cs.cause_of_action && <span className="text-muted-foreground text-xs shrink-0">{cs.cause_of_action}</span>}
                      {cs.status_label && <Badge variant="outline" className="text-[11px] px-2 py-0.5 shrink-0">{cs.status_label}</Badge>}
                      {cs.target_amount != null && <span className="text-muted-foreground shrink-0">{formatAmountInt(cs.target_amount)}</span>}
                    </div>
                  ))}
                </div>
              </DetailCard>
            )}
          </motion.div>
        )}

        {/* ════════════════════════════════════════════ */}
        {/*  Tab: 当事人与律师                             */}
        {/* ════════════════════════════════════════════ */}
        {activeTab === 'parties' && (
          <motion.div key="parties" {...tabVariants} transition={tabTransition}>
            <DetailCard title="合同当事人">
              {contract.contract_parties.length === 0 ? (
                <p className="text-muted-foreground text-[13px]">暂无当事人</p>
              ) : (
                <div className="flex flex-col gap-2">
                  {contract.contract_parties.map((p) => (
                    <div
                      key={p.id}
                      className="flex items-center gap-3 rounded-md border border-border/60 bg-muted/30 px-3 py-3 text-[13px] cursor-pointer hover:bg-muted/60 transition-colors"
                      onClick={() => setSelectedParty(p)}
                    >
                      <User className="size-3.5 text-muted-foreground shrink-0" />
                      <span className="font-semibold flex-1">{p.client_detail.name}</span>
                      <Badge variant="outline" className="text-[11px] px-2 py-0.5">{p.role_label}</Badge>
                      <Badge variant={p.client_detail.is_our_client ? 'default' : 'secondary'} className="text-[10px] px-1.5 py-0">
                        {p.client_detail.is_our_client ? '我方' : '对方'}
                      </Badge>
                    </div>
                  ))}
                </div>
              )}
            </DetailCard>

            <DetailCard title="律师指派">
              {contract.assignments.length === 0 ? (
                <p className="text-muted-foreground text-[13px]">暂无指派律师</p>
              ) : (
                <div className="flex flex-col gap-2">
                  {contract.assignments.map((a) => (
                    <div
                      key={a.id}
                      className="flex items-center gap-3 rounded-md border border-border/60 bg-muted/30 px-3 py-3 text-[13px] cursor-pointer hover:bg-muted/60 transition-colors"
                      onClick={() => setSelectedLawyer(a)}
                    >
                      <User className="size-3.5 text-muted-foreground shrink-0" />
                      <span className="font-semibold flex-1">{a.lawyer_name}</span>
                      <Badge variant={a.is_primary ? 'default' : 'secondary'} className="text-[11px] px-2 py-0.5">
                        {a.is_primary ? '主办' : '协办'}
                      </Badge>
                    </div>
                  ))}
                </div>
              )}
            </DetailCard>

            {contract.supplementary_agreements.length > 0 && (
              <DetailCard title="补充协议">
                <SupplementaryAgreementList contractId={contract.id} agreements={contract.supplementary_agreements} />
              </DetailCard>
            )}

            {/* Party Detail Sheet */}
            <Sheet open={!!selectedParty} onOpenChange={(open) => !open && setSelectedParty(null)}>
              <SheetContent className="sm:max-w-md">
                <SheetHeader className="pb-0">
                  <SheetTitle className="text-base">{selectedParty?.client_detail.name}</SheetTitle>
                  <SheetDescription>
                    {selectedParty?.client_detail.client_type_label}
                  </SheetDescription>
                </SheetHeader>
                {selectedParty && (() => {
                  const d = selectedParty.client_detail
                  const isNatural = d.client_type === 'natural'
                  const CopyableField = ({ label, value }: { label: string; value: string | null | undefined }) => {
                    if (!value) return null
                    return (
                      <div className="flex items-center justify-between py-2.5 border-b border-border/40 last:border-b-0">
                        <span className="text-xs text-muted-foreground shrink-0 w-24">{label}</span>
                        <span className="text-[13px] font-mono text-right flex-1 min-w-0 truncate">{value}</span>
                        <button
                          className="ml-2 p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors shrink-0"
                          onClick={() => copyToClipboard(String(value))}
                        >
                          <Copy className="size-3" />
                        </button>
                      </div>
                    )
                  }

                  return (
                    <div className="mt-4 flex flex-col h-full">
                      {/* Badges */}
                      <div className="flex items-center gap-2 mb-4 px-1">
                        <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${
                          d.is_our_client ? 'bg-primary/10 text-primary' : 'bg-orange-50 text-orange-700'
                        }`}>
                          {d.is_our_client ? '我方当事人' : '对方当事人'}
                        </span>
                        <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-muted text-muted-foreground">
                          {selectedParty.role_label}
                        </span>
                      </div>

                      {/* Fields */}
                      <div className="rounded-lg border border-border/60 bg-muted/20 px-4 py-1 mb-4">
                        <CopyableField label="主体类型" value={d.client_type_label} />
                        <CopyableField label="当事人角色" value={selectedParty.role_label} />
                        <CopyableField label={isNatural ? '身份证号码' : '统一社会信用代码'} value={d.id_number} />
                        <CopyableField label="联系电话" value={d.phone} />
                        <CopyableField label="住所地" value={d.address} />
                      </div>

                      {/* Legal Representative Section */}
                      {!isNatural && d.legal_representative && (
                        <>
                          <div className="flex items-center gap-2 mb-3 px-1">
                            <Scale className="size-3.5 text-muted-foreground" />
                            <span className="text-xs font-semibold text-foreground">
                              {d.client_type === 'legal' ? '法定代表人信息' : '负责人信息'}
                            </span>
                          </div>
                          <div className="rounded-lg border border-border/60 bg-muted/20 px-4 py-1 mb-4">
                            <CopyableField label="姓名" value={d.legal_representative} />
                            <CopyableField label="身份证号码" value={d.legal_representative_id_number} />
                          </div>
                        </>
                      )}

                      {/* Copy All Button */}
                      <div className="mt-auto pt-3 border-t border-border/40 flex justify-end">
                        <button
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground hover:bg-muted/60 rounded-md transition-colors"
                          onClick={() => {
                            const lines = isNatural
                              ? [
                                  d.name ? `姓名：${d.name}` : null,
                                  d.id_number ? `身份证号码：${d.id_number}` : null,
                                  d.phone ? `联系电话：${d.phone}` : null,
                                  d.address ? `住所地：${d.address}` : null,
                                ]
                              : [
                                  d.name ? `名称：${d.name}` : null,
                                  d.id_number ? `统一社会信用代码：${d.id_number}` : null,
                                  d.legal_representative ? `法定代表人：${d.legal_representative}` : null,
                                  d.phone ? `联系电话：${d.phone}` : null,
                                  d.address ? `住所地：${d.address}` : null,
                                ]
                            const text = lines.filter(Boolean).join('\n')
                            if (text) copyToClipboard(text, '已复制全部信息')
                          }}
                        >
                          <Copy className="size-3" />复制全部
                        </button>
                      </div>
                    </div>
                  )
                })()}
              </SheetContent>
            </Sheet>

            {/* Lawyer Detail Sheet */}
            <Sheet open={!!selectedLawyer} onOpenChange={(open) => !open && setSelectedLawyer(null)}>
              <SheetContent className="sm:max-w-md">
                <SheetHeader className="pb-0">
                  <SheetTitle className="text-base">{selectedLawyer?.lawyer_name}</SheetTitle>
                  <SheetDescription>
                    {selectedLawyer?.is_primary ? '主办律师' : '协办律师'}
                  </SheetDescription>
                </SheetHeader>
                {selectedLawyer && (
                  <div className="mt-4 flex flex-col h-full">
                    {/* Badge */}
                    <div className="flex items-center gap-2 mb-4 px-1">
                      <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${
                        selectedLawyer.is_primary ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground'
                      }`}>
                        {selectedLawyer.is_primary ? '主办律师' : '协办律师'}
                      </span>
                    </div>

                    {/* Fields */}
                    <div className="rounded-lg border border-border/60 bg-muted/20 px-4 py-1 mb-4">
                      <div className="flex items-center justify-between py-2.5 border-b border-border/40">
                        <span className="text-xs text-muted-foreground shrink-0 w-24">姓名</span>
                        <span className="text-[13px] text-right flex-1 min-w-0 truncate">{selectedLawyer.lawyer_name}</span>
                        <button
                          className="ml-2 p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors shrink-0"
                          onClick={() => copyToClipboard(selectedLawyer.lawyer_name)}
                        >
                          <Copy className="size-3" />
                        </button>
                      </div>
                      <div className="flex items-center justify-between py-2.5 border-b border-border/40 last:border-b-0">
                        <span className="text-xs text-muted-foreground shrink-0 w-24">律师 ID</span>
                        <span className="text-[13px] font-mono text-right flex-1 min-w-0 truncate">{selectedLawyer.lawyer_id}</span>
                        <button
                          className="ml-2 p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors shrink-0"
                          onClick={() => copyToClipboard(String(selectedLawyer.lawyer_id))}
                        >
                          <Copy className="size-3" />
                        </button>
                      </div>
                    </div>

                    {/* Copy All Button */}
                    <div className="mt-auto pt-3 border-t border-border/40 flex justify-end">
                      <button
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground hover:bg-muted/60 rounded-md transition-colors"
                        onClick={() => {
                          const lines = [
                            `姓名：${selectedLawyer.lawyer_name}`,
                            `角色：${selectedLawyer.is_primary ? '主办律师' : '协办律师'}`,
                            `律师 ID：${selectedLawyer.lawyer_id}`,
                          ].join('\n')
                          copyToClipboard(lines, '已复制全部信息')
                          toast.success('已复制全部信息')
                        }}
                      >
                        <Copy className="size-3" />复制全部
                      </button>
                    </div>
                  </div>
                )}
              </SheetContent>
            </Sheet>
          </motion.div>
        )}

        {/* ════════════════════════════════════════════ */}
        {/*  Tab: 收费/财务                               */}
        {/* ════════════════════════════════════════════ */}
        {activeTab === 'fees' && (
          <motion.div key="fees" {...tabVariants} transition={tabTransition}>
            <FeesTab contract={contract} />
          </motion.div>
        )}

        {/* ════════════════════════════════════════════ */}
        {/*  Tab: 立案/OA                                 */}
        {/* ════════════════════════════════════════════ */}
        {activeTab === 'filing' && (
          <motion.div key="filing" {...tabVariants} transition={tabTransition}>
            <FilingTab contract={contract} />
          </motion.div>
        )}

        {/* ════════════════════════════════════════════ */}
        {/*  Tab: 文书/提醒                               */}
        {/* ════════════════════════════════════════════ */}
        {activeTab === 'documents' && (
          <motion.div key="documents" {...tabVariants} transition={tabTransition}>
            <DocumentsTab contract={contract} />
          </motion.div>
        )}

        {/* ════════════════════════════════════════════ */}
        {/*  Tab: 归档清单                                */}
        {/* ════════════════════════════════════════════ */}
        {activeTab === 'archive' && (
          <motion.div key="archive" {...tabVariants} transition={tabTransition}>
            <ArchiveTab contract={contract} />
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Delete Dialog ── */}
      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除合同</AlertDialogTitle>
            <AlertDialogDescription>删除「{contract.name}」后，其关联数据将一并删除，且无法恢复。</AlertDialogDescription>
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

export default ContractDetail
