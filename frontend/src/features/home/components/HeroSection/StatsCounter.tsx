/**
 * StatsCounter - 统计计数器组件
 * @module features/home/components/HeroSection/StatsCounter
 *
 * 显示统计数字，带有从 0 计数到目标值的动画效果
 * 使用 useInView 触发动画
 *
 * Requirements: 2.8, 2.9
 */

import { motion } from 'framer-motion'
import { useCounterAnimation } from '../../hooks/use-counter-animation'
import { STATS_DATA, fadeInUp, staggerContainer } from '../../constants'
import type { StatItem } from '../../types'

interface StatsCounterProps {
  /** 自定义类名 */
  className?: string
  /** 自定义统计数据，默认使用 STATS_DATA */
  data?: StatItem[]
  /** 动画持续时间（毫秒） */
  duration?: number
}

interface StatItemProps {
  item: StatItem
  duration: number
}

/**
 * 单个统计项组件
 */
function StatItemComponent({ item, duration }: StatItemProps) {
  const { count, ref, isComplete } = useCounterAnimation(item.value, {
    duration,
    startOnView: true,
    triggerOnce: true,
  })

  return (
    <motion.div
      ref={ref as React.RefObject<HTMLDivElement>}
      variants={fadeInUp}
      className="text-center"
    >
      <div className="text-4xl font-bold text-white md:text-5xl">
        <span data-testid="counter-value">{count}</span>
        {item.suffix && <span>{item.suffix}</span>}
        {/* 显示 + 号表示"以上"，带弹跳动画效果 */}
        {isComplete && item.value >= 10 && (
          <motion.span
            className="inline-block bg-gradient-to-r from-cyan-400 to-purple-400 bg-clip-text text-transparent"
            initial={{ opacity: 0, scale: 0, rotate: -180, y: 20 }}
            animate={{ opacity: 1, scale: 1, rotate: 0, y: 0 }}
            transition={{
              type: 'spring',
              stiffness: 400,
              damping: 10,
              delay: 0.15,
            }}
          >
            +
          </motion.span>
        )}
      </div>
      <div className="mt-2 text-sm text-muted-foreground md:text-base">
        {item.label}
      </div>
    </motion.div>
  )
}

/**
 * 统计计数器组件
 *
 * 显示三个统计数字（核心功能模块、API接口、小时自动化）
 * 当组件进入视口时，数字从 0 动画计数到目标值
 *
 * @example
 * ```tsx
 * <StatsCounter />
 *
 * // 自定义数据
 * <StatsCounter data={customStats} duration={1500} />
 * ```
 */
export function StatsCounter({
  className = '',
  data = STATS_DATA,
  duration = 2000,
}: StatsCounterProps) {
  return (
    <motion.div
      variants={staggerContainer}
      initial="initial"
      whileInView="animate"
      viewport={{ once: true, amount: 0.5 }}
      className={`grid grid-cols-3 gap-8 md:gap-12 ${className}`}
    >
      {data.map((item) => (
        <StatItemComponent key={item.label} item={item} duration={duration} />
      ))}
    </motion.div>
  )
}
