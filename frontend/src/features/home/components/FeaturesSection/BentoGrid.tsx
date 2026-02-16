/**
 * BentoGrid - Bento Grid 网格布局组件
 * @module features/home/components/FeaturesSection/BentoGrid
 *
 * 实现 CSS Grid 4 列布局和 stagger 入场动画
 * Requirements: 3.1, 3.2, 3.3
 */

import { motion, useInView } from 'framer-motion'
import { useRef } from 'react'

import { cn } from '@/lib/utils'

import { FEATURES_DATA } from '../../constants'
import { BentoCard } from './BentoCard'
import { CaseListMockUI } from './CaseListMockUI'

interface BentoGridProps {
  className?: string
}

// Stagger 动画变体 - 增强版
const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.08,
      delayChildren: 0.1,
    },
  },
}

// 单个卡片的入场动画变体 - 增强版
const itemVariants = {
  hidden: {
    opacity: 0,
    y: 60,
    scale: 0.9,
    filter: 'blur(10px)',
  },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    filter: 'blur(0px)',
    transition: {
      type: 'spring' as const,
      stiffness: 100,
      damping: 15,
      mass: 0.8,
    },
  },
}

export function BentoGrid({ className }: BentoGridProps) {
  const gridRef = useRef<HTMLDivElement>(null)
  const isInView = useInView(gridRef, {
    once: true,
    margin: '-50px',
  })

  return (
    <motion.div
      ref={gridRef}
      className={cn(
        // CSS Grid 布局 - 4K 超宽屏幕支持
        'grid gap-6',
        // 4K 超宽屏幕：5 列
        '3xl:grid-cols-5 3xl:gap-8',
        // 超宽屏幕：4 列
        '2xl:grid-cols-4',
        // 桌面端：4 列
        'lg:grid-cols-4',
        // 平板端：2 列
        'md:grid-cols-2',
        // 移动端：1 列
        'grid-cols-1',
        className
      )}
      variants={containerVariants}
      initial="hidden"
      animate={isInView ? 'visible' : 'hidden'}
    >
      {FEATURES_DATA.map((feature, index) => (
        <motion.div
          key={feature.title}
          variants={itemVariants}
          custom={index}
          className={cn(
            'h-full',
            // 根据卡片尺寸设置 grid span
            feature.size === 'large' && 'md:col-span-2 md:row-span-2',
            feature.size === 'wide' && 'md:col-span-2',
            feature.size === 'tall' && 'row-span-2'
          )}
        >
          <BentoCard
            icon={feature.icon}
            title={feature.title}
            description={feature.description}
            size={feature.size}
            colorScheme={feature.colorScheme}
          >
            {/* 案件管理卡片（第一个带有 hasVisual 的卡片）包含 CaseListMockUI */}
            {feature.hasVisual && <CaseListMockUI />}
          </BentoCard>
        </motion.div>
      ))}
    </motion.div>
  )
}
