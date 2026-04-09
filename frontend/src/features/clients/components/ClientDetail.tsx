/**
 * ClientDetail - 当事人详情组件
 */

import { useCallback, useState } from 'react'
import { useNavigate } from 'react-router'
import {
  ArrowLeft, Edit, User, Building2, Phone, MapPin, CreditCard, UserCheck, FileWarning, Trash2, Copy,
} from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { Badge } from '@/components/ui/badge'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { PATHS, generatePath } from '@/routes/paths'

import { useClient } from '../hooks/use-client'
import { useClientMutations } from '../hooks/use-client-mutations'
import { PropertyClueList } from './PropertyClueList'
import { IdentityDocManager } from './IdentityDocManager'
import { CLIENT_TYPE_LABELS } from '../types'
import { formatClientText } from '../utils/format-client-text'
import type { ClientType } from '../types'

export interface ClientDetailProps {
  clientId: string
}

function getIdNumberLabel(ct: ClientType) {
  return ct === 'natural' ? '身份证号' : '统一社会信用代码'
}

function getLegalRepLabel(ct: ClientType) {
  return ct === 'non_legal_org' ? '负责人' : '法定代表人'
}

function InfoItem({ icon: Icon, label, value, mono }: {
  icon: React.ElementType; label: string; value: string | null | undefined; mono?: boolean
}) {
  const isEmpty = !value
  return (
    <div className="space-y-1.5">
      <div className="text-muted-foreground flex items-center gap-1.5 text-sm">
        <Icon className="size-4" /><span>{label}</span>
      </div>
      <p className={`text-sm ${isEmpty ? 'text-muted-foreground' : 'text-foreground'} ${mono && !isEmpty ? 'font-mono' : ''}`}>
        {value || '未填写'}
      </p>
    </div>
  )
}

export function ClientDetail({ clientId }: ClientDetailProps) {
  const navigate = useNavigate()
  const { data: client, isLoading, error } = useClient(clientId)
  const { deleteClient } = useClientMutations()
  const [deleteOpen, setDeleteOpen] = useState(false)

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
    } catch {
      toast.error('删除失败')
    }
  }, [deleteClient, clientId, navigate])

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="bg-muted h-4 w-40 animate-pulse rounded" />
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
        <div className="bg-muted h-64 w-full animate-pulse rounded-lg" />
      </div>
    )
  }

  if (error || !client) {
    return (
      <div className="flex min-h-[400px] flex-col items-center justify-center">
        <FileWarning className="text-muted-foreground mb-4 size-16 opacity-50" />
        <h2 className="mb-2 text-xl font-semibold">当事人不存在</h2>
        <p className="text-muted-foreground mb-6">您访问的当事人可能已被删除或不存在</p>
        <Button onClick={handleBack} variant="outline"><ArrowLeft className="mr-2 size-4" />返回列表</Button>
      </div>
    )
  }

  const TypeIcon = client.client_type === 'natural' ? User : Building2
  const showLegalRep = client.client_type !== 'natural'

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <nav className="text-sm" aria-label="Breadcrumb">
        <ol className="flex items-center gap-1.5">
          <li>
            <span className="text-muted-foreground hover:text-foreground cursor-pointer transition-colors" onClick={handleBack}>
              当事人
            </span>
          </li>
          <li className="text-muted-foreground">/</li>
          <li className="text-foreground truncate max-w-[300px]">{client.name}</li>
        </ol>
      </nav>

      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3 min-w-0">
          <div className="bg-primary/10 flex size-10 items-center justify-center rounded-full shrink-0">
            <TypeIcon className="text-primary size-5" />
          </div>
          <div className="min-w-0">
            <h1 className="text-xl font-semibold truncate">{client.name}</h1>
            <div className="mt-1 flex items-center gap-2">
              <Badge variant={client.client_type === 'natural' ? 'default' : 'secondary'} className="text-xs">
                {CLIENT_TYPE_LABELS[client.client_type]}
              </Badge>
              {client.is_our_client && <Badge variant="outline" className="text-xs">我方当事人</Badge>}
            </div>
          </div>
        </div>
        <div className="flex gap-2 shrink-0">
          <Button variant="outline" onClick={handleBack}>
            <ArrowLeft className="mr-2 size-4" />返回
          </Button>
          <Button variant="outline" onClick={handleCopy} className="transition-colors">
            <Copy className="mr-2 size-4" />复制
          </Button>
          <Button
            variant="outline"
            onClick={() => setDeleteOpen(true)}
            className="text-destructive hover:text-destructive hover:bg-destructive/10 transition-colors"
          >
            <Trash2 className="mr-2 size-4" />删除
          </Button>
          <Button onClick={handleEdit} className="transition-colors">
            <Edit className="mr-2 size-4" />编辑
          </Button>
        </div>
      </div>

      <Separator />

      {/* Basic Info */}
      <Card>
        <CardHeader><CardTitle className="text-base">基本信息</CardTitle></CardHeader>
        <CardContent>
          <div className="grid gap-6 sm:grid-cols-2">
            <InfoItem icon={User} label="姓名" value={client.name} />
            <InfoItem icon={CreditCard} label={getIdNumberLabel(client.client_type)} value={client.id_number} mono />
            <InfoItem icon={Phone} label="手机号" value={client.phone} mono />
            <InfoItem icon={MapPin} label="地址" value={client.address} />
            {showLegalRep && (
              <InfoItem icon={UserCheck} label={getLegalRepLabel(client.client_type)} value={client.legal_representative} />
            )}
          </div>
        </CardContent>
      </Card>

      {/* Property Clues */}
      <PropertyClueList clientId={client.id} />

      {/* Identity Docs */}
      <IdentityDocManager clientId={clientId} clientType={client.client_type} docs={client.identity_docs} />

      {/* Delete Confirmation */}
      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除当事人</AlertDialogTitle>
            <AlertDialogDescription>
              删除「{client.name}」后，其关联的证件、财产线索等数据将一并删除，且无法恢复。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
              确认删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

export default ClientDetail
