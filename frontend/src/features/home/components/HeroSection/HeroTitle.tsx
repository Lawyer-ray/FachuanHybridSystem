/**
 * HeroTitle - 渐变色动画标题组件
 * @module features/home/components/HeroSection/HeroTitle
 *
 * 实现主标题和副标题，使用流畅的整体动画效果
 * 始终使用深色主题配色，不受明暗模式影响
 * Requirements: 2.4, 2.5
 */

import { motion } from 'framer-motion'

import { springConfig } from '../../constants'

export function HeroTitle() {
  return (
    <div className="text-center">
      {/* 主标题 - 整体淡入 + 上移动画 */}
      <motion.h1
        className="text-4xl font-bold tracking-tight sm:text-5xl md:text-6xl lg:text-7xl"
        initial={{ opacity: 0, y: 40 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{
          type: 'spring' as const,
          stiffness: 80,
          damping: 20,
          delay: 0.2,
        }}
      >
        {/* 第一部分：白色文字（固定颜色，不受主题影响） */}
        <motion.span
          className="text-white"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.3 }}
        >
          法穿AI 智能案件
        </motion.span>

        {/* 第二部分：渐变文字 - 带流动渐变效果 */}
        <motion.span
          className="inline-block bg-gradient-to-r from-purple-500 via-pink-500 to-cyan-500 bg-clip-text text-transparent"
          style={{ backgroundSize: '200% 100%' }}
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{
            opacity: 1,
            scale: 1,
            backgroundPosition: ['0% 50%', '100% 50%', '0% 50%'],
          }}
          transition={{
            opacity: { duration: 0.6, delay: 0.5 },
            scale: { type: 'spring' as const, stiffness: 100, damping: 15, delay: 0.5 },
            backgroundPosition: { duration: 6, repeat: Infinity, ease: 'linear' },
          }}
        >
          管理系统
        </motion.span>
      </motion.h1>

      {/* 副标题 - 灰色文字（固定颜色，不受主题影响） */}
      <motion.p
        className="mx-auto mt-6 max-w-2xl text-lg text-gray-400 sm:text-xl"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ ...springConfig, delay: 0.7 }}
      >
        智能化法律案件全生命周期管理，AI 驱动的文书生成与自动化工作流，
        让律师专注于专业价值创造
      </motion.p>
    </div>
  )
}
