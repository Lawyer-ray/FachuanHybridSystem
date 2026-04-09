/**
 * 教程页面
 * 展示系统使用教程，包含立案流程动画演示
 */

import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  User,
  FileText,
  Briefcase,
  Upload,
  ScanLine,
  CheckCircle2,
  ArrowRight,
  Play,
  RotateCcw,
  Sparkles,
  ChevronRight,
} from 'lucide-react'
import { lazy, Suspense } from 'react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { Navigation } from '@/features/home/components/Navigation'

// 懒加载 Footer
const Footer = lazy(() =>
  import('@/features/home/components/Footer').then((m) => ({ default: m.Footer }))
)

// 动画配置
const springConfig = {
  type: 'spring' as const,
  stiffness: 100,
  damping: 15,
}

// 立案流程步骤数据
const CASE_FILING_STEPS = [
  {
    id: 'client',
    title: '创建当事人',
    description: '上传身份证件，系统自动 OCR 识别信息',
    icon: User,
    color: 'purple',
    details: [
      { icon: Upload, text: '上传身份证正反面' },
      { icon: ScanLine, text: 'AI 自动识别姓名、身份证号' },
      { icon: CheckCircle2, text: '自动填充当事人信息' },
    ],
  },
  {
    id: 'contract',
    title: '创建合同',
    description: '录入委托合同信息，关联当事人',
    icon: FileText,
    color: 'cyan',
    details: [
      { icon: FileText, text: '选择合同类型' },
      { icon: User, text: '关联已创建的当事人' },
      { icon: CheckCircle2, text: '设置收费方式和金额' },
    ],
  },
  {
    id: 'case',
    title: '创建案件',
    description: '填写案件信息，关联合同和当事人',
    icon: Briefcase,
    color: 'pink',
    details: [
      { icon: Briefcase, text: '选择案由和管辖法院' },
      { icon: FileText, text: '关联委托合同' },
      { icon: CheckCircle2, text: '案件创建完成，开始管理' },
    ],
  },
]

/**
 * 加载骨架组件
 */
function SectionSkeleton() {
  return (
    <div className="flex min-h-[200px] items-center justify-center bg-gray-950">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-cyan-500 border-t-transparent" />
    </div>
  )
}

/**
 * 流程步骤卡片
 */
function StepCard({
  step,
  index,
  isActive,
  isCompleted,
  onClick,
}: {
  step: (typeof CASE_FILING_STEPS)[0]
  index: number
  isActive: boolean
  isCompleted: boolean
  onClick: () => void
}) {
  const Icon = step.icon

  const colorClasses = {
    purple: {
      bg: 'bg-purple-500/10',
      border: 'border-purple-500/30',
      activeBorder: 'border-purple-500',
      text: 'text-purple-400',
      glow: 'shadow-purple-500/20',
    },
    cyan: {
      bg: 'bg-cyan-500/10',
      border: 'border-cyan-500/30',
      activeBorder: 'border-cyan-500',
      text: 'text-cyan-400',
      glow: 'shadow-cyan-500/20',
    },
    pink: {
      bg: 'bg-pink-500/10',
      border: 'border-pink-500/30',
      activeBorder: 'border-pink-500',
      text: 'text-pink-400',
      glow: 'shadow-pink-500/20',
    },
  }

  const colors = colorClasses[step.color as keyof typeof colorClasses]

  return (
    <motion.button
      onClick={onClick}
      className={cn(
        'relative flex flex-col items-center gap-4 rounded-2xl border p-6 text-center',
        'transition-all duration-300',
        'hover:bg-white/5',
        isActive
          ? `${colors.activeBorder} ${colors.glow} shadow-lg bg-white/5`
          : isCompleted
            ? `${colors.border} bg-white/[0.02]`
            : 'border-gray-800 bg-gray-900/50'
      )}
      whileHover={{ y: -4 }}
      whileTap={{ scale: 0.98 }}
    >
      {/* 步骤编号 */}
      <div
        className={cn(
          'absolute -top-3 left-1/2 -translate-x-1/2',
          'flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold',
          isActive || isCompleted
            ? `${colors.bg} ${colors.text}`
            : 'bg-gray-800 text-gray-500'
        )}
      >
        {isCompleted ? <CheckCircle2 className="h-4 w-4" /> : index + 1}
      </div>

      {/* 图标 */}
      <motion.div
        className={cn(
          'flex h-16 w-16 items-center justify-center rounded-2xl',
          isActive || isCompleted ? colors.bg : 'bg-gray-800/50'
        )}
        animate={isActive ? { scale: [1, 1.1, 1] } : {}}
        transition={{ duration: 2, repeat: Infinity }}
      >
        <Icon
          className={cn(
            'h-8 w-8',
            isActive || isCompleted ? colors.text : 'text-gray-500'
          )}
        />
      </motion.div>

      {/* 标题 */}
      <h3
        className={cn(
          'text-lg font-semibold',
          isActive || isCompleted ? 'text-white' : 'text-gray-400'
        )}
      >
        {step.title}
      </h3>

      {/* 描述 */}
      <p className="text-sm text-gray-500">{step.description}</p>
    </motion.button>
  )
}

