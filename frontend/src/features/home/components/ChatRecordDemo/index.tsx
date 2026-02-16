/**
 * ChatRecordDemo - 聊天记录取证流程演示组件
 * @module features/home/components/ChatRecordDemo
 *
 * 展示聊天记录取证的完整流程演示
 * Requirements: 5.1, 5.2, 5.3, 5.4
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ArrowRight,
  Upload,
  Sparkles,
  Grid3X3,
  FileDown,
  Play,
  RotateCcw,
  Check,
  X,
  Video,
  Clock,
  HardDrive,
} from 'lucide-react'

import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { CHAT_AI_TASKS } from '../../constants'
import type { AITaskStatus } from '../../types'

// ============================================================================
// 类型定义
// ============================================================================

interface ChatRecordDemoProps {
  className?: string
}

interface StepColumnProps {
  title: string
  icon: React.ReactNode
  isActive: boolean
  children: React.ReactNode
}

// ============================================================================
// 常量
// ============================================================================

const TOTAL_STEPS = 12
const STEP_DURATION = 600

// 模拟截帧数据
const MOCK_FRAMES = [
  { id: 1, isDuplicate: false },
  { id: 2, isDuplicate: false },
  { id: 3, isDuplicate: true },
  { id: 4, isDuplicate: false },
  { id: 5, isDuplicate: true },
  { id: 6, isDuplicate: false },
]

// ============================================================================
// 步骤列组件
// ============================================================================

function StepColumn({ title, icon, isActive, children }: StepColumnProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center gap-4 rounded-xl border p-4',
        'bg-gray-900/50 backdrop-blur-sm transition-all duration-300',
        isActive
          ? 'border-cyan-500/50 shadow-lg shadow-cyan-500/10'
          : 'border-gray-700/50'
      )}
    >
      {/* 步骤图标 */}
      <div
        className={cn(
          'flex h-12 w-12 items-center justify-center rounded-xl',
          'transition-all duration-300',
          isActive
            ? 'bg-gradient-to-br from-cyan-500 to-blue-500 text-white'
            : 'bg-gray-800 text-gray-400'
        )}
      >
        {icon}
      </div>

      {/* 步骤标题 */}
      <h4
        className={cn(
          'text-sm font-medium transition-colors duration-300',
          isActive ? 'text-white' : 'text-gray-500'
        )}
      >
        {title}
      </h4>

      {/* 步骤内容 */}
      <div className="w-full">{children}</div>
    </div>
  )
}

// ============================================================================
// 箭头连接组件
// ============================================================================

interface ArrowConnectorProps {
  isActive: boolean
  isVertical?: boolean
}

function ArrowConnector({ isActive, isVertical = false }: ArrowConnectorProps) {
  return (
    <motion.div
      className={cn(
        'flex items-center justify-center',
        isVertical ? 'rotate-90 py-2' : 'px-2'
      )}
      animate={
        isActive
          ? {
              x: isVertical ? 0 : [0, 4, 0],
              y: isVertical ? [0, 4, 0] : 0,
            }
          : {}
      }
      transition={
        isActive
          ? {
              duration: 1,
              repeat: Infinity,
              ease: 'easeInOut',
            }
          : {}
      }
    >
      <ArrowRight
        className={cn(
          'h-5 w-5 transition-colors duration-300',
          isActive ? 'text-cyan-400' : 'text-gray-600'
        )}
      />
    </motion.div>
  )
}

// ============================================================================
// 上传步骤内容
// ============================================================================

interface UploadStepContentProps {
  progress: number
  isComplete: boolean
}

