/**
 * ResultCards - 短信处理结果卡片组件
 * @module features/home/components/SMSFlowDemo/ResultCards
 *
 * 实现结果卡片（文书已归档、已重命名、开庭提醒、费用异常）
 * 使用 Framer Motion 实现交错淡入动画
 * Requirements: 4.1
 */

import { motion, AnimatePresence } from 'framer-motion'
import type { LucideIcon } from 'lucide-react'

import { cn } from '@/lib/utils'
import { SMS_RESULT_CARDS } from '../../constants'

// ============================================================================
// 类型定义
// ============================================================================

interface ResultCardData {
  id: string
  title: string
  description: string
  icon: LucideIcon
  colorScheme: 'green' | 'blue' | 'yellow' | 'red'
}

interface ResultCardsProps {
  /** 控制每个卡片是否可见的布尔数组 */
  visibleCards: boolean[]
  /** 自定义类名 */
  className?: string
}

interface ResultCardProps {
  /** 卡片数据 */
  card: ResultCardData
  /** 卡片索引，用于动画延迟 */
  index: number
}

// ============================================================================
// 颜色配置
// ============================================================================

const colorSchemeMap: Record<
  string,
  {
    iconBg: string
    border: string
    shadow: string
    accent: string
  }
> = {
  green: {
    iconBg: 'bg-gradient-to-br from-green-500 to-green-600',
    border: 'border-green-500/30',
    shadow: 'shadow-green-500/10',
    accent: 'text-green-400',
  },
  blue: {
    iconBg: 'bg-gradient-to-br from-blue-500 to-blue-600',
    border: 'border-blue-500/30',
    shadow: 'shadow-blue-500/10',
    accent: 'text-blue-400',
  },
  yellow: {
    iconBg: 'bg-gradient-to-br from-yellow-500 to-yellow-600',
    border: 'border-yellow-500/30',
    shadow: 'shadow-yellow-500/10',
    accent: 'text-yellow-400',
  },
  red: {
    iconBg: 'bg-gradient-to-br from-red-500 to-red-600',
    border: 'border-red-500/30',
    shadow: 'shadow-red-500/10',
    accent: 'text-red-400',
  },
}

// ============================================================================
// 动画配置
// ============================================================================

const cardVariants = {
  hidden: {
    opacity: 0,
    y: 20,
    scale: 0.95,
  },
  visible: (index: number) => ({
    opacity: 1,
    y: 0,
    scale: 1,
    transition: {
      type: 'spring' as const,
      stiffness: 100,
      damping: 15,
      delay: index * 0.15, // 交错动画延迟
    },
  }),
  exit: {
    opacity: 0,
    y: -10,
    scale: 0.95,
    transition: {
      duration: 0.2,
    },
  },
}

// ============================================================================
// 单个结果卡片组件
// ============================================================================

function ResultCard({ card, index }: ResultCardProps) {
  const Icon = card.icon
  const colors = colorSchemeMap[card.colorScheme] || colorSchemeMap.green

  return (
    <motion.div
      variants={cardVariants}
      initial="hidden"
      animate="visible"
      exit="exit"
      custom={index}
      className={cn(
        'relative flex items-center gap-3 rounded-xl p-3',
        'border bg-gray-900/60 backdrop-blur-sm',
        'transition-colors duration-300',
        colors.border,
        colors.shadow,
        'shadow-lg'
      )}
    >
      {/* 图标容器 */}
      <div
        className={cn(
          'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl',
          colors.iconBg
        )}
      >
        <Icon className="h-4 w-4 text-white" />
      </div>

      {/* 文本内容 */}
      <div className="min-w-0 flex-1">
        <h4 className={cn('text-sm font-medium', colors.accent)}>
          {card.title}
        </h4>
        <p className="truncate text-xs text-gray-400">{card.description}</p>
      </div>
    </motion.div>
  )
}

// ============================================================================
// 结果卡片网格组件
// ============================================================================

export function ResultCards({ visibleCards, className }: ResultCardsProps) {
  // 将 SMS_RESULT_CARDS 转换为带有正确类型的数据
  const cards = SMS_RESULT_CARDS as ResultCardData[]

  return (
    <div
      className={cn(
        'grid gap-3',
        // 超宽屏幕：4 列
        '2xl:grid-cols-4',
        // 默认垂直堆叠，大屏幕 2x2 网格
        'grid-cols-1 sm:grid-cols-2',
        className
      )}
    >
      <AnimatePresence mode="popLayout">
        {cards.map((card, index) =>
          visibleCards[index] ? (
            <ResultCard key={card.id} card={card} index={index} />
          ) : null
        )}
      </AnimatePresence>
    </div>
  )
}
