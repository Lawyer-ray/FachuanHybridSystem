/**
 * ClientTable Component
 *
 * 当事人列表表格组件
 * - 显示姓名、身份证号、手机号、类型、创建时间列
 * - 实现行点击导航到详情页
 * - 支持加载状态和空状态
 * - 移动端支持横向滚动
 *
 * Requirements: 3.1, 3.2, 3.7, 3.8, 3.9, 7.2, 7.5
 */

import { useNavigate } from 'react-router'
import { Users } from 'lucide-react'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { generatePath } from '@/routes/paths'
import { type Client, CLIENT_TYPE_LABELS } from '../types'

// ============================================================================
// Types
// ============================================================================

export interface ClientTableProps {
  /** 当事人列表数据 */
  clients: Client[]
  /** 是否正在加载 */
  isLoading?: boolean
}

// ============================================================================
// Sub-components
// ============================================================================

/**
 * 表格骨架屏 - 加载状态
 * Requirements: 3.8
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
            <div className="bg-muted h-4 w-40 animate-pulse rounded" />
          </TableCell>
          <TableCell>
            <div className="bg-muted h-4 w-28 animate-pulse rounded" />
          </TableCell>
          <TableCell>
            <div className="bg-muted h-4 w-16 animate-pulse rounded" />
          </TableCell>
          <TableCell>
            <div className="bg-muted h-4 w-24 animate-pulse rounded" />
          </TableCell>
        </TableRow>
      ))}
    </>
  )
}

/**
 * 空状态组件
 * Requirements: 3.9
 */
function EmptyState() {
  return (
    <TableRow>
      <TableCell colSpan={5} className="h-48">
        <div className="flex flex-col items-center justify-center gap-3">
          <div className="bg-muted flex size-12 items-center justify-center rounded-full">
            <Users className="text-muted-foreground size-6" />
          </div>
          <div className="text-center">
            <p className="text-muted-foreground text-sm font-medium">
              暂无当事人数据
            </p>
            <p className="text-muted-foreground/70 mt-1 text-xs">
              点击「新建当事人」按钮添加第一个当事人
            </p>
          </div>
        </div>
      </TableCell>
    </TableRow>
  )
}

/**
 * 格式化日期时间
 */
function formatDateTime(dateString: string | undefined | null): string {
  if (!dateString) return '-'
  try {
    const date = new Date(dateString)
    return date.toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    })
  } catch {
    return '-'
  }
}

/**
 * 格式化身份证号/统一社会信用代码（脱敏显示）
 */
function formatIdNumber(idNumber: string | null): string {
  if (!idNumber) return '-'
  // 统一社会信用代码通常是18位，身份证号是18位
  if (idNumber.length <= 8) return idNumber
  return `${idNumber.slice(0, 4)}****${idNumber.slice(-4)}`
}

/**
 * 获取身份证号/统一社会信用代码的列标题
 */
function getIdColumnLabel(clients: Client[]): string {
  // 如果列表中有法人，显示更通用的标题
  const hasLegalEntity = clients.some(
    (c) => c.client_type === 'legal' || c.client_type === 'non_legal_org'
  )
  return hasLegalEntity ? '证件号码' : '身份证号'
}

/**
 * 格式化手机号（脱敏显示）
 */
function formatPhone(phone: string | null): string {
  if (!phone) return '-'
  if (phone.length !== 11) return phone
  return `${phone.slice(0, 3)}****${phone.slice(-4)}`
}

// ============================================================================
// Main Component
// ============================================================================

/**
 * 当事人表格组件
 *
 * Requirements:
 * - 3.1: 以表格形式展示当事人列表
 * - 3.2: 显示姓名、身份证号、手机号、类型、创建时间列
 * - 3.7: 点击行导航到详情页
 * - 3.8: 数据加载时显示加载状态
 * - 3.9: 列表为空时显示空状态提示
 * - 7.2: 屏幕宽度小于 768px 时表格支持横向滚动
 * - 7.5: 所有交互元素在触摸设备上有足够的点击区域（最小 44px）
 */
export function ClientTable({ clients, isLoading = false }: ClientTableProps) {
  const navigate = useNavigate()
  const idColumnLabel = getIdColumnLabel(clients)

  /**
   * 处理行点击 - 导航到详情页
   * Requirements: 3.7
   */
  const handleRowClick = (client: Client) => {
    navigate(generatePath.clientDetail(client.id))
  }

  return (
    // 外层容器：支持横向滚动 - Requirements: 7.2
    <div className="overflow-x-auto rounded-md border">
      {/* 表格设置最小宽度，确保在小屏幕上不会过度压缩 */}
      <Table className="min-w-[600px]">
        {/* 表头 - Requirements: 3.2 */}
        <TableHeader>
          <TableRow>
            <TableHead className="w-[100px] text-xs sm:w-[120px] sm:text-sm">
              姓名
            </TableHead>
            <TableHead className="w-[140px] text-xs sm:w-[180px] sm:text-sm">
              {idColumnLabel}
            </TableHead>
            <TableHead className="w-[110px] text-xs sm:w-[140px] sm:text-sm">
              手机号
            </TableHead>
            <TableHead className="w-[80px] text-xs sm:w-[100px] sm:text-sm">
              类型
            </TableHead>
            <TableHead className="w-[100px] text-xs sm:w-[120px] sm:text-sm">
              创建时间
            </TableHead>
          </TableRow>
        </TableHeader>

        {/* 表体 - Requirements: 3.1, 3.8, 3.9 */}
        <TableBody>
          {isLoading ? (
            <TableSkeleton />
          ) : clients.length === 0 ? (
            <EmptyState />
          ) : (
            clients.map((client) => (
              <TableRow
                key={client.id}
                onClick={() => handleRowClick(client)}
                // 触摸友好的行高 - Requirements: 7.5
                className="h-11 cursor-pointer sm:h-auto"
              >
                <TableCell className="text-xs font-medium sm:text-sm">
                  {client.name}
                </TableCell>
                <TableCell className="text-muted-foreground font-mono text-xs sm:text-sm">
                  {formatIdNumber(client.id_number)}
                </TableCell>
                <TableCell className="text-muted-foreground font-mono text-xs sm:text-sm">
                  {formatPhone(client.phone)}
                </TableCell>
                <TableCell>
                  <span className="bg-secondary text-secondary-foreground inline-flex items-center rounded-md px-1.5 py-0.5 text-xs font-medium sm:px-2">
                    {CLIENT_TYPE_LABELS[client.client_type]}
                  </span>
                </TableCell>
                <TableCell className="text-muted-foreground text-xs sm:text-sm">
                  {formatDateTime(client.created_at)}
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  )
}