function UploadStepContent({ progress, isComplete }: UploadStepContentProps) {
  return (
    <div className="space-y-3">
      {/* 上传进度条 */}
      <div className="relative h-2 overflow-hidden rounded-full bg-gray-700">
        <motion.div
          className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-cyan-500 to-blue-500"
          initial={{ width: 0 }}
          animate={{ width: `${progress}%` }}
          transition={{ duration: 0.3 }}
        />
      </div>

      {/* 进度文字 */}
      <div className="text-center text-sm text-gray-400">
        {isComplete ? '上传完成' : `上传中 ${progress}%`}
      </div>

      {/* 视频信息卡片 */}
      <AnimatePresence>
        {isComplete && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="rounded-lg border border-green-500/30 bg-green-500/10 p-3"
          >
            <div className="flex items-center gap-2 text-green-400">
              <Video className="h-5 w-5" />
              <span className="text-sm font-medium">chat_record.mp4</span>
            </div>
            <div className="mt-2 flex items-center gap-4 text-sm text-gray-400">
              <span className="flex items-center gap-1">
                <Clock className="h-4 w-4" />
                03:24
              </span>
              <span className="flex items-center gap-1">
                <HardDrive className="h-4 w-4" />
                128MB
              </span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ============================================================================
// AI 解析步骤内容
// ============================================================================

interface AIParseStepContentProps {
  taskStatuses: Record<string, AITaskStatus>
}

function AIParseStepContent({ taskStatuses }: AIParseStepContentProps) {
  return (
    <div className="space-y-2">
      {CHAT_AI_TASKS.map((task) => {
        const status = taskStatuses[task.id] || 'idle'
        const Icon = task.icon

        return (
          <motion.div
            key={task.id}
            className={cn(
              'flex items-center gap-2 rounded-lg border p-2',
              'transition-all duration-300',
              status === 'idle' && 'border-gray-700/50 bg-gray-800/50',
              status === 'processing' &&
                'border-yellow-500/50 bg-yellow-500/10',
              status === 'completed' && 'border-green-500/50 bg-green-500/10'
            )}
            animate={
              status === 'processing'
                ? {
                    borderColor: [
                      'rgba(234, 179, 8, 0.5)',
                      'rgba(250, 204, 21, 0.5)',
                      'rgba(234, 179, 8, 0.5)',
                    ],
                  }
                : {}
            }
            transition={
              status === 'processing'
                ? {
                    duration: 1,
                    repeat: Infinity,
                  }
                : {}
            }
          >
            <Icon
              className={cn(
                'h-5 w-5',
                status === 'idle' && 'text-gray-500',
                status === 'processing' && 'text-yellow-400',
                status === 'completed' && 'text-green-400'
              )}
            />
            <span
              className={cn(
                'flex-1 text-sm',
                status === 'idle' && 'text-gray-500',
                status === 'processing' && 'text-yellow-400',
                status === 'completed' && 'text-green-400'
              )}
            >
              {task.title}
            </span>
            {status === 'completed' && (
              <Check className="h-4 w-4 text-green-400" />
            )}
          </motion.div>
        )
      })}
    </div>
  )
}

// ============================================================================
// 截帧步骤内容
// ============================================================================

interface FrameStepContentProps {
  visibleFrames: number[]
}

function FrameStepContent({ visibleFrames }: FrameStepContentProps) {
  return (
    <div className="grid grid-cols-3 gap-2">
      {MOCK_FRAMES.map((frame, index) => {
        const isVisible = visibleFrames.includes(index)

        return (
          <AnimatePresence key={frame.id}>
            {isVisible && (
              <motion.div
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.8 }}
                transition={{ type: 'spring', stiffness: 200, damping: 20 }}
                className={cn(
                  'relative aspect-square rounded-lg border',
                  'bg-gradient-to-br from-gray-700 to-gray-800',
                  frame.isDuplicate
                    ? 'border-red-500/50'
                    : 'border-gray-600/50'
                )}
              >
                {/* 帧序号 */}
                <span className="absolute left-1 top-1 text-xs text-gray-400">
                  #{frame.id}
                </span>

                {/* 重复标记 */}
                {frame.isDuplicate && (
                  <div className="absolute inset-0 flex items-center justify-center bg-red-500/20">
                    <X className="h-5 w-5 text-red-400" />
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        )
      })}
    </div>
  )
}

// ============================================================================
// 导出步骤内容
// ============================================================================

interface ExportStepContentProps {
  isVisible: boolean
}

function ExportStepContent({ isVisible }: ExportStepContentProps) {
  return (
    <AnimatePresence>
      {isVisible && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          className="space-y-3"
        >
          {/* PDF 文件卡片 */}
          <div className="rounded-lg border border-blue-500/30 bg-blue-500/10 p-4">
            <div className="flex items-center gap-2 text-blue-400">
              <FileDown className="h-5 w-5" />
              <span className="text-sm font-medium">聊天记录_证据.pdf</span>
            </div>
            <div className="mt-2 text-sm text-gray-400">
              共 4 页 · 已去重 2 帧
            </div>
          </div>

          {/* 完成标记 */}
          <div className="flex items-center justify-center gap-2 text-green-400">
            <Check className="h-5 w-5" />
            <span className="text-sm">导出完成</span>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

// ============================================================================
// 主组件
// ============================================================================

export function ChatRecordDemo({ className }: ChatRecordDemoProps) {
  // 状态
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentStep, setCurrentStep] = useState(0)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [uploadComplete, setUploadComplete] = useState(false)
  const [aiTaskStatuses, setAiTaskStatuses] = useState<
    Record<string, AITaskStatus>
  >(
    CHAT_AI_TASKS.reduce(
      (acc, task) => ({ ...acc, [task.id]: 'idle' as AITaskStatus }),
      {}
    )
  )
  const [visibleFrames, setVisibleFrames] = useState<number[]>([])
  const [exportVisible, setExportVisible] = useState(false)

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // 清除定时器
  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }, [])

  // 重置状态
  const reset = useCallback(() => {
    clearTimer()
    setIsPlaying(false)
    setCurrentStep(0)
    setUploadProgress(0)
    setUploadComplete(false)
    setAiTaskStatuses(
      CHAT_AI_TASKS.reduce(
        (acc, task) => ({ ...acc, [task.id]: 'idle' as AITaskStatus }),
        {}
      )
    )
    setVisibleFrames([])
    setExportVisible(false)
  }, [clearTimer])

  // 播放动画
  const play = useCallback(() => {
    if (isPlaying) return
    reset()
    setIsPlaying(true)
    setCurrentStep(1)
  }, [isPlaying, reset])

  // 动画步骤执行
  useEffect(() => {
    if (!isPlaying || currentStep === 0) return

    const executeStep = () => {
      switch (currentStep) {
        // Steps 1-3: 上传进度
        case 1:
          setUploadProgress(33)
          break
        case 2:
          setUploadProgress(66)
          break
        case 3:
          setUploadProgress(100)
          setUploadComplete(true)
          break

        // Steps 4-7: AI 任务
        case 4:
        case 5:
        case 6:
        case 7: {
          const taskIndex = currentStep - 4
          const taskId = CHAT_AI_TASKS[taskIndex]?.id
          const prevTaskId = taskIndex > 0 ? CHAT_AI_TASKS[taskIndex - 1]?.id : null

          setAiTaskStatuses((prev) => {
            const newStatuses = { ...prev }
            if (prevTaskId) {
              newStatuses[prevTaskId] = 'completed'
            }
            if (taskId) {
              newStatuses[taskId] = 'processing'
            }
            return newStatuses
          })
          break
        }

        // Step 8: 完成最后一个 AI 任务
        case 8: {
          const lastTaskId = CHAT_AI_TASKS[CHAT_AI_TASKS.length - 1]?.id
          setAiTaskStatuses((prev) => ({
            ...prev,
            [lastTaskId]: 'completed',
          }))
          break
        }

        // Steps 9-11: 显示截帧
        case 9:
          setVisibleFrames([0, 1])
          break
        case 10:
          setVisibleFrames([0, 1, 2, 3])
          break
        case 11:
          setVisibleFrames([0, 1, 2, 3, 4, 5])
          break

        // Step 12: 显示导出
        case 12:
          setExportVisible(true)
          break
      }

      // 继续下一步或结束
      if (currentStep < TOTAL_STEPS) {
        timerRef.current = setTimeout(() => {
          setCurrentStep((prev) => prev + 1)
        }, STEP_DURATION)
      } else {
        setIsPlaying(false)
      }
    }

    executeStep()

    return () => {
      clearTimer()
    }
  }, [isPlaying, currentStep, clearTimer])

  // 组件卸载时清理
  useEffect(() => {
    return () => {
      clearTimer()
    }
  }, [clearTimer])

  // 计算各步骤激活状态
  const isUploadActive = currentStep >= 1 && currentStep <= 3
  const isAIActive = currentStep >= 4 && currentStep <= 8
  const isFrameActive = currentStep >= 9 && currentStep <= 11
  const isExportActive = currentStep >= 12

  const isComplete = currentStep >= TOTAL_STEPS && !isPlaying

  return (
    <section
      id="chat-record-flow"
      className={cn('relative overflow-hidden bg-gray-950 py-16 md:py-20', className)}
    >
      {/* 背景装饰 - 与其他区域融合 */}
      <div className="pointer-events-none absolute inset-0">
        {/* 顶部渐变过渡 */}
        <div className="absolute inset-x-0 top-0 h-32 bg-gradient-to-b from-gray-950 to-transparent" />
        <div className="absolute right-1/4 top-1/4 h-64 w-64 rounded-full bg-purple-500/10 blur-3xl" />
        <div className="absolute bottom-1/4 left-1/4 h-64 w-64 rounded-full bg-pink-500/10 blur-3xl" />
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
            聊天记录
            <span className="bg-gradient-to-r from-purple-400 to-pink-500 bg-clip-text text-transparent">
              智能取证
            </span>
          </h2>
          <p className="mx-auto max-w-2xl text-base text-gray-400 md:text-lg">
            上传微信聊天录屏，AI 自动解析、智能截帧、去重过滤，一键导出 PDF 证据材料
          </p>
        </motion.div>

        {/* 控制栏 */}
        <div className="mb-6 flex flex-col items-center gap-3 sm:flex-row sm:justify-center">
          <Button
            onClick={play}
            disabled={isPlaying}
            size="sm"
            className={cn(
              'relative overflow-hidden',
              'bg-gradient-to-r from-purple-500 to-pink-500',
              'hover:from-purple-400 hover:to-pink-400',
              'disabled:from-gray-600 disabled:to-gray-700 disabled:opacity-50',
              'shadow-lg shadow-purple-500/25'
            )}
          >
            <span className="relative flex items-center gap-2">
              <Play className="h-4 w-4" />
              {isPlaying ? '播放中...' : isComplete ? '重新播放' : '播放演示'}
            </span>
          </Button>

          <Button
            onClick={reset}
            variant="outline"
            size="sm"
            disabled={currentStep === 0 && !isPlaying}
            className="border-gray-700 bg-gray-800/50 text-gray-300 hover:border-gray-600 hover:bg-gray-700/50"
          >
            <RotateCcw className="mr-2 h-4 w-4" />
            重置
          </Button>

          {/* 进度指示 */}
          <span className="text-base text-gray-400">
            {currentStep > 0 ? `步骤 ${currentStep}/${TOTAL_STEPS}` : '准备就绪'}
          </span>
        </div>

        {/* 流程演示区域 - 响应式布局 */}
        <div
          className={cn(
            'grid gap-6',
            // 超宽屏幕：四列布局
            '2xl:grid-cols-[1fr_auto_1fr_auto_1fr_auto_1fr]',
            // 桌面端：四列布局
            'md:grid-cols-[1fr_auto_1fr_auto_1fr_auto_1fr]',
            // 移动端：单列垂直布局
            'grid-cols-1',
            'items-start'
          )}
        >
          {/* 上传步骤 */}
          <StepColumn
            title="上传录屏"
            icon={<Upload className="h-6 w-6" />}
            isActive={isUploadActive || uploadComplete}
          >
            <UploadStepContent
              progress={uploadProgress}
              isComplete={uploadComplete}
            />
          </StepColumn>

          {/* 箭头 1 */}
          <div className="hidden items-center md:flex">
            <ArrowConnector isActive={uploadComplete} />
          </div>
          <div className="flex justify-center md:hidden">
            <ArrowConnector isActive={uploadComplete} isVertical />
          </div>

          {/* AI 解析步骤 */}
          <StepColumn
            title="AI 解析"
            icon={<Sparkles className="h-6 w-6" />}
            isActive={isAIActive}
          >
            <AIParseStepContent taskStatuses={aiTaskStatuses} />
          </StepColumn>

          {/* 箭头 2 */}
          <div className="hidden items-center md:flex">
            <ArrowConnector
              isActive={
                Object.values(aiTaskStatuses).every((s) => s === 'completed')
              }
            />
          </div>
          <div className="flex justify-center md:hidden">
            <ArrowConnector
              isActive={
                Object.values(aiTaskStatuses).every((s) => s === 'completed')
              }
              isVertical
            />
          </div>

          {/* 截帧步骤 */}
          <StepColumn
            title="智能截帧"
            icon={<Grid3X3 className="h-6 w-6" />}
            isActive={isFrameActive}
          >
            <FrameStepContent visibleFrames={visibleFrames} />
          </StepColumn>

          {/* 箭头 3 */}
          <div className="hidden items-center md:flex">
            <ArrowConnector isActive={visibleFrames.length === 6} />
          </div>
          <div className="flex justify-center md:hidden">
            <ArrowConnector isActive={visibleFrames.length === 6} isVertical />
          </div>

          {/* 导出步骤 */}
          <StepColumn
            title="导出 PDF"
            icon={<FileDown className="h-6 w-6" />}
            isActive={isExportActive}
          >
            <ExportStepContent isVisible={exportVisible} />
          </StepColumn>
        </div>
      </div>
    </section>
  )
}