/**
 * 步骤详情面板
 */
function StepDetailPanel({
  step,
  isVisible,
}: {
  step: (typeof CASE_FILING_STEPS)[0]
  isVisible: boolean
}) {
  const colorClasses = {
    purple: 'from-purple-500 to-pink-500',
    cyan: 'from-cyan-500 to-blue-500',
    pink: 'from-pink-500 to-rose-500',
  }

  const gradient = colorClasses[step.color as keyof typeof colorClasses]

  return (
    <AnimatePresence mode="wait">
      {isVisible && (
        <motion.div
          key={step.id}
          initial={{ opacity: 0, y: 20, scale: 0.95 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -20, scale: 0.95 }}
          transition={springConfig}
          className="rounded-2xl border border-gray-800 bg-gray-900/50 p-8"
        >
          {/* 标题 */}
          <div className="mb-6 flex items-center gap-4">
            <div
              className={cn(
                'flex h-12 w-12 items-center justify-center rounded-xl',
                `bg-gradient-to-br ${gradient}`
              )}
            >
              <step.icon className="h-6 w-6 text-white" />
            </div>
            <div>
              <h3 className="text-xl font-bold text-white">{step.title}</h3>
              <p className="text-gray-400">{step.description}</p>
            </div>
          </div>

          {/* 详细步骤 */}
          <div className="space-y-4">
            {step.details.map((detail, index) => (
              <motion.div
                key={index}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.15 }}
                className="flex items-center gap-4 rounded-xl bg-gray-800/50 p-4"
              >
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gray-700/50">
                  <detail.icon className="h-5 w-5 text-gray-300" />
                </div>
                <span className="text-gray-300">{detail.text}</span>
                {index < step.details.length - 1 && (
                  <ChevronRight className="ml-auto h-5 w-5 text-gray-600" />
                )}
              </motion.div>
            ))}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

/**
 * 连接线组件
 */
function ConnectionLine({ isActive }: { isActive: boolean }) {
  return (
    <div className="hidden md:flex items-center justify-center px-2">
      <motion.div
        className={cn(
          'h-1 w-12 rounded-full',
          isActive ? 'bg-gradient-to-r from-cyan-500 to-purple-500' : 'bg-gray-700'
        )}
        animate={isActive ? { scaleX: [0.8, 1, 0.8] } : {}}
        transition={{ duration: 1.5, repeat: Infinity }}
      />
      <ArrowRight
        className={cn(
          'h-5 w-5 -ml-1',
          isActive ? 'text-purple-400' : 'text-gray-600'
        )}
      />
    </div>
  )
}

/**
 * 立案流程动画演示组件
 */
function CaseFilingDemo() {
  const [currentStep, setCurrentStep] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [completedSteps, setCompletedSteps] = useState<number[]>([])

  // 自动播放逻辑
  useEffect(() => {
    if (!isPlaying) return

    const timer = setInterval(() => {
      setCurrentStep((prev) => {
        const next = prev + 1
        if (next >= CASE_FILING_STEPS.length) {
          setIsPlaying(false)
          setCompletedSteps([0, 1, 2])
          return prev
        }
        setCompletedSteps((completed) => [...completed, prev])
        return next
      })
    }, 3000)

    return () => clearInterval(timer)
  }, [isPlaying])

  const handlePlay = () => {
    setCurrentStep(0)
    setCompletedSteps([])
    setIsPlaying(true)
  }

  const handleReset = () => {
    setCurrentStep(0)
    setCompletedSteps([])
    setIsPlaying(false)
  }

  const handleStepClick = (index: number) => {
    if (!isPlaying) {
      setCurrentStep(index)
    }
  }

  return (
    <div className="space-y-8">
      {/* 控制栏 */}
      <div className="flex items-center justify-center gap-4">
        <Button
          onClick={handlePlay}
          disabled={isPlaying}
          className={cn(
            'gap-2',
            'bg-gradient-to-r from-cyan-500 to-purple-500 text-white',
            'hover:opacity-90'
          )}
        >
          <Play className="h-4 w-4" />
          {isPlaying ? '演示中...' : '开始演示'}
        </Button>
        <Button
          onClick={handleReset}
          variant="outline"
          className="gap-2 border-gray-700 text-gray-300 hover:bg-gray-800"
        >
          <RotateCcw className="h-4 w-4" />
          重置
        </Button>
      </div>

      {/* 进度指示器 */}
      <div className="flex items-center justify-center gap-2">
        {CASE_FILING_STEPS.map((_, index) => (
          <motion.div
            key={index}
            className={cn(
              'h-2 rounded-full transition-all duration-300',
              index === currentStep
                ? 'w-8 bg-gradient-to-r from-cyan-500 to-purple-500'
                : completedSteps.includes(index)
                  ? 'w-4 bg-green-500'
                  : 'w-4 bg-gray-700'
            )}
          />
        ))}
      </div>

      {/* 步骤卡片 */}
      <div className="grid gap-4 md:grid-cols-[1fr_auto_1fr_auto_1fr]">
        {CASE_FILING_STEPS.map((step, index) => (
          <motion.div
            key={step.id}
            className="contents"
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: index * 0.1 }}
          >
            <StepCard
              step={step}
              index={index}
              isActive={currentStep === index}
              isCompleted={completedSteps.includes(index)}
              onClick={() => handleStepClick(index)}
            />
            {index < CASE_FILING_STEPS.length - 1 && (
              <ConnectionLine
                isActive={
                  currentStep > index || completedSteps.includes(index)
                }
              />
            )}
          </motion.div>
        ))}
      </div>

      {/* 步骤详情 */}
      <StepDetailPanel
        step={CASE_FILING_STEPS[currentStep]}
        isVisible={true}
      />
    </div>
  )
}

