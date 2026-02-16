/**
 * ClientDetail Component
 *
 * 当事人详情组件
 * - 显示当事人基本信息
 * - 条件显示法定代表人（法人/非法人组织）
 * - 渲染 IdentityDocList
 * - 实现编辑和返回按钮
 *
 * Requirements: 4.1, 4.2, 4.5, 4.6, 4.7, 4.8
 */

import { useCallback } from 'react'
import { useNavigate } from 'react-router'
import {
  ArrowLeft,
  Edit,
  User,
  Building2,
  Phone,
  MapPin,
  CreditCard,
  UserCheck,
  FileWarning,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { PATHS, generatePath } from '@/routes/paths'

import { useClient } from '../hooks/use-client'
import { IdentityDocList } from './IdentityDocList'
import { CLIENT_TYPE_LABELS } from '../types'
import type { Client, ClientType } from '../types'

// ============================================================================
// Types
// ============================================================================

export interface ClientDetailProps {
  /** 当事人 ID */
  clientId: string
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * 获取法定代表人/负责人的标签
 * 法人显示"法定代表人"，非法人组织显示"负责人"
 */
function getLegalRepLabel(clientType: ClientType): string {
  return clientType === 'non_legal_org' ? '负责人' : '法定代表人'
}

/**
 * 获取身份证号/统一社会信用代码的标签
 * 自然人显示"身份证号"，法人显示"统一社会信用代码"
 */
function getIdNumberLabel(clientType: ClientType): string {
  switch (clientType) {
    case 'natural':
      return '身份证号'
    case 'legal':
      return '统一社会信用代码'
    case 'non_legal_org':
      return '统一社会信用代码'
    default:
      return '身份证号'
  }
}

/**
 * 判断是否需要显示法定代表人
 * 法人和非法人组织需要显示
 * Requirements: 4.2
 */
function shouldShowLegalRepresentative(clientType: ClientType): boolean {
  return clientType === 'legal' || clientType === 'non_legal_org'
}

/**
 * 获取当事人类型图标
 */
function getClientTypeIcon(clientType: ClientType) {
  switch (clientType) {
    case 'natural':
      return User
    case 'legal':
    case 'non_legal_org':
      return Building2
    default:
      return User
  }
}

/**
 * 获取当事人类型徽章变体
 */
function getClientTypeBadgeVariant(
  clientType: ClientType
): 'default' | 'secondary' | 'outline' {
  switch (clientType) {
    case 'natural':
      return 'default'
    case 'legal':
      return 'secondary'
    case 'non_legal_org':
      return 'outline'
    default:
      return 'default'
  }
}

// ============================================================================
// Sub-components
// ============================================================================

/**
 * 加载状态骨架屏
 * Requirements: 4.7
 */
function ClientDetailSkeleton() {
  return (
    <div className="space-y-6">
      {/* 头部骨架 */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <Skeleton className="size-10 rounded-full" />
          <div className="space-y-2">
            <Skeleton className="h-6 w-32" />
            <Skeleton className="h-4 w-20" />
          </div>
        </div>
        <div className="flex gap-2">
          <Skeleton className="h-9 w-20" />
          <Skeleton className="h-9 w-20" />
        </div>
      </div>

      {/* 基本信息卡片骨架 */}
      <Card>
        <CardHeader>
          <Skeleton className="h-5 w-24" />
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="space-y-2">
                <Skeleton className="h-4 w-16" />
                <Skeleton className="h-5 w-full" />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* 证件列表骨架 */}
      <Card>
        <CardHeader>
          <Skeleton className="h-5 w-24" />
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="aspect-[4/3] rounded-lg" />
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

/**
 * 404 错误页面
 * Requirements: 4.8
 */
function ClientNotFound() {
  const navigate = useNavigate()

  const handleBack = useCallback(() => {
    navigate(PATHS.ADMIN_CLIENTS)
  }, [navigate])

  return (
    <div className="flex min-h-[400px] flex-col items-center justify-center">
      <div className="text-center">
        <FileWarning className="text-muted-foreground mx-auto mb-4 size-16 opacity-50" />
        <h2 className="mb-2 text-xl font-semibold">当事人不存在</h2>
        <p className="text-muted-foreground mb-6">
          您访问的当事人可能已被删除或不存在
        </p>
        <Button onClick={handleBack} variant="outline">
          <ArrowLeft className="mr-2 size-4" />
          返回列表
        </Button>
      </div>
    </div>
  )
}

interface InfoItemProps {
  icon: React.ElementType
  label: string
  value: string | null | undefined
  emptyText?: string
}

/**
 * 信息项组件
 */
function InfoItem({ icon: Icon, label, value, emptyText = '未填写' }: InfoItemProps) {
  return (
    <div className="space-y-1.5">
      <div className="text-muted-foreground flex items-center gap-1.5 text-sm">
        <Icon className="size-4" />
        <span>{label}</span>
      </div>
      <p className={`text-sm ${value ? 'text-foreground' : 'text-muted-foreground'}`}>
        {value || emptyText}
      </p>
    </div>
  )
}

interface ClientHeaderProps {
  client: Client
  onEdit: () => void
  onBack: () => void
}

/**
 * 详情页头部
 */
function ClientHeader({ client, onEdit, onBack }: ClientHeaderProps) {
  const TypeIcon = getClientTypeIcon(client.client_type)

  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      {/* 左侧：当事人信息 */}
      <div className="flex items-center gap-3">
        <div className="bg-primary/10 flex size-12 items-center justify-center rounded-full">
          <TypeIcon className="text-primary size-6" />
        </div>
        <div>
          <h1 className="text-xl font-semibold">{client.name}</h1>
          <Badge variant={getClientTypeBadgeVariant(client.client_type)}>
            {CLIENT_TYPE_LABELS[client.client_type]}
          </Badge>
        </div>
      </div>

      {/* 右侧：操作按钮 */}
      <div className="flex gap-2">
        {/* 返回按钮 - Requirements: 4.6 */}
        <Button variant="outline" onClick={onBack}>
          <ArrowLeft className="mr-2 size-4" />
          返回
        </Button>
        {/* 编辑按钮 - Requirements: 4.5 */}
        <Button onClick={onEdit}>
          <Edit className="mr-2 size-4" />
          编辑
        </Button>
      </div>
    </div>
  )
}

interface BasicInfoCardProps {
  client: Client
}

/**
 * 基本信息卡片
 * Requirements: 4.1, 4.2
 */
function BasicInfoCard({ client }: BasicInfoCardProps) {
  const showLegalRep = shouldShowLegalRepresentative(client.client_type)
  const idNumberLabel = getIdNumberLabel(client.client_type)
  const legalRepLabel = getLegalRepLabel(client.client_type)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">基本信息</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid gap-6 sm:grid-cols-2">
          {/* 姓名 - Requirements: 4.1 */}
          <InfoItem icon={User} label="姓名" value={client.name} />

          {/* 身份证号/统一社会信用代码 - Requirements: 4.1 */}
          <InfoItem icon={CreditCard} label={idNumberLabel} value={client.id_number} />

          {/* 手机号 - Requirements: 4.1 */}
          <InfoItem icon={Phone} label="手机号" value={client.phone} />

          {/* 地址 - Requirements: 4.1 */}
          <InfoItem icon={MapPin} label="地址" value={client.address} />

          {/* 法定代表人/负责人 - Requirements: 4.2 */}
          {showLegalRep && (
            <InfoItem
              icon={UserCheck}
              label={legalRepLabel}
              value={client.legal_representative}
            />
          )}
        </div>
      </CardContent>
    </Card>
  )
}

interface IdentityDocsCardProps {
  client: Client
}

/**
 * 身份证件卡片
 * Requirements: 4.3, 4.4
 */
function IdentityDocsCard({ client }: IdentityDocsCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">身份证件</CardTitle>
      </CardHeader>
      <CardContent>
        <IdentityDocList docs={client.identity_docs} />
      </CardContent>
    </Card>
  )
}

// ============================================================================
// Main Component
// ============================================================================

/**
 * 当事人详情组件
 *
 * Requirements:
 * - 4.1: 显示当事人的基本信息：姓名、类型、身份证号、手机号、地址
 * - 4.2: 当事人类型为法人或非法人组织时额外显示法定代表人信息
 * - 4.5: 点击「编辑」按钮导航到编辑页面
 * - 4.6: 点击「返回」按钮导航回列表页
 * - 4.7: 数据加载时显示加载状态
 * - 4.8: 当事人不存在时显示 404 错误页面
 */
export function ClientDetail({ clientId }: ClientDetailProps) {
  const navigate = useNavigate()

  // ========== 数据查询 ==========
  const { data: client, isLoading, error } = useClient(clientId)

  // ========== 事件处理 ==========

  /**
   * 处理编辑按钮点击
   * Requirements: 4.5
   */
  const handleEdit = useCallback(() => {
    navigate(generatePath.clientEdit(clientId))
  }, [navigate, clientId])

  /**
   * 处理返回按钮点击
   * Requirements: 4.6
   */
  const handleBack = useCallback(() => {
    navigate(PATHS.ADMIN_CLIENTS)
  }, [navigate])

  // ========== 渲染 ==========

  // 加载状态 - Requirements: 4.7
  if (isLoading) {
    return <ClientDetailSkeleton />
  }

  // 404 错误 - Requirements: 4.8
  if (error || !client) {
    return <ClientNotFound />
  }

  return (
    <div className="space-y-6">
      {/* 头部 */}
      <ClientHeader client={client} onEdit={handleEdit} onBack={handleBack} />

      <Separator />

      {/* 基本信息 - Requirements: 4.1, 4.2 */}
      <BasicInfoCard client={client} />

      {/* 身份证件 - Requirements: 4.3, 4.4 */}
      <IdentityDocsCard client={client} />
    </div>
  )
}

export default ClientDetail
