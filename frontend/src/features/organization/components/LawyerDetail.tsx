/**
 * LawyerDetail Component
 *
 * 律师详情组件
 * - 显示律师完整信息：用户名、真实姓名、手机号、执业证号、身份证号、所属律所、是否管理员、状态
 * - 显示执业证 PDF 链接
 * - 实现编辑和返回按钮
 * - 支持加载状态和 404 错误状态
 *
 * Requirements: 3.5
 */

import { useCallback } from 'react'
import { useNavigate } from 'react-router'
import {
  ArrowLeft,
  Edit,
  UserRound,
  User,
  Phone,
  CreditCard,
  Building2,
  FileText,
  Shield,
  FileWarning,
  ExternalLink,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { PATHS, generatePath } from '@/routes/paths'

import { useLawyer } from '../hooks/use-lawyer'
import type { Lawyer } from '../types'

// ============================================================================
// Types
// ============================================================================

export interface LawyerDetailProps {
  /** 律师 ID */
  lawyerId: string
}

// ============================================================================
// Sub-components
// ============================================================================

/**
 * 加载状态骨架屏
 */
function LawyerDetailSkeleton() {
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
            {Array.from({ length: 8 }).map((_, i) => (
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
function LawyerNotFound() {
  const navigate = useNavigate()

  const handleBack = useCallback(() => {
    navigate(PATHS.ADMIN_ORGANIZATION)
  }, [navigate])

  return (
    <div className="flex min-h-[400px] flex-col items-center justify-center">
      <div className="text-center">
        <FileWarning className="text-muted-foreground mx-auto mb-4 size-16 opacity-50" />
        <h2 className="mb-2 text-xl font-semibold">律师不存在</h2>
        <p className="text-muted-foreground mb-6">
          您访问的律师可能已被删除或不存在
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
  value: React.ReactNode
  emptyText?: string
}

/**
 * 信息项组件
 */
function InfoItem({ icon: Icon, label, value, emptyText = '未填写' }: InfoItemProps) {
  const isEmpty = value === null || value === undefined || value === ''

  return (
    <div className="space-y-1.5">
      <div className="text-muted-foreground flex items-center gap-1.5 text-sm">
        <Icon className="size-4" />
        <span>{label}</span>
      </div>
      <div className={`text-sm ${isEmpty ? 'text-muted-foreground' : 'text-foreground'}`}>
        {isEmpty ? emptyText : value}
      </div>
    </div>
  )
}

interface LawyerHeaderProps {
  lawyer: Lawyer
  onEdit: () => void
  onBack: () => void
}

/**
 * 详情页头部
 */
function LawyerHeader({ lawyer, onEdit, onBack }: LawyerHeaderProps) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      {/* 左侧：律师信息 */}
      <div className="flex items-center gap-3">
        <div className="bg-primary/10 flex size-12 items-center justify-center rounded-full">
          <UserRound className="text-primary size-6" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-semibold">
              {lawyer.real_name || lawyer.username}
            </h1>
            {/* 状态徽章 */}
            <Badge variant={lawyer.is_active ? 'default' : 'destructive'}>
              {lawyer.is_active ? '启用' : '禁用'}
            </Badge>
          </div>
          <p className="text-muted-foreground text-sm">律师信息</p>
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
  lawyer: Lawyer
}

/**
 * 基本信息卡片
 * 显示律师完整信息：用户名、真实姓名、手机号、执业证号、身份证号、所属律所、是否管理员、状态
 * Requirements: 3.5
 */
function BasicInfoCard({ lawyer }: BasicInfoCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">基本信息</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid gap-6 sm:grid-cols-2">
          {/* 用户名 */}
          <InfoItem icon={User} label="用户名" value={lawyer.username} />

          {/* 真实姓名 */}
          <InfoItem icon={User} label="真实姓名" value={lawyer.real_name} />

          {/* 手机号 */}
          <InfoItem icon={Phone} label="手机号" value={lawyer.phone} />

          {/* 执业证号 */}
          <InfoItem icon={FileText} label="执业证号" value={lawyer.license_no} />

          {/* 身份证号 */}
          <InfoItem icon={CreditCard} label="身份证号" value={lawyer.id_card} />

          {/* 所属律所 */}
          <InfoItem
            icon={Building2}
            label="所属律所"
            value={lawyer.law_firm_detail?.name}
            emptyText="未设置"
          />

          {/* 是否管理员 */}
          <InfoItem
            icon={Shield}
            label="角色"
            value={
              <Badge variant={lawyer.is_admin ? 'default' : 'secondary'}>
                {lawyer.is_admin ? '管理员' : '普通用户'}
              </Badge>
            }
          />

          {/* 执业证 PDF */}
          <InfoItem
            icon={FileText}
            label="执业证"
            value={
              lawyer.license_pdf_url ? (
                <a
                  href={lawyer.license_pdf_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary hover:underline inline-flex items-center gap-1"
                >
                  查看执业证
                  <ExternalLink className="size-3" />
                </a>
              ) : null
            }
            emptyText="未上传"
          />
        </div>
      </CardContent>
    </Card>
  )
}

// ============================================================================
// Main Component
// ============================================================================

/**
 * 律师详情组件
 *
 * Requirements:
 * - 3.5: 显示律师完整信息
 * - 显示执业证 PDF 链接
 * - 实现编辑和返回按钮
 * - 支持加载状态和 404 错误状态
 */
export function LawyerDetail({ lawyerId }: LawyerDetailProps) {
  const navigate = useNavigate()

  // ========== 数据查询 ==========
  const { data: lawyer, isLoading, error } = useLawyer(lawyerId)

  // ========== 事件处理 ==========

  /**
   * 处理编辑按钮点击
   * 导航到编辑页面
   */
  const handleEdit = useCallback(() => {
    navigate(generatePath.lawyerEdit(lawyerId))
  }, [navigate, lawyerId])

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
    return <LawyerDetailSkeleton />
  }

  // 404 错误
  if (error || !lawyer) {
    return <LawyerNotFound />
  }

  return (
    <div className="space-y-6">
      {/* 头部 */}
      <LawyerHeader lawyer={lawyer} onEdit={handleEdit} onBack={handleBack} />

      <Separator />

      {/* 基本信息 - Requirements: 3.5 */}
      <BasicInfoCard lawyer={lawyer} />
    </div>
  )
}

export default LawyerDetail
