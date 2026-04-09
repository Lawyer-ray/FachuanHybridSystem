/**
 * CaseListMockUI - 案件管理卡片的模拟 UI 组件
 * @module features/home/components/FeaturesSection/CaseListMockUI
 *
 * 显示模拟的案件列表，包含案件状态、案号、类型和金额
 * Requirements: 3.5
 */

import { motion } from 'framer-motion'

import { cn } from '@/lib/utils'

// 案件状态类型
type CaseStatus = '进行中' | '已结案' | '待立案'

// 模拟案件数据接口
interface MockCaseItem {
  id: string
  status: CaseStatus
  caseNumber: string
  caseType: string
  amount: number
}

// 模拟案件数据
const MOCK_CASES: MockCaseItem[] = [
  {
    id: '1',
    status: '进行中',
    caseNumber: '(2024)粤0106民初12345号',
    caseType: '民间借贷纠纷',
    amount: 150000,
  },
  {
    id: '2',
    status: '已结案',
    caseNumber: '(2024)粤0106民初11234号',
    caseType: '买卖合同纠纷',
    amount: 280000,
  },
  {
    id: '3',
    status: '待立案',
    caseNumber: '(2024)粤0106民初13456号',
    caseType: '劳动争议纠纷',
    amount: 85000,
  },
  {
    id: '4',
    status: '进行中',
    caseNumber: '(2024)粤0106民初14567号',
    caseType: '房屋租赁纠纷',
    amount: 120000,
  },
]

// 状态徽章颜色映射
const statusStyles: Record<CaseStatus, { bg: string; text: string; dot: string }> = {
  '进行中': {
    bg: 'bg-blue-500/20',
    text: 'text-blue-400',
    dot: 'bg-blue-400',
  },
  '已结案': {
    bg: 'bg-green-500/20',
    text: 'text-green-400',
    dot: 'bg-green-400',
  },
  '待立案': {
    bg: 'bg-amber-500/20',
    text: 'text-amber-400',
    dot: 'bg-amber-400',
  },
}

// 格式化金额
function formatAmount(amount: number): string {
  return `¥${amount.toLocaleString('zh-CN')}`
}

// 案件状态徽章组件
function StatusBadge({ status }: { status: CaseStatus }) {
  const styles = statusStyles[status]

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium',
        styles.bg,
        styles.text
      )}
    >
      <span className={cn('h-1.5 w-1.5 rounded-full', styles.dot)} />
      {status}
    </span>
  )
}

// 单个案件项组件
function CaseItem({ item, index }: { item: MockCaseItem; index: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{
        delay: index * 0.1,
        duration: 0.3,
      }}
      className={cn(
        'group/item relative rounded-lg border border-white/5 bg-white/5 p-3',
        'transition-all duration-200',
        'hover:border-white/20 hover:bg-white/10'
      )}
    >
      {/* 顶部：状态和金额 */}
      <div className="mb-2 flex items-center justify-between">
        <StatusBadge status={item.status} />
        <span className="text-sm font-semibold text-white/90">
          {formatAmount(item.amount)}
        </span>
      </div>

      {/* 案号 */}
      <p className="mb-1 truncate text-sm font-medium text-white/70">
        {item.caseNumber}
      </p>

      {/* 案件类型 */}
      <p className="text-xs text-white/50">{item.caseType}</p>

      {/* Hover 时的左侧高亮线 */}
      <div
        className={cn(
          'absolute left-0 top-1/2 h-8 w-0.5 -translate-y-1/2 rounded-full',
          'bg-purple-500 opacity-0 transition-opacity duration-200',
          'group-hover/item:opacity-100'
        )}
      />
    </motion.div>
  )
}

// 主组件
export function CaseListMockUI() {
  return (
    <div className="flex flex-col gap-3">
      {/* 列表标题 */}
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-white/40">最近案件</span>
        <span className="text-sm text-white/30">{MOCK_CASES.length} 件</span>
      </div>

      {/* 案件列表 */}
      <div className="flex flex-col gap-2">
        {MOCK_CASES.map((item, index) => (
          <CaseItem key={item.id} item={item} index={index} />
        ))}
      </div>
    </div>
  )
}
