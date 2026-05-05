import { useCallback, useState } from 'react'
import { useNavigate } from 'react-router'
import { AnimatePresence, motion } from 'framer-motion'
import {
  ArrowLeft, Edit, Trash2, Copy, FileWarning,
  User, Building2, Briefcase, FileText, ExternalLink,
} from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { PATHS, generatePath } from '@/routes/paths'

import { useClient } from '../hooks/use-client'
import { useClientMutations } from '../hooks/use-client-mutations'
import { useRelatedItems } from '../hooks/use-related-items'
import { PropertyClueList } from './PropertyClueList'
import { IdentityDocManager } from './IdentityDocManager'
import { CLIENT_TYPE_LABELS } from '../types'
import { formatClientText } from '../utils/format-client-text'
import type { ClientType } from '../types'

export interface ClientDetailProps { clientId: string }

/* ── Shared helpers (matching ContractDetail style) ── */

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

/* ── Helpers ── */

function getIdNumberLabel(ct: ClientType) {
  return ct === 'natural' ? '身份证号' : '统一社会信用代码'
}

function getLegalRepLabel(ct: ClientType) {
  return ct === 'non_legal_org' ? '负责人' : '法定代表人'
}

/* ── Tabs config ── */

const TABS = [
  { value: 'basic', label: '基本信息' },
  { value: 'docs', label: '证件管理' },
  { value: 'clues', label: '财产线索' },
  { value: 'related', label: '关联案件/合同' },
]

const tabVariants = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -6 },
}

const tabTransition = { duration: 0.2, ease: 'easeInOut' as const }

/* ── Main component ── */