export function TutorialPage() {
  return (
    <div className="min-h-screen bg-gray-950">
      {/* 导航栏 */}
      <Navigation />

      {/* Hero 区域 */}
      <section className="relative overflow-hidden pt-32 pb-16 md:pt-40 md:pb-20">
        {/* 背景装饰 */}
        <div className="pointer-events-none absolute inset-0">
          <div className="absolute left-1/4 top-1/4 h-[500px] w-[500px] rounded-full bg-purple-600/10 blur-[120px]" />
          <div className="absolute right-1/4 bottom-1/4 h-[400px] w-[400px] rounded-full bg-cyan-500/10 blur-[100px]" />
        </div>

        <div className="relative mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 2xl:max-w-[1600px]">
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={springConfig}
            className="text-center"
          >
            {/* 徽章 */}
            <motion.div
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ ...springConfig, delay: 0.1 }}
              className="mb-6 inline-flex items-center gap-2 rounded-full border border-purple-500/30 bg-purple-500/10 px-4 py-1.5 text-sm font-medium text-purple-300"
            >
              <Sparkles className="h-4 w-4" />
              <span>快速上手</span>
            </motion.div>

            {/* 标题 */}
            <h1 className="mb-6 text-4xl font-bold tracking-tight text-white sm:text-5xl md:text-6xl">
              使用
              <span className="bg-gradient-to-r from-purple-400 via-pink-400 to-cyan-400 bg-clip-text text-transparent">
                教程
              </span>
            </h1>

            {/* 描述 */}
            <p className="mx-auto max-w-2xl text-lg text-gray-400 md:text-xl">
              通过交互式演示，快速了解法穿AI的核心功能
              <br className="hidden sm:block" />
              从创建当事人到案件管理，一步步带你入门
            </p>
          </motion.div>
        </div>
      </section>

      {/* 立案流程演示区域 */}
      <section className="relative py-16 md:py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 2xl:max-w-[1600px]">
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={springConfig}
            className="mb-12 text-center"
          >
            <h2 className="mb-4 text-3xl font-bold text-white md:text-4xl">
              如何
              <span className="bg-gradient-to-r from-cyan-400 to-purple-500 bg-clip-text text-transparent">
                立案
              </span>
            </h2>
            <p className="text-gray-400">
              三步完成案件创建：当事人 → 合同 → 案件
            </p>
          </motion.div>

          <CaseFilingDemo />
        </div>
      </section>

      {/* Footer */}
      <Suspense fallback={<SectionSkeleton />}>
        <Footer />
      </Suspense>
    </div>
  )
}
