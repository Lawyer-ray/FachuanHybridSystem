/**
 * FlowControls - 流程演示控制组件
 * @module features/home/components/SMSFlowDemo/FlowControls
 *
 * 实现播放/重置按钮和流程步骤指示器
 * Requirements: 4.3, 4.7, 4.8
 */

import { motion } from 'framer-motion'
import { Play, RotateCcw, Pause } from 'lucide-react'

import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'

// ============================================================================
// 类型定义
// ============================================================================

interface FlowControlsProps {
  /** 是否正在播放 */
  isPlaying: boolean
  /** 当前步骤（1-based） */
  currentStep: number
  /** 总步骤数 */
  totalSteps: number
  /** 播放按钮点击回调 */
  onPlay: () => void
  /** 重置按钮点击回调 */
  onReset: () => void
  /** 自定义类名 */
  className?: string
}

// ============================================================================
// 步骤指示器组件
// ============================================================================

interface StepIndicatorProps {
  currentStep: number
  totalSteps: number
}

/**
 * 步骤指示器 - 显示当前进度
 */
function StepIndicator({ currentStep, totalSteps }: StepIndicatorProps) {
  const progress = currentStep > 0 ? (currentStep / totalSteps) * 100 : 0

  return (
    <div className="flex items-center gap-2">
      {/* 步骤文字 */}
      <span className="text-sm font-medium text-gray-400">
        {currentStep > 0 ? (
          <>
            步骤{' '}
            <span className="text-white">
              {currentStep}/{totalSteps}
            </span>
          </>
        ) : (
          '准备就绪'
        )}
      </span>

      {/* 进度条 */}
      <div className="relative h-1 w-20 overflow-hidden rounded-full bg-gray-700/50">
        <motion.div
          className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-cyan-500 to-blue-500"
          initial={{ width: 0 }}
          animate={{ width: `${progress}%` }}
          transition={{
            type: 'spring',
            stiffness: 100,
            damping: 20,
          }}
        />
      </div>

      {/* 进度点指示器 */}
      <div className="hidden items-center gap-0.5 sm:flex">
        {Array.from({ length: Math.min(totalSteps, 13) }).map((_, index) => {
          const stepNum = index + 1
          const isActive = stepNum <= currentStep
          const isCurrent = stepNum === currentStep

          return (
            <motion.div
              key={index}
              className={cn(
                'h-1 w-1 rounded-full transition-colors duration-200',
                isActive ? 'bg-cyan-500' : 'bg-gray-600',
                isCurrent && 'ring-1 ring-cyan-500/50'
              )}
              animate={
                isCurrent
                  ? {
                      scale: [1, 1.3, 1],
                    }
                  : {}
              }
              transition={
                isCurrent
                  ? {
                      duration: 0.8,
                      repeat: Infinity,
                      ease: 'easeInOut',
                    }
                  : {}
              }
            />
          )
        })}
      </div>
    </div>
  )
}

// ============================================================================
// 主组件
// ============================================================================

/**
 * 流程控制组件
 *
 * 提供播放/重置按钮和步骤进度指示器
 *
 * @example
 * ```tsx
 * <FlowControls
 *   isPlaying={isPlaying}
 *   currentStep={currentStep}
 *   totalSteps={totalSteps}
 *   onPlay={play}
 *   onReset={reset}
 * />
 * ```
 */
export function FlowControls({
  isPlaying,
  currentStep,
  totalSteps,
  onPlay,
  onReset,
  className,
}: FlowControlsProps) {
  const isComplete = currentStep >= totalSteps && !isPlaying

  return (
    <div
      className={cn(
        'flex flex-col items-center gap-3 sm:flex-row sm:justify-between',
        className
      )}
    >
      {/* 控制按钮组 */}
      <div className="flex items-center gap-2">
        {/* 播放/暂停按钮 */}
        <Button
          onClick={onPlay}
          disabled={isPlaying}
          size="sm"
          className={cn(
            'relative overflow-hidden',
            'bg-gradient-to-r from-cyan-500 to-blue-500',
            'hover:from-cyan-400 hover:to-blue-400',
            'disabled:from-gray-600 disabled:to-gray-700 disabled:opacity-50',
            'shadow-lg shadow-cyan-500/25',
            'transition-all duration-300'
          )}
        >
          {/* 按钮发光效果 */}
          {!isPlaying && !isComplete && (
            <motion.div
              className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent"
              animate={{
                x: ['-100%', '100%'],
              }}
              transition={{
                duration: 2,
                repeat: Infinity,
                ease: 'linear',
              }}
            />
          )}

          <span className="relative flex items-center gap-2">
            {isPlaying ? (
              <>
                <Pause className="h-4 w-4" />
                播放中...
              </>
            ) : isComplete ? (
              <>
                <Play className="h-4 w-4" />
                重新播放
              </>
            ) : (
              <>
                <Play className="h-4 w-4" />
                播放演示
              </>
            )}
          </span>
        </Button>

        {/* 重置按钮 */}
        <Button
          onClick={onReset}
          variant="outline"
          size="sm"
          disabled={currentStep === 0 && !isPlaying}
          className={cn(
            'border-gray-700 bg-gray-800/50 text-gray-300',
            'hover:border-gray-600 hover:bg-gray-700/50 hover:text-white',
            'disabled:opacity-50',
            'transition-all duration-300'
          )}
        >
          <RotateCcw className="mr-2 h-4 w-4" />
          重置
        </Button>
      </div>

      {/* 步骤指示器 */}
      <StepIndicator currentStep={currentStep} totalSteps={totalSteps} />
    </div>
  )
}
