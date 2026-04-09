/**
 * SMSFlowDemo - 法院短信处理流程演示组件
 * @module features/home/components/SMSFlowDemo
 *
 * 展示法院短信自动处理的完整流程演示
 * Requirements: 4.1, 4.2, 4.3, 4.9
 */

import { motion, AnimatePresence } from 'framer-motion'
import { ArrowRight, Forward } from 'lucide-react'

import { cn } from '@/lib/utils'
import { useFlowAnimation } from '../../hooks/use-flow-animation'
import { PhoneMockup } from './PhoneMockup'
import { ProcessNodes } from './ProcessNodes'
import { ResultCards } from './ResultCards'
import { FlowControls } from './FlowControls'

// ============================================================================
// 导出子组件
// ============================================================================

export { PhoneMockup } from './PhoneMockup'
export { ProcessNodes } from './ProcessNodes'
export { ResultCards } from './ResultCards'
export { FlowControls } from './FlowControls'

// ============================================================================
// 类型定义
// ============================================================================

interface SMSFlowDemoProps {
  /** 自定义类名 */
  className?: string
}

// ============================================================================
// 转发卡片组件
// ============================================================================

interface ForwardCardProps {
  visible: boolean
  arrowActive: boolean
}

/**
 * 转发卡片 - 显示短信转发到系统的过程
 */
function ForwardCard({ visible, arrowActive }: ForwardCardProps) {
  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.9 }}
          transition={{ type: 'spring', stiffness: 200, damping: 20 }}
          className="flex flex-col items-center gap-3"
        >
          {/* 转发图标 */}
          <div
            className={cn(
              'flex h-12 w-12 items-center justify-center rounded-xl',
              'bg-gradient-to-br from-blue-500 to-cyan-500',
              'shadow-lg shadow-blue-500/30'
            )}
          >
            <Forward className="h-6 w-6 text-white" />
          </div>

          {/* 转发文字 */}
          <span className="text-sm font-medium text-gray-400">自动转发</span>

          {/* 箭头动画 */}
          <motion.div
            className={cn(
              'flex items-center gap-1',
              arrowActive ? 'text-cyan-400' : 'text-gray-600'
            )}
            animate={
              arrowActive
                ? {
                    x: [0, 8, 0],
                  }
                : {}
            }
            transition={
              arrowActive
                ? {
                    duration: 1,
                    repeat: Infinity,
                    ease: 'easeInOut',
                  }
                : {}
            }
          >
            <ArrowRight className="h-4 w-4" />
            <ArrowRight className="h-4 w-4 -ml-3 opacity-60" />
            <ArrowRight className="h-4 w-4 -ml-3 opacity-30" />
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

// ============================================================================
// 主组件
// ============================================================================

/**
 * 短信处理流程演示组件
 *
 * 展示法院短信从接收到处理完成的完整流程：
 * 1. 手机接收短信通知
 * 2. 自动转发到系统
 * 3. 7个处理节点依次执行
 * 4. 显示处理结果卡片
 *
 * @example
 * ```tsx
 * <SMSFlowDemo className="py-20" />
 * ```
 */
export function SMSFlowDemo({ className }: SMSFlowDemoProps) {
  const { state, currentStep, isPlaying, play, reset, totalSteps } =
    useFlowAnimation()

  return (
    <section
      id="sms-flow"
      className={cn('relative overflow-hidden bg-gray-950 py-16 md:py-20', className)}
    >
      {/* 背景装饰 - 与 FeaturesSection 融合 */}
      <div className="pointer-events-none absolute inset-0">
        {/* 顶部渐变过渡 - 与上一区域融合 */}
        <div className="absolute inset-x-0 top-0 h-32 bg-gradient-to-b from-gray-950 to-transparent" />
        {/* 渐变光晕 */}
        <div className="absolute left-1/4 top-1/4 h-64 w-64 rounded-full bg-cyan-500/10 blur-3xl" />
        <div className="absolute bottom-1/4 right-1/4 h-64 w-64 rounded-full bg-blue-500/10 blur-3xl" />
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
            法院短信
            <span className="bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
              智能处理
            </span>
          </h2>
          <p className="mx-auto max-w-2xl text-base text-gray-400 md:text-lg">
            自动接收法院短信，智能解析链接，下载文书并归档到对应案件，
            全程无需人工干预
          </p>
        </motion.div>

        {/* 控制栏 */}
        <FlowControls
          isPlaying={isPlaying}
          currentStep={currentStep}
          totalSteps={totalSteps}
          onPlay={play}
          onReset={reset}
          className="mb-6"
        />

        {/* 流程演示区域 - 响应式布局 */}
        <div
          className={cn(
            'grid gap-8',
            // 超宽屏幕：三列布局
            '2xl:grid-cols-[300px_120px_1fr]',
            // 桌面端：三列布局（手机 | 转发 | 处理流程+结果）
            'lg:grid-cols-[260px_100px_1fr]',
            // 平板端：两列布局
            'md:grid-cols-[260px_1fr]',
            // 移动端：单列垂直布局
            'grid-cols-1',
            'items-center'
          )}
        >
          {/* 左侧：手机模拟器 */}
          <motion.div
            initial={{ opacity: 0, x: -30 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, delay: 0.1 }}
            className="flex justify-center"
          >
            <AnimatePresence>
              {state.phoneVisible && (
                <motion.div
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.9 }}
                  transition={{ type: 'spring', stiffness: 200, damping: 20 }}
                >
                  <PhoneMockup smsVisible={state.smsVisible} />
                </motion.div>
              )}
            </AnimatePresence>

            {/* 手机占位符（未显示时） */}
            {!state.phoneVisible && (
              <div className="flex h-[500px] w-[280px] items-center justify-center rounded-[3rem] border-2 border-dashed border-gray-700">
                <span className="text-gray-500">等待演示开始...</span>
              </div>
            )}
          </motion.div>

          {/* 中间：转发卡片（仅桌面端显示） */}
          <div className="hidden lg:flex lg:justify-center">
            <ForwardCard
              visible={state.forwardVisible}
              arrowActive={state.arrowActive}
            />
          </div>

          {/* 右侧：处理流程 + 结果 */}
          <motion.div
            initial={{ opacity: 0, x: 30 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, delay: 0.2 }}
            className="space-y-4"
          >
            {/* 移动端/平板端：转发指示器 */}
            <div className="flex items-center justify-center gap-4 lg:hidden">
              <AnimatePresence>
                {state.forwardVisible && (
                  <motion.div
                    initial={{ opacity: 0, y: -10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    className="flex items-center gap-2 text-cyan-400"
                  >
                    <Forward className="h-5 w-5" />
                    <span className="text-sm">自动转发到系统</span>
                    <ArrowRight className="h-4 w-4" />
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* 处理节点网格 */}
            <div>
              <h3 className="mb-4 text-sm font-medium text-gray-400">
                处理流程
              </h3>
              <ProcessNodes nodeStatuses={state.nodeStatuses} />
            </div>

            {/* 结果卡片 */}
            <div>
              <h3 className="mb-4 text-sm font-medium text-gray-400">
                处理结果
              </h3>
              <ResultCards visibleCards={state.resultCardsVisible} />
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  )
}
