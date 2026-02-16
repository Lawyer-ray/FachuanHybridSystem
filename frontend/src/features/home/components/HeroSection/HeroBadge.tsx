/**
 * HeroBadge - 产品徽章组件
 * @module features/home/components/HeroSection/HeroBadge
 *
 * 显示产品徽章和脉冲动画绿点
 * Requirements: 2.3
 */

import { motion } from 'framer-motion'

import { pulseAnimation } from '../../constants'

interface HeroBadgeProps {
  className?: string
}

export function HeroBadge({ className }: HeroBadgeProps) {
  return (
    <div className={className}>
      <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-white/80 backdrop-blur-sm">
        <motion.span
          className="h-2 w-2 rounded-full bg-green-500"
          animate={pulseAnimation.animate}
          transition={pulseAnimation.transition}
        />
        免费开源 · 持续更新
      </span>
    </div>
  )
}
