/**
 * LawFirmTable Component
 *
 * 律所列表表格组件
 * - 显示律所名称、地址、联系电话、统一社会信用代码列
 * - 实现行点击导航到详情页
 * - 支持加载状态和空状态
 * - 移动端支持横向滚动
 *
 * Requirements: 2.1, 2.2, 2.4, 2.5, 2.6
 */

import { useNavigate } from 'react-router'
import { Building2 } from 'lucide-react'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { generatePath } from '@/routes/paths'
import { type LawFirm } from '../types'

// ============================================================================
// Types
// ============================================================================

export interface LawFirmTableProps {
  /** 律所列表数据 */
  lawFirms: LawFirm[]
  /** 是否正在加载 */
  isLoading?: boolean
}

// ============================================================================
// Sub-components
// ============================================================================

/**
 * 表格骨架屏 - 加载状态
 * Requirements: 2.5
 */
function TableSkeleton() {
  return (
    <>
      {Array.from({ length: 5 }).map((_, index) => (
        <TableRow key={index}>
          <TableCell>
            <div className="bg-muted h-4 w-32 animate-pulse rounded" />
          </TableCell>
          <TableCell>
            <div className="bg-muted h-4 w-48 animate-pulse rounded" />
          </TableCell>
          <TableCell>
            <div className="bg-muted h-4 w-28 animate-pulse rounded" />
          </TableCell>
          <TableCell>
            <div className="bg-muted h-4 w-40 animate-pulse rounded" />
          </TableCell>
        </TableRow>
      ))}
    </>
  )
}

/**
 * 空状态组件
 * Requirements: 2.6
 */
function EmptyState() {
  return (
    <TableRow>
      <TableCell colSpan={4} className="h-48">
        <div className="flex flex-col items-center justify-center gap-3">
          <div className="bg-muted flex size-12 items-center justify-center rounded-full">
            <Building2 className="text-muted-foreground size-6" />
          </div>
          <div className="text-center">
            <p className="text-muted-foreground text-sm font-medium">
              暂无律所数据
            </p>
            <p className="text-muted-foreground/70 mt-1 text-xs">
              点击「新建律所」按钮添加第一个律所
            </p>
          </div>
        </div>
      </TableCell>
    </TableRow>
  )
}

/**
 * 格式化统一社会信用代码（脱敏显示）
 */
function formatSocialCreditCode(code: string | null | undefined): string {
  if (!code) return '-'
  // 统一社会信用代码通常是18位
  if (code.length <= 8) return code
  return `${code.slice(0, 4)}****${code.slice(-4)}`
}

/**
 * 格式化手机号（脱敏显示）
 */
function formatPhone(phone: string | null | undefined): string {
  if (!phone) return '-'
  if (phone.length !== 11) return phone
  return `${phone.slice(0, 3)}****${phone.slice(-4)}`
}

/**
 * 格式化地址（截断显示）
 */
function formatAddress(address: string | null | undefined): string {
  if (!address) return '-'
  if (address.length <= 30) return address
  return `${address.slice(0, 30)}...`
}

// ============================================================================
// Main Component
// ============================================================================

/**
 * 律所表格组件
 *
 * Requirements:
 * - 2.1: 以表格形式展示律所列表
 * - 2.2: 显示律所名称、地址、联系电话、统一社会信用代码列
 * - 2.4: 点击行导航到详情页
 * - 2.5: 数据加载时显示加载状态
 * - 2.6: 列表为空时显示空状态提示
 * - 6.2: 屏幕宽度小于 768px 时表格支持横向滚动
 */
export function LawFirmTable({ lawFirms, isLoading = false }: LawFirmTableProps) {
  const navigate = useNavigate()

  /**
   * 处理行点击 - 导航到详情页
   * Requirements: 2.4
   */
  const handleRowClick = (lawFirm: LawFirm) => {
    navigate(generatePath.lawFirmDetail(lawFirm.id))
  }

  return (
    // 外层容器：支持横向滚动 - Requirements: 6.2
    <div className="overflow-x-auto rounded-md border">
      {/* 表格设置最小宽度，确保在小屏幕上不会过度压缩 */}
      <Table className="min-w-[600px]">
        {/* 表头 - Requirements: 2.2 */}
        <TableHeader>
          <TableRow>
            <TableHead className="w-[120px] text-xs sm:w-[160px] sm:text-sm">
              律所名称
            </TableHead>
            <TableHead className="w-[180px] text-xs sm:w-[240px] sm:text-sm">
              地址
            </TableHead>
            <TableHead className="w-[110px] text-xs sm:w-[140px] sm:text-sm">
              联系电话
            </TableHead>
            <TableHead className="w-[140px] text-xs sm:w-[180px] sm:text-sm">
              统一社会信用代码
            </TableHead>
          </TableRow>
        </TableHeader>

        {/* 表体 - Requirements: 2.1, 2.5, 2.6 */}
        <TableBody>
          {isLoading ? (
            <TableSkeleton />
          ) : lawFirms.length === 0 ? (
            <EmptyState />
          ) : (
            lawFirms.map((lawFirm) => (
              <TableRow
                key={lawFirm.id}
                onClick={() => handleRowClick(lawFirm)}
                // 触摸友好的行高 - 最小 44px 点击区域
                className="h-11 cursor-pointer sm:h-auto"
              >
                <TableCell className="text-xs font-medium sm:text-sm">
                  {lawFirm.name || '-'}
                </TableCell>
                <TableCell className="text-muted-foreground text-xs sm:text-sm">
                  {formatAddress(lawFirm.address)}
                </TableCell>
                <TableCell className="text-muted-foreground font-mono text-xs sm:text-sm">
                  {formatPhone(lawFirm.phone)}
                </TableCell>
                <TableCell className="text-muted-foreground font-mono text-xs sm:text-sm">
                  {formatSocialCreditCode(lawFirm.social_credit_code)}
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  )
}
