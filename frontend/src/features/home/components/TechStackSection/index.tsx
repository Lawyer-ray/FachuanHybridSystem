/**
 * TechStackSection - 技术栈展示区域组件
 * @module features/home/components/TechStackSection
 *
 * 展示系统使用的技术栈和架构亮点
 * Requirements: 6.1, 6.2, 6.3, 6.4, 6.5
 */

import { motion } from 'framer-motion'
import { ArrowRight } from 'lucide-react'

import { cn } from '@/lib/utils'
import { TECH_STACK, ARCH_HIGHLIGHTS } from '../../constants'
import type { TechCategory, TechItem } from '../../types'

// ============================================================================
// 类型定义
// ============================================================================

interface TechStackSectionProps {
  className?: string
}

// ============================================================================
// 技术项卡片组件
// ============================================================================

interface TechItemCardProps {
  item: TechItem
  index: number
}

function TechItemCard({ item, index }: TechItemCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      whileInView={{ opacity: 1, x: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.4, delay: index * 0.1 }}
      whileHover={{ x: 8 }}
      className={cn(
        'group flex items-center gap-3 rounded-lg border border-gray-700/50 p-3',
        'bg-gray-800/30 backdrop-blur-sm',
        'transition-all duration-300',
        'hover:border-cyan-500/30 hover:bg-gray-800/50'
      )}
    >
      {/* 图标 */}
      <span className="text-2xl">{item.icon}</span>

      {/* 文本内容 */}
      <div className="flex-1 min-w-0">
        <h4 className="text-sm font-medium text-white">{item.name}</h4>
        <p className="text-xs text-gray-400 truncate">{item.description}</p>
      </div>

      {/* Hover 箭头 */}
      <ArrowRight
        className={cn(
          'h-4 w-4 flex-shrink-0 text-gray-600 transition-all duration-300',
          'opacity-0 group-hover:opacity-100 group-hover:text-cyan-400'
        )}
      />
    </motion.div>
  )
}

// ============================================================================
// 技术分类卡片组件
// ============================================================================

interface TechCategoryCardProps {
  category: TechCategory
  index: number
}

function TechCategoryCard({ category, index }: TechCategoryCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 30 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.5, delay: index * 0.15 }}
      className={cn(
        'rounded-2xl border border-gray-700/50 p-6',
        'bg-gray-900/50 backdrop-blur-sm'
      )}
    >
      {/* 分类标题 */}
      <div className="mb-5 flex items-center gap-3">
        <span className="text-3xl">{category.icon}</span>
        <h3 className="text-lg font-semibold text-white">{category.title}</h3>
      </div>

      {/* 技术项列表 */}
      <div className="space-y-3">
        {category.items.map((item, itemIndex) => (
          <TechItemCard key={item.name} item={item} index={itemIndex} />
        ))}
      </div>
    </motion.div>
  )
}

// ============================================================================
// 架构亮点统计组件
// ============================================================================

function ArchHighlights() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.6, delay: 0.3 }}
      className={cn(
        'mt-10 rounded-2xl border border-gray-700/50 p-8',
        'bg-gradient-to-br from-gray-900/80 to-gray-800/50 backdrop-blur-sm'
      )}
    >
      <h3 className="mb-6 text-center text-lg font-semibold text-white">
        架构亮点
      </h3>

      <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
        {ARCH_HIGHLIGHTS.map((highlight, index) => (
          <motion.div
            key={highlight.label}
            initial={{ opacity: 0, scale: 0.9 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 0.4, delay: 0.4 + index * 0.1 }}
            className="text-center"
          >
            <div className="mb-2 text-4xl font-bold">
              <span className="bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
                {highlight.value}
              </span>
              <span className="text-cyan-400">{highlight.suffix}</span>
            </div>
            <div className="text-sm text-gray-400">{highlight.label}</div>
          </motion.div>
        ))}
      </div>
    </motion.div>
  )
}

// ============================================================================
// 主组件
// ============================================================================

export function TechStackSection({ className }: TechStackSectionProps) {
  return (
    <section
      id="tech"
      className={cn('relative overflow-hidden bg-gray-950 py-16 md:py-20', className)}
    >
      {/* 背景装饰 - 与其他区域融合 */}
      <div className="pointer-events-none absolute inset-0">
        {/* 顶部渐变过渡 */}
        <div className="absolute inset-x-0 top-0 h-32 bg-gradient-to-b from-gray-950 to-transparent" />
        <div className="absolute left-1/3 top-1/4 h-64 w-64 rounded-full bg-blue-500/5 blur-3xl" />
        <div className="absolute bottom-1/4 right-1/3 h-64 w-64 rounded-full bg-cyan-500/5 blur-3xl" />
      </div>

      <div className="relative mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 2xl:max-w-[1600px] 3xl:max-w-[2400px]">
        {/* 区域标题 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="mb-12 text-center"
        >
          <h2 className="mb-4 text-3xl font-bold text-white md:text-4xl">
            技术
            <span className="bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
              架构
            </span>
          </h2>
          <p className="mx-auto max-w-2xl text-base text-gray-400 md:text-lg">
            基于现代化技术栈构建，采用四层架构设计，确保系统的可扩展性和可维护性
          </p>
        </motion.div>

        {/* 技术分类网格 - 响应式布局 */}
        <div
          className={cn(
            'grid gap-6',
            // 超宽屏幕：三列布局
            '2xl:grid-cols-3',
            // 桌面端：三列布局
            'lg:grid-cols-3',
            // 移动端：单列布局
            'grid-cols-1'
          )}
        >
          {TECH_STACK.map((category, index) => (
            <TechCategoryCard
              key={category.title}
              category={category}
              index={index}
            />
          ))}
        </div>

        {/* 架构亮点统计 */}
        <ArchHighlights />
      </div>
    </section>
  )
}
