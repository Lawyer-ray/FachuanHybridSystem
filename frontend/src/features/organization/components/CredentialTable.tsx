/**
 * CredentialTable Component
 *
 * 账号凭证列表表格组件
 * - 显示网站名称、URL、账号、所属律师、创建时间列
 * - 实现编辑和删除按钮（非行点击导航）
 * - 支持加载状态和空状态
 * - 移动端支持横向滚动
 *
 * Requirements: 5.1, 5.2, 5.5, 5.6, 5.7
 */

import { Edit2, ExternalLink, KeyRound, Trash2 } from 'lucide-react'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Button } from '@/components/ui/button'
import { type AccountCredential, type Lawyer } from '../types'

// ============================================================================
// Types
// ============================================================================

export interface CredentialTableProps {
  /** 凭证列表数据 */
  credentials: AccountCredential[]
  /** 律师列表（用于查找律师名称） */
  lawyers: Lawyer[]
  /** 是否正在加载 */
  isLoading?: boolean
  /** 编辑回调 */
  onEdit: (credential: AccountCredential) => void
  /** 删除回调 */
  onDelete: (credential: AccountCredential) => void
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * 格式化日期为 YYYY-MM-DD 格式
 */
function formatDate(dateString: string): string {
  if (!dateString) return '-'
  try {
    const date = new Date(dateString)
    return date.toISOString().split('T')[0]
  } catch {
    return '-'
  }
}

// ============================================================================
// Sub-components
// ============================================================================

/**
 * 表格骨架屏 - 加载状态
 * Requirements: 5.7
 */
function TableSkeleton() {
  return (
    <>
      {Array.from({ length: 5 }).map((_, index) => (
        <TableRow key={index}>
          <TableCell>
            <div className="bg-muted h-4 w-24 animate-pulse rounded" />
          </TableCell>
          <TableCell>
            <div className="bg-muted h-4 w-32 animate-pulse rounded" />
          </TableCell>
          <TableCell>
            <div className="bg-muted h-4 w-28 animate-pulse rounded" />
          </TableCell>
          <TableCell>
            <div className="bg-muted h-4 w-20 animate-pulse rounded" />
          </TableCell>
          <TableCell>
            <div className="bg-muted h-4 w-24 animate-pulse rounded" />
          </TableCell>
          <TableCell>
            <div className="bg-muted flex h-4 w-20 animate-pulse gap-2 rounded" />
          </TableCell>
        </TableRow>
      ))}
    </>
  )
}

/**
 * 空状态组件
 */
function EmptyState() {
  return (
    <TableRow>
      <TableCell colSpan={6} className="h-48">
        <div className="flex flex-col items-center justify-center gap-3">
          <div className="bg-muted flex size-12 items-center justify-center rounded-full">
            <KeyRound className="text-muted-foreground size-6" />
          </div>
          <div className="text-center">
            <p className="text-muted-foreground text-sm font-medium">
              暂无凭证数据
            </p>
            <p className="text-muted-foreground/70 mt-1 text-xs">
              点击「新建凭证」按钮添加第一个凭证
            </p>
          </div>
        </div>
      </TableCell>
    </TableRow>
  )
}

// ============================================================================
// Main Component
// ============================================================================

/**
 * 凭证表格组件
 *
 * Requirements:
 * - 5.1: 以表格形式展示凭证列表
 * - 5.2: 显示网站名称、URL、账号、所属律师、创建时间列
 * - 5.5: 实现编辑按钮
 * - 5.6: 实现删除按钮
 * - 5.7: 数据加载时显示加载状态
 * - 6.2: 屏幕宽度小于 768px 时表格支持横向滚动
 */
export function CredentialTable({
  credentials,
  lawyers,
  isLoading = false,
  onEdit,
  onDelete,
}: CredentialTableProps) {
  /**
   * 根据律师 ID 查找律师名称
   * 优先显示 real_name，如果没有则显示 username
   */
  const getLawyerName = (lawyerId: number): string => {
    const lawyer = lawyers.find((l) => l.id === lawyerId)
    if (!lawyer) return '-'
    return lawyer.real_name || lawyer.username || '-'
  }

  return (
    // 外层容器：支持横向滚动 - Requirements: 6.2
    <div className="overflow-x-auto rounded-md border">
      {/* 表格设置最小宽度，确保在小屏幕上不会过度压缩 */}
      <Table className="min-w-[700px]">
        {/* 表头 - Requirements: 5.2 */}
        <TableHeader>
          <TableRow>
            <TableHead className="w-[120px] text-xs sm:w-[140px] sm:text-sm">
              网站名称
            </TableHead>
            <TableHead className="w-[160px] text-xs sm:w-[200px] sm:text-sm">
              URL
            </TableHead>
            <TableHead className="w-[120px] text-xs sm:w-[140px] sm:text-sm">
              账号
            </TableHead>
            <TableHead className="w-[100px] text-xs sm:w-[120px] sm:text-sm">
              所属律师
            </TableHead>
            <TableHead className="w-[100px] text-xs sm:w-[120px] sm:text-sm">
              创建时间
            </TableHead>
            <TableHead className="w-[100px] text-xs sm:w-[120px] sm:text-sm">
              操作
            </TableHead>
          </TableRow>
        </TableHeader>

        {/* 表体 - Requirements: 5.1, 5.5, 5.6, 5.7 */}
        <TableBody>
          {isLoading ? (
            <TableSkeleton />
          ) : credentials.length === 0 ? (
            <EmptyState />
          ) : (
            credentials.map((credential) => (
              <TableRow
                key={credential.id}
                // 触摸友好的行高 - 最小 44px 点击区域
                className="h-11 sm:h-auto"
              >
                {/* 网站名称 */}
                <TableCell className="text-xs font-medium sm:text-sm">
                  {credential.site_name || '-'}
                </TableCell>

                {/* URL - 显示为可点击链接 */}
                <TableCell className="text-xs sm:text-sm">
                  {credential.url ? (
                    <a
                      href={credential.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-primary hover:text-primary/80 inline-flex max-w-[180px] items-center gap-1 truncate transition-colors"
                      title={credential.url}
                    >
                      <span className="truncate">{credential.url}</span>
                      <ExternalLink className="size-3 shrink-0" />
                    </a>
                  ) : (
                    <span className="text-muted-foreground">-</span>
                  )}
                </TableCell>

                {/* 账号 */}
                <TableCell className="text-muted-foreground text-xs sm:text-sm">
                  {credential.account || '-'}
                </TableCell>

                {/* 所属律师 */}
                <TableCell className="text-muted-foreground text-xs sm:text-sm">
                  {getLawyerName(credential.lawyer)}
                </TableCell>

                {/* 创建时间 */}
                <TableCell className="text-muted-foreground text-xs sm:text-sm">
                  {formatDate(credential.created_at)}
                </TableCell>

                {/* 操作按钮 */}
                <TableCell>
                  <div className="flex items-center gap-1">
                    {/* 编辑按钮 - Requirements: 5.5 */}
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-8"
                      onClick={() => onEdit(credential)}
                      aria-label={`编辑凭证 ${credential.site_name}`}
                    >
                      <Edit2 className="size-4" />
                    </Button>
                    {/* 删除按钮 - Requirements: 5.6 */}
                    <Button
                      variant="ghost"
                      size="icon"
                      className="text-destructive hover:text-destructive size-8"
                      onClick={() => onDelete(credential)}
                      aria-label={`删除凭证 ${credential.site_name}`}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  )
}
