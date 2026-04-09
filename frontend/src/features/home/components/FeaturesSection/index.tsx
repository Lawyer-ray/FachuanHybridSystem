/**
 * FeaturesSection - 功能特性区域组件
 * @module features/home/components/FeaturesSection
 *
 * 展示系统核心功能的 Bento Grid 布局区域
 * - 包含区域标题和描述
 * - 使用 BentoGrid 组件展示功能卡片
 * - 响应式布局：桌面端 4 列，平板端 2 列，移动端 1 列
 *
 * Requirements: 3.6, 3.7
 */

import { motion, useInView } from 'framer-motion'
import { Sparkles } from 'lucide-react'
import { useRef } from 'react'

import { cn } from '@/lib/utils'

import { springConfig } from '../../constants'
import { BentoGrid } from './BentoGrid'

// 导出子组件供外部使用
export { BentoCard } from './BentoCard'
export { BentoGrid } from './BentoGrid'
export { CaseListMockUI } from './CaseListMockUI'

interface FeaturesSectionProps {
  className?: string
}

// 区域标题动画变体
const titleVariants = {
  hidden: { opacity: 0, y: 30 },
  visible: {
    opacity: 1,
    y: 0,
    transition: {
      ...springConfig,
      delay: 0.1,
    },
  },
}

// 区域描述动画变体
const descriptionVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: {
    opacity: 1,
    y: 0,
    transition: {
      ...springConfig,
      delay: 0.2,
    },
  },
}

// 徽章动画变体
const badgeVariants = {
  hidden: { opacity: 0, scale: 0.8 },
  visible: {
    opacity: 1,
    scale: 1,
    transition: {
      ...springConfig,
      delay: 0,
    },
  },
}

export function FeaturesSection({ className }: FeaturesSectionProps) {
  const sectionRef = useRef<HTMLElement>(null)
  const isInView = useInView(sectionRef, {
    once: true,
    margin: '-100px',
  })

  return (
    <section
      id="features"
      ref={sectionRef}
      className={cn(
        // 区域基础样式
        'relative w-full',
        // 垂直内边距
        'py-16 md:py-20',
        // 统一深色背景 - 与 SMSFlowDemo 融合
        'bg-gray-950',
        className
      )}
    >
      {/* 最大宽度容器 - 4K 超宽屏幕支持 */}
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 2xl:max-w-[1600px] 3xl:max-w-[2400px]">
        {/* 区域头部 */}
        <div className="mb-10 flex flex-col items-center text-center">
          {/* 徽章 */}
          <motion.div
            variants={badgeVariants}
            initial="hidden"
            animate={isInView ? 'visible' : 'hidden'}
            className={cn(
              'mb-4 inline-flex items-center gap-2 rounded-full',
              'border border-purple-500/30 bg-purple-500/10 px-4 py-1.5',
              'text-sm font-medium text-purple-300'
            )}
          >
            <Sparkles className="h-4 w-4" />
            <span>核心功能</span>
          </motion.div>

          {/* 标题 */}
          <motion.h2
            variants={titleVariants}
            initial="hidden"
            animate={isInView ? 'visible' : 'hidden'}
            className={cn(
              'mb-4 text-3xl font-bold tracking-tight text-white',
              'sm:text-4xl md:text-5xl'
            )}
          >
            强大的
            <span className="bg-gradient-to-r from-purple-400 via-pink-400 to-cyan-400 bg-clip-text text-transparent">
              功能特性
            </span>
          </motion.h2>

          {/* 描述 */}
          <motion.p
            variants={descriptionVariants}
            initial="hidden"
            animate={isInView ? 'visible' : 'hidden'}
            className={cn(
              'max-w-2xl text-base text-white/60',
              'sm:text-lg'
            )}
          >
            从案件管理到 AI 文书生成，从自动化引擎到数据安全，
            <br className="hidden sm:block" />
            全方位覆盖法律工作的每一个环节
          </motion.p>
        </div>

        {/* Bento Grid 功能卡片网格 */}
        <BentoGrid />
      </div>

      {/* 背景装饰 - 多层渐变光晕 */}
      <div className="pointer-events-none absolute inset-0 -z-10">
        {/* 顶部渐变过渡 - 与 HeroSection 融合 */}
        <div className="absolute inset-x-0 top-0 h-32 bg-gradient-to-b from-gray-950 to-transparent" />
        {/* 紫色光晕 - 左上 */}
        <div className="absolute left-1/4 top-1/4 h-[500px] w-[500px] rounded-full bg-purple-600/10 blur-[120px]" />
        {/* 青色光晕 - 右下 */}
        <div className="absolute bottom-1/4 right-1/4 h-[400px] w-[400px] rounded-full bg-cyan-500/8 blur-[100px]" />
        {/* 底部渐变过渡 - 与下一区域融合 */}
        <div className="absolute inset-x-0 bottom-0 h-32 bg-gradient-to-b from-transparent to-gray-950" />
      </div>
    </section>
  )
}

// 默认导出
export default FeaturesSection
