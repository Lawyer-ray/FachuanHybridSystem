/**
 * LawyerTable Component
 *
 * 律师列表表格组件
 * - 显示用户名、真实姓名、手机号、执业证号、所属律所、是否管理员、状态列
 * - 实现行点击导航到详情页
 * - 支持加载状态和空状态
 * - 移动端支持横向滚动
 *
 * Requirements: 3.1, 3.2, 3.5, 3.6, 3.7
 */

import { useNavigate } from 'react-router'
import { UserRound } from 'lucide-react'
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
import { type Lawyer } from '../types'

// ============================================================================
// Types
// ============================================================================

export interface LawyerTableProps {
  /** 律师列表数据 */
  lawyers: Lawyer[]
  /** 是否正在加载 */
  isLoading?: boolean
}

// ============================================================================
// Sub-components
// ============================================================================

/**
 * 表格骨架屏 - 加载状态
 * Requirements: 3.6
 */
function TableSkeleton() {
  return (
    <>
      {Array.from({ length: 5 }).map((_, index) => (
        <TableRow key={index}>
          <TableCell>
            <div className="bg-muted h-4 w-20 animate-pulse rounded" />
          </TableCell>
          <TableCell>
            <div className="bg-muted h-4 w-16 animate-pulse rounded" />
          </TableCell>
          <TableCell>
            <div className="bg-muted h-4 w-28 animate-pulse rounded" />
          </TableCell>
          <TableCell>
            <div className="bg-muted h-4 w-32 animate-pulse rounded" />
          </TableCell>
          <TableCell>
            <div className="bg-muted h-4 w-24 animate-pulse rounded" />
          </TableCell>
          <TableCell>
            <div className="bg-muted h-5 w-14 animate-pulse rounded-full" />
          </TableCell>
          <TableCell>
            <div className="bg-muted h-5 w-12 animate-pulse rounded-full" />
          </TableCell>
        </TableRow>
      ))}
    </>
  )
}

/**
 * 空状态组件
 * Requirements: 3.7
 */
function EmptyState() {
  return (
    <TableRow>
      <TableCell colSpan={7} className="h-48">
        <div className="flex flex-col items-center justify-center gap-3">
          <div className="bg-muted flex size-12 items-center justify-center rounded-full">
            <UserRound className="text-muted-foreground size-6" />
          </div>
          <div className="text-center">
            <p className="text-muted-foreground text-sm font-medium">
              暂无律师数据
            </p>
            <p className="text-muted-foreground/70 mt-1 text-xs">
              点击「新建律师」按钮添加第一个律师
            </p>
          </div>
        </div>
      </TableCell>
    </TableRow>
  )
}

/**
 * 格式化手机号（脱敏显示：显示前3位和后4位）
 */
function formatPhone(phone: string | null | undefined): string {
  if (!phone) return '-'
  if (phone.length !== 11) return phone
  return `${phone.slice(0, 3)}****${phone.slice(-4)}`
}

/**
 * 格式化执业证号（截断显示）
 */
function formatLicenseNo(licenseNo: string | null | undefined): string {
  if (!licenseNo) return '-'
  return licenseNo
}

/**
 * 获取所属律所名称
 */
function getLawFirmName(lawFirmDetail: Lawyer['law_firm_detail']): string {
  if (!lawFirmDetail) return '-'
  return lawFirmDetail.name || '-'
}

// ============================================================================
// Main Component
// ============================================================================

/**
 * 律师表格组件
 *
 * Requirements:
 * - 3.1: 以表格形式展示律师列表
 * - 3.2: 显示用户名、真实姓名、手机号、执业证号、所属律所、是否管理员、状态列
 * - 3.5: 点击行导航到详情页
 * - 3.6: 数据加载时显示加载状态
 * - 3.7: 列表为空时显示空状态提示
 * - 6.2: 屏幕宽度小于 768px 时表格支持横向滚动
 */
export function LawyerTable({ lawyers, isLoading = false }: LawyerTableProps) {
  const navigate = useNavigate()

  /**
   * 处理行点击 - 导航到详情页
   * Requirements: 3.5
   */
  const handleRowClick = (lawyer: Lawyer) => {
    navigate(generatePath.lawyerDetail(lawyer.id))
  }

  return (
    // 外层容器：支持横向滚动 - Requirements: 6.2
    <div className="overflow-x-auto rounded-md border">
      {/* 表格设置最小宽度，确保在小屏幕上不会过度压缩 */}
      <Table className="min-w-[800px]">
        {/* 表头 - Requirements: 3.2 */}
        <TableHeader>
          <TableRow>
            <TableHead className="w-[100px] text-xs sm:w-[120px] sm:text-sm">
              用户名
            </TableHead>
            <TableHead className="w-[80px] text-xs sm:w-[100px] sm:text-sm">
              真实姓名
            </TableHead>
            <TableHead className="w-[110px] text-xs sm:w-[130px] sm:text-sm">
              手机号
            </TableHead>
            <TableHead className="w-[140px] text-xs sm:w-[160px] sm:text-sm">
              执业证号
            </TableHead>
            <TableHead className="w-[120px] text-xs sm:w-[140px] sm:text-sm">
              所属律所
            </TableHead>
            <TableHead className="w-[80px] text-center text-xs sm:w-[90px] sm:text-sm">
              是否管理员
            </TableHead>
            <TableHead className="w-[70px] text-center text-xs sm:w-[80px] sm:text-sm">
              状态
            </TableHead>
          </TableRow>
        </TableHeader>

        {/* 表体 - Requirements: 3.1, 3.6, 3.7 */}
        <TableBody>
          {isLoading ? (
            <TableSkeleton />
          ) : lawyers.length === 0 ? (
            <EmptyState />
          ) : (
            lawyers.map((lawyer) => (
              <TableRow
                key={lawyer.id}
                onClick={() => handleRowClick(lawyer)}
                // 触摸友好的行高 - 最小 44px 点击区域
                className="h-11 cursor-pointer sm:h-auto"
              >
                <TableCell className="text-xs font-medium sm:text-sm">
                  {lawyer.username || '-'}
                </TableCell>
                <TableCell className="text-xs sm:text-sm">
                  {lawyer.real_name || '-'}
                </TableCell>
                <TableCell className="text-muted-foreground font-mono text-xs sm:text-sm">
                  {formatPhone(lawyer.phone)}
                </TableCell>
                <TableCell className="text-muted-foreground font-mono text-xs sm:text-sm">
                  {formatLicenseNo(lawyer.license_no)}
                </TableCell>
                <TableCell className="text-muted-foreground text-xs sm:text-sm">
                  {getLawFirmName(lawyer.law_firm_detail)}
                </TableCell>
                <TableCell className="text-center">
                  <Badge
                    variant={lawyer.is_admin ? 'default' : 'secondary'}
                    className="text-xs"
                  >
                    {lawyer.is_admin ? '管理员' : '普通用户'}
                  </Badge>
                </TableCell>
                <TableCell className="text-center">
                  <Badge
                    variant={lawyer.is_active ? 'default' : 'destructive'}
                    className={`text-xs ${
                      lawyer.is_active
                        ? 'bg-green-100 text-green-800 hover:bg-green-100 dark:bg-green-900/30 dark:text-green-400'
                        : ''
                    }`}
                  >
                    {lawyer.is_active ? '启用' : '禁用'}
                  </Badge>
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  )
}