export function ClientDetail({ clientId }: ClientDetailProps) {
  const navigate = useNavigate()
  const { data: client, isLoading, error } = useClient(clientId)
  const { deleteClient } = useClientMutations()
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [activeTab, setActiveTab] = useState('basic')

  const { data: relatedItems } = useRelatedItems(clientId)

  const handleEdit = useCallback(() => navigate(generatePath.clientEdit(clientId)), [navigate, clientId])
  const handleBack = useCallback(() => navigate(PATHS.ADMIN_CLIENTS), [navigate])
  const handleCopy = useCallback(() => {
    if (!client) return
    navigator.clipboard.writeText(formatClientText(client))
    toast.success('已复制当事人信息')
  }, [client])
  const handleDelete = useCallback(async () => {
    try {
      await deleteClient.mutateAsync(clientId)
      toast.success('当事人已删除')
      navigate(PATHS.ADMIN_CLIENTS)
    } catch { toast.error('删除失败') }
  }, [deleteClient, clientId, navigate])

  if (isLoading) return <DetailSkeleton />

  if (error || !client) return (
    <div className="flex min-h-[400px] flex-col items-center justify-center">
      <FileWarning className="text-muted-foreground mb-4 size-16 opacity-50" />
      <h2 className="mb-2 text-xl font-semibold">当事人不存在</h2>
      <p className="text-muted-foreground mb-6">您访问的当事人可能已被删除或不存在</p>
      <Button onClick={handleBack} variant="outline"><ArrowLeft className="mr-2 size-4" />返回列表</Button>
    </div>
  )

  const showLegalRep = client.client_type !== 'natural'
  const typeLabel = CLIENT_TYPE_LABELS[client.client_type]
  const TypeIcon = client.client_type === 'natural' ? User : Building2

  return (
    <div className="space-y-0">
      {/* ── Page Header ── */}
      <div className="flex items-start justify-between flex-wrap gap-3 mb-5">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2.5 flex-wrap">
            <h1 className="text-lg font-semibold truncate">{client.name}</h1>
            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium ${
              client.client_type === 'natural' ? 'bg-blue-50 text-blue-700' : 'bg-purple-50 text-purple-700'
            }`}>
              {typeLabel}
            </span>
            {client.is_our_client && (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-green-50 text-green-700">
                我方当事人
              </span>
            )}
          </div>
          <div className="mt-1.5 flex items-center gap-4 text-[13px] text-muted-foreground flex-wrap">
            {client.id_number && (
              <span className="font-mono">{client.id_number}</span>
            )}
            {client.phone && (
              <span>{client.phone}</span>
            )}
          </div>
        </div>
        <div className="flex gap-2 shrink-0">
          <Button variant="outline" size="sm" className="h-8 text-xs" onClick={handleBack}>
            <ArrowLeft className="mr-1 size-3.5" />返回列表
          </Button>
          <Button variant="outline" size="sm" className="h-8 text-xs" onClick={handleCopy}>
            <Copy className="mr-1 size-3.5" />复制
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
              <DetailCard title="基本信息">
                <div className="grid gap-[14px] sm:grid-cols-2">
                  <DetailField label="姓名" value={client.name} />
                  <DetailField label="当事人类型" value={
                    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium ${
                      client.client_type === 'natural' ? 'bg-blue-50 text-blue-700' : 'bg-purple-50 text-purple-700'
                    }`}>
                      <TypeIcon className="size-3 mr-1" />
                      {typeLabel}
                    </span>
                  } />
                  <DetailField label={getIdNumberLabel(client.client_type)} value={client.id_number} mono />
                  <DetailField label="手机号" value={client.phone} mono />
                  <DetailField label="地址" value={client.address} />
                  <DetailField label="是否我方当事人" value={client.is_our_client ? '是' : '否'} />
                </div>
              </DetailCard>

              <DetailCard title={showLegalRep ? '法定代表人/负责人' : '附加信息'}>
                <div className="grid gap-[14px] sm:grid-cols-2">
                  {showLegalRep ? (
                    <>
                      <DetailField label={getLegalRepLabel(client.client_type)} value={client.legal_representative} />
                      <DetailField label={`${getLegalRepLabel(client.client_type)}身份证号`} value={client.legal_representative_id_number} mono />
                    </>
                  ) : (
                    <>
                      <DetailField label="创建时间" value={client.created_at ? new Date(client.created_at).toLocaleDateString('zh-CN') : '—'} mono />
                      <DetailField label="证件数量" value={client.identity_docs?.length ?? 0} />
                    </>
                  )}
                </div>
              </DetailCard>
            </div>
          </motion.div>
        )}

        {/* ════════════════════════════════════════════ */}
        {/*  Tab: 证件管理                                */}
        {/* ════════════════════════════════════════════ */}
        {activeTab === 'docs' && (
          <motion.div key="docs" {...tabVariants} transition={tabTransition}>
            <IdentityDocManager clientId={clientId} clientType={client.client_type} docs={client.identity_docs} />
          </motion.div>
        )}

        {/* ════════════════════════════════════════════ */}
        {/*  Tab: 财产线索                                */}
        {/* ════════════════════════════════════════════ */}
        {activeTab === 'clues' && (
          <motion.div key="clues" {...tabVariants} transition={tabTransition}>
            <PropertyClueList clientId={client.id} />
          </motion.div>
        )}

        {/* ════════════════════════════════════════════ */}
        {/*  Tab: 关联案件/合同                            */}
        {/* ════════════════════════════════════════════ */}
        {activeTab === 'related' && (
          <motion.div key="related" {...tabVariants} transition={tabTransition}>
            {/* 关联案件 */}
            <DetailCard title="关联案件" extra={<Briefcase className="text-muted-foreground size-4" />}>
              {!relatedItems || relatedItems.cases.length === 0 ? (
                <p className="text-muted-foreground text-[13px]">暂无关联案件</p>
              ) : (
                <div className="flex flex-col gap-2">
                  {relatedItems.cases.map((cs) => (
                    <a
                      key={cs.id}
                      href={generatePath.caseDetail(String(cs.id))}
                      className="flex items-center gap-3 rounded-md border border-border/60 bg-muted/30 px-3 py-3 text-[13px] hover:bg-muted/50 transition-colors"
                    >
                      <Briefcase className="text-muted-foreground size-3.5 shrink-0" />
                      <span className="font-medium flex-1 truncate">{cs.name}</span>
                      {cs.current_stage && <Badge variant="outline" className="text-[11px] px-2 py-0.5 shrink-0">{cs.current_stage}</Badge>}
                      {cs.legal_status && <Badge variant="secondary" className="text-[11px] px-2 py-0.5 shrink-0">{cs.legal_status}</Badge>}
                      <ExternalLink className="text-muted-foreground size-3 shrink-0" />
                    </a>
                  ))}
                </div>
              )}
            </DetailCard>

            {/* 关联合同 */}
            <DetailCard title="关联合同" extra={<FileText className="text-muted-foreground size-4" />}>
              {!relatedItems || relatedItems.contracts.length === 0 ? (
                <p className="text-muted-foreground text-[13px]">暂无关联合同</p>
              ) : (
                <div className="flex flex-col gap-2">
                  {relatedItems.contracts.map((ct) => (
                    <a
                      key={ct.id}
                      href={generatePath.contractDetail(String(ct.id))}
                      className="flex items-center gap-3 rounded-md border border-border/60 bg-muted/30 px-3 py-3 text-[13px] hover:bg-muted/50 transition-colors"
                    >
                      <FileText className="text-muted-foreground size-3.5 shrink-0" />
                      <span className="font-medium flex-1 truncate">{ct.name}</span>
                      {ct.role && <Badge variant="outline" className="text-[11px] px-2 py-0.5 shrink-0">{ct.role}</Badge>}
                      <ExternalLink className="text-muted-foreground size-3 shrink-0" />
                    </a>
                  ))}
                </div>
              )}
            </DetailCard>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Delete Dialog ── */}
      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除当事人</AlertDialogTitle>
            <AlertDialogDescription>删除「{client.name}」后，其关联数据将一并删除，且无法恢复。</AlertDialogDescription>
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

export default ClientDetail
