/**
 * HeroSection - Hero 区域组件
 * @module features/home/components/HeroSection
 *
 * 组装所有 Hero 子组件，实现首屏视觉效果
 * - 100vh 高度
 * - OrbBackground 作为背景层
 * - FloatingCards 作为装饰元素
 * - 主内容垂直居中（HeroBadge, HeroTitle, HeroButtons, StatsCounter）
 *
 * Requirements: 2.1
 */

import { motion } from 'framer-motion'

import { cn } from '@/lib/utils'

import { springConfig } from '../../constants'
import { FloatingCards } from './FloatingCards'
import { HeroBadge } from './HeroBadge'
import { HeroButtons } from './HeroButtons'
import { HeroTitle } from './HeroTitle'
import { OrbBackground } from './OrbBackground'
import { StatsCounter } from './StatsCounter'

interface HeroSectionProps {
  /** 自定义类名 */
  className?: string
}

/**
 * Hero 区域组件
 *
 * 首页顶部的主视觉区域，包含：
 * - 动态光斑背景
 * - 产品徽章
 * - 渐变标题和副标题
 * - CTA 按钮组
 * - 统计计数器
 * - 浮动装饰卡片（仅桌面端显示）
 */
export function HeroSection({ className }: HeroSectionProps) {
  return (
    <section
      className={cn(
        'relative flex min-h-[85vh] items-center justify-center overflow-hidden',
        // 统一深色背景 - 与 FeaturesSection 融合
        'bg-gray-950',
        className
      )}
    >
      {/* 背景层 - 动态光斑 */}
      <OrbBackground />

      {/* 浮动装饰卡片（仅桌面端显示） */}
      <FloatingCards />

      {/* 主内容区域 - 垂直居中 */}
      <div className="relative z-10 mx-auto w-full max-w-5xl px-4 sm:px-6 lg:px-8 2xl:max-w-6xl 3xl:max-w-7xl">
        <motion.div
          className="flex flex-col items-center gap-6"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ ...springConfig, delay: 0.1 }}
        >
          {/* 产品徽章 */}
          <HeroBadge />

          {/* 主标题和副标题 */}
          <HeroTitle />

          {/* CTA 按钮组 */}
          <HeroButtons className="mt-2" />

          {/* 统计计数器 */}
          <StatsCounter className="mt-8" />
        </motion.div>
      </div>

      {/* 底部渐变过渡 - 与下一区域融合 */}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-32 bg-gradient-to-b from-transparent to-gray-950" />
    </section>
  )
}

// 导出子组件供单独使用
export { OrbBackground } from './OrbBackground'
export { HeroBadge } from './HeroBadge'
export { HeroTitle } from './HeroTitle'
export { HeroButtons } from './HeroButtons'
export { StatsCounter } from './StatsCounter'
export { FloatingCards } from './FloatingCards'
