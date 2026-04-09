/**
 * FloatingCards - 浮动卡片组件
 * @module features/home/components/HeroSection/FloatingCards
 *
 * 实现三个浮动卡片（案件自动归档、AI文书生成、数据可视化）
 * Requirements: 2.10, 2.11, 2.12
 */

import { motion } from 'framer-motion'

import { cn } from '@/lib/utils'

import { FLOATING_CARDS, floatAnimation } from '../../constants'
import type { FloatingCardData } from '../../types'

// 卡片位置样式映射
const positionStyles: Record<FloatingCardData['position'], string> = {
  left: 'left-[5%] top-[20%]',
  right: 'right-[5%] top-[30%]',
  bottom: 'left-[15%] bottom-[15%]',
}

// 卡片颜色方案映射
const colorSchemeStyles: Record<FloatingCardData['colorScheme'], {
  bg: string
  border: string
  iconBg: string
  iconColor: string
}> = {
  purple: {
    bg: 'bg-purple-500/10',
    border: 'border-purple-500/30',
    iconBg: 'bg-purple-500/20',
    iconColor: 'text-purple-400',
  },
  cyan: {
    bg: 'bg-cyan-500/10',
    border: 'border-cyan-500/30',
    iconBg: 'bg-cyan-500/20',
    iconColor: 'text-cyan-400',
  },
  pink: {
    bg: 'bg-pink-500/10',
    border: 'border-pink-500/30',
    iconBg: 'bg-pink-500/20',
    iconColor: 'text-pink-400',
  },
}

// 动画延迟配置
const animationDelays: Record<FloatingCardData['position'], number> = {
  left: 0,
  right: 2,
  bottom: 4,
}

interface FloatingCardProps {
  data: FloatingCardData
}

function FloatingCard({ data }: FloatingCardProps) {
  const { icon: Icon, title, description, position, colorScheme } = data
  const colors = colorSchemeStyles[colorScheme]
  const delay = animationDelays[position]

  return (
    <motion.div
      className={cn(
        'absolute hidden lg:block',
        positionStyles[position]
      )}
      animate={floatAnimation.animate}
      transition={{
        ...floatAnimation.transition,
        delay,
      }}
    >
      <div
        className={cn(
          'rounded-xl border p-4 backdrop-blur-sm',
          'shadow-lg shadow-black/20',
          colors.bg,
          colors.border
        )}
      >
        <div className="flex items-center gap-3">
          <div
            className={cn(
              'flex h-10 w-10 items-center justify-center rounded-lg',
              colors.iconBg
            )}
          >
            <Icon className={cn('h-5 w-5', colors.iconColor)} />
          </div>
          <div>
            <h4 className="text-sm font-medium text-white">{title}</h4>
            <p className="text-xs text-white/60">{description}</p>
          </div>
        </div>
      </div>
    </motion.div>
  )
}

export function FloatingCards() {
  return (
    <>
      {FLOATING_CARDS.map((card) => (
        <FloatingCard key={card.title} data={card} />
      ))}
    </>
  )
}
