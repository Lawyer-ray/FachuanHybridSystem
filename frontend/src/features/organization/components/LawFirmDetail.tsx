/**
 * LawFirmDetail Component
 *
 * 律所详情组件
 * - 显示律所完整信息：名称、地址、联系电话、统一社会信用代码、开户行、银行账号
 * - 实现编辑和返回按钮
 * - 支持加载状态和 404 错误状态
 *
 * Requirements: 2.4
 */

import { useCallback } from 'react'
import { useNavigate } from 'react-router'
import {
  ArrowLeft,
  Edit,
  Building2,
  Phone,
  MapPin,
  CreditCard,
  Landmark,
  FileWarning,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { PATHS, generatePath } from '@/routes/paths'

import { useLawFirm } from '../hooks/use-lawfirm'
import type { LawFirm } from '../types'

// ============================================================================
// Types
// ============================================================================

export interface LawFirmDetailProps {
  /** 律所 ID */
  lawFirmId: string
}

// ============================================================================
// Sub-components
// ============================================================================

/**
 * 加载状态骨架屏
 */
function LawFirmDetailSkeleton() {
  return (
    <div className="space-y-6">
      {/* 头部骨架 */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <Skeleton className="size-12 rounded-full" />
          <div className="space-y-2">
            <Skeleton className="h-6 w-40" />
            <Skeleton className="h-4 w-24" />
          </div>
        </div>
        <div className="flex gap-2">
          <Skeleton className="h-9 w-20" />
          <Skeleton className="h-9 w-20" />
        </div>
      </div>

      <Skeleton className="h-px w-full" />

      {/* 基本信息卡片骨架 */}
      <Card>
        <CardHeader>
          <Skeleton className="h-5 w-24" />
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-6 sm:grid-cols-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="space-y-2">
                <Skeleton className="h-4 w-20" />
                <Skeleton className="h-5 w-full" />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

/**
 * 404 错误页面
 */
function LawFirmNotFound() {
  const navigate = useNavigate()

  const handleBack = useCallback(() => {
    navigate(PATHS.ADMIN_ORGANIZATION)
  }, [navigate])

  return (
    <div className="flex min-h-[400px] flex-col items-center justify-center">
      <div className="text-center">
        <FileWarning className="text-muted-foreground mx-auto mb-4 size-16 opacity-50" />
        <h2 className="mb-2 text-xl font-semibold">律所不存在</h2>
        <p className="text-muted-foreground mb-6">
          您访问的律所可能已被删除或不存在
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

interface LawFirmHeaderProps {
  lawFirm: LawFirm
  onEdit: () => void
  onBack: () => void
}

/**
 * 详情页头部
 */
function LawFirmHeader({ lawFirm, onEdit, onBack }: LawFirmHeaderProps) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      {/* 左侧：律所信息 */}
      <div className="flex items-center gap-3">
        <div className="bg-primary/10 flex size-12 items-center justify-center rounded-full">
          <Building2 className="text-primary size-6" />
        </div>
        <div>
          <h1 className="text-xl font-semibold">{lawFirm.name}</h1>
          <p className="text-muted-foreground text-sm">律所信息</p>
        </div>
      </div>

      {/* 右侧：操作按钮 */}
      <div className="flex gap-2">
        {/* 返回按钮 */}
        <Button variant="outline" onClick={onBack}>
          <ArrowLeft className="mr-2 size-4" />
          返回
        </Button>
        {/* 编辑按钮 */}
        <Button onClick={onEdit}>
          <Edit className="mr-2 size-4" />
          编辑
        </Button>
      </div>
    </div>
  )
}

interface BasicInfoCardProps {
  lawFirm: LawFirm
}

/**
 * 基本信息卡片
 * 显示律所完整信息：名称、地址、联系电话、统一社会信用代码、开户行、银行账号
 * Requirements: 2.4
 */
function BasicInfoCard({ lawFirm }: BasicInfoCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">基本信息</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid gap-6 sm:grid-cols-2">
          {/* 名称 */}
          <InfoItem icon={Building2} label="名称" value={lawFirm.name} />

          {/* 地址 */}
          <InfoItem icon={MapPin} label="地址" value={lawFirm.address} />

          {/* 联系电话 */}
          <InfoItem icon={Phone} label="联系电话" value={lawFirm.phone} />

          {/* 统一社会信用代码 */}
          <InfoItem
            icon={CreditCard}
            label="统一社会信用代码"
            value={lawFirm.social_credit_code}
          />

          {/* 开户行 */}
          <InfoItem icon={Landmark} label="开户行" value={lawFirm.bank_name} />

          {/* 银行账号 */}
          <InfoItem icon={CreditCard} label="银行账号" value={lawFirm.bank_account} />
        </div>
      </CardContent>
    </Card>
  )
}

// ============================================================================
// Main Component
// ============================================================================

/**
 * 律所详情组件
 *
 * Requirements:
 * - 2.4: 显示律所完整信息
 * - 实现编辑和返回按钮
 * - 支持加载状态和 404 错误状态
 */
export function LawFirmDetail({ lawFirmId }: LawFirmDetailProps) {
  const navigate = useNavigate()

  // ========== 数据查询 ==========
  const { data: lawFirm, isLoading, error } = useLawFirm(lawFirmId)

  // ========== 事件处理 ==========

  /**
   * 处理编辑按钮点击
   * 导航到编辑页面
   */
  const handleEdit = useCallback(() => {
    navigate(generatePath.lawFirmEdit(lawFirmId))
  }, [navigate, lawFirmId])

  /**
   * 处理返回按钮点击
   * 导航回组织管理列表页
   */
  const handleBack = useCallback(() => {
    navigate(PATHS.ADMIN_ORGANIZATION)
  }, [navigate])

  // ========== 渲染 ==========

  // 加载状态
  if (isLoading) {
    return <LawFirmDetailSkeleton />
  }

  // 404 错误
  if (error || !lawFirm) {
    return <LawFirmNotFound />
  }

  return (
    <div className="space-y-6">
      {/* 头部 */}
      <LawFirmHeader lawFirm={lawFirm} onEdit={handleEdit} onBack={handleBack} />

      <Separator />

      {/* 基本信息 - Requirements: 2.4 */}
      <BasicInfoCard lawFirm={lawFirm} />
    </div>
  )
}

export default LawFirmDetail
