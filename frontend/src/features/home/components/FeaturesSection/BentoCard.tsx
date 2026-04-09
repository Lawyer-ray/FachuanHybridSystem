/**
 * BentoCard - Bento Grid 功能卡片组件
 * @module features/home/components/FeaturesSection/BentoCard
 *
 * 实现不同尺寸（default、large、wide、tall）和 hover 效果
 * Requirements: 3.4
 */

import { motion } from 'framer-motion'

import { cn } from '@/lib/utils'

import type { BentoCardColorScheme, BentoCardProps, BentoCardSize } from '../../types'

// 卡片尺寸样式映射（CSS Grid span）
const sizeStyles: Record<BentoCardSize, string> = {
  default: 'col-span-1 row-span-1',
  large: 'col-span-1 row-span-2 md:col-span-2 md:row-span-2',
  wide: 'col-span-1 md:col-span-2 row-span-1',
  tall: 'col-span-1 row-span-2',
}

// 卡片颜色方案映射
const colorSchemeStyles: Record<BentoCardColorScheme, {
  iconBg: string
  iconColor: string
  gradientLine: string
  hoverBorder: string
}> = {
  'style-1': {
    iconBg: 'bg-transparent border border-purple-500/30',
    iconColor: 'text-purple-400',
    gradientLine: 'from-purple-500 via-purple-400 to-transparent',
    hoverBorder: 'group-hover:border-purple-500/50',
  },
  'style-2': {
    iconBg: 'bg-transparent border border-cyan-500/30',
    iconColor: 'text-cyan-400',
    gradientLine: 'from-cyan-500 via-cyan-400 to-transparent',
    hoverBorder: 'group-hover:border-cyan-500/50',
  },
  'style-3': {
    iconBg: 'bg-transparent border border-pink-500/30',
    iconColor: 'text-pink-400',
    gradientLine: 'from-pink-500 via-pink-400 to-transparent',
    hoverBorder: 'group-hover:border-pink-500/50',
  },
}

export function BentoCard({
  icon: Icon,
  title,
  description,
  size = 'default',
  colorScheme = 'style-1',
  children,
}: BentoCardProps) {
  const colors = colorSchemeStyles[colorScheme]

  return (
    <motion.div
      className={cn(
        'group relative h-full',
        sizeStyles[size]
      )}
      whileHover={{ y: -4 }}
      transition={{
        type: 'spring',
        stiffness: 300,
        damping: 20,
      }}
    >
      {/* 卡片容器 */}
      <div
        className={cn(
          'relative h-full overflow-hidden rounded-3xl border border-white/10 bg-white/[0.03] backdrop-blur-sm',
          'p-6',
          'transition-all duration-400',
          'hover:bg-white/[0.08]',
          colors.hoverBorder
        )}
      >
        {/* 顶部渐变线 - hover 时显示 */}
        <div
          className={cn(
            'absolute inset-x-0 top-0 h-[1px] bg-gradient-to-r opacity-0 transition-opacity duration-400',
            'group-hover:opacity-100',
            colors.gradientLine
          )}
        />

        {/* 卡片内容 */}
        <div className="flex h-full flex-col gap-4">
          {/* 图标 - 带 hover 动画 */}
          <motion.div
            className={cn(
              'flex items-center justify-center rounded-2xl',
              'h-14 w-14',
              colors.iconBg,
              'transition-all duration-300',
              'group-hover:scale-110 group-hover:shadow-lg',
              colorScheme === 'style-1' && 'group-hover:shadow-purple-500/20',
              colorScheme === 'style-2' && 'group-hover:shadow-cyan-500/20',
              colorScheme === 'style-3' && 'group-hover:shadow-pink-500/20'
            )}
          >
            <motion.div
              className="relative"
              whileHover={{ rotate: [0, -10, 10, 0] }}
              transition={{ duration: 0.5 }}
            >
              <Icon
                className={cn(
                  'h-7 w-7 transition-transform duration-300',
                  colors.iconColor,
                  'group-hover:scale-110'
                )}
                strokeWidth={1.5}
              />
            </motion.div>
          </motion.div>

          {/* 标题 */}
          <h3 className="text-xl font-bold text-white">
            {title}
          </h3>

          {/* 描述 */}
          <p className="text-[15px] leading-relaxed text-white/60">
            {description}
          </p>

          {/* 自定义内容（如案件列表模拟 UI） */}
          {children && (
            <div className="mt-auto flex-1 min-h-0">
              {children}
            </div>
          )}
        </div>

        {/* 背景装饰 - 渐变光晕 */}
        <div
          className={cn(
            'pointer-events-none absolute -bottom-20 -right-20 h-40 w-40 rounded-full opacity-0 blur-3xl transition-opacity duration-500',
            'group-hover:opacity-30',
            colorScheme === 'style-1' && 'bg-purple-500',
            colorScheme === 'style-2' && 'bg-cyan-500',
            colorScheme === 'style-3' && 'bg-pink-500'
          )}
        />
      </div>
    </motion.div>
  )
}
