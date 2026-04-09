/**
 * PhoneMockup - 手机模拟器组件
 * @module features/home/components/SMSFlowDemo/PhoneMockup
 *
 * 实现 iPhone 风格的手机外壳、刘海、状态栏和短信通知卡片
 * Requirements: 4.1
 */

import { motion, AnimatePresence } from 'framer-motion'
import { Battery, MessageSquare, Signal, Wifi } from 'lucide-react'

import { cn } from '@/lib/utils'

interface PhoneMockupProps {
  /** 控制短信通知是否可见（用于动画） */
  smsVisible?: boolean
  /** 自定义类名 */
  className?: string
}

/**
 * 获取当前时间字符串（HH:MM 格式）
 */
function getCurrentTime(): string {
  const now = new Date()
  return `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`
}

/**
 * 状态栏组件 - 显示时间、信号、WiFi、电池
 */
function StatusBar() {
  return (
    <div className="flex items-center justify-between px-6 py-2 text-white">
      {/* 左侧：时间 */}
      <span className="text-sm font-semibold">{getCurrentTime()}</span>

      {/* 右侧：状态图标 */}
      <div className="flex items-center gap-1.5">
        <Signal className="h-4 w-4" />
        <Wifi className="h-4 w-4" />
        <div className="flex items-center gap-0.5">
          <Battery className="h-4 w-4" />
          <span className="text-xs">100%</span>
        </div>
      </div>
    </div>
  )
}

/**
 * 动态岛/刘海组件
 */
function DynamicIsland() {
  return (
    <div className="absolute left-1/2 top-3 -translate-x-1/2">
      <div className="h-7 w-28 rounded-full bg-black" />
    </div>
  )
}

/**
 * 短信通知卡片组件
 */
function SMSNotificationCard() {
  return (
    <motion.div
      initial={{ opacity: 0, y: -20, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -10, scale: 0.95 }}
      transition={{
        type: 'spring',
        stiffness: 300,
        damping: 25,
      }}
      className="mx-4 mt-4"
    >
      <div
        className={cn(
          'rounded-2xl border border-white/20 bg-white/10 p-4 backdrop-blur-xl',
          'shadow-lg shadow-black/20'
        )}
      >
        {/* 通知头部 */}
        <div className="mb-2 flex items-center gap-3">
          {/* 短信图标 */}
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-green-500">
            <MessageSquare className="h-5 w-5 text-white" />
          </div>

          {/* 发送者和时间 */}
          <div className="flex-1">
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold text-white">12368</span>
              <span className="text-xs text-white/50">刚刚</span>
            </div>
            <span className="text-xs text-white/60">法院短信</span>
          </div>
        </div>

        {/* 短信内容预览 */}
        <p className="text-sm leading-relaxed text-white/80">
          【广州市天河区人民法院】您有一份新的法律文书，请点击链接查看：
          <span className="text-cyan-400">https://ssfw.gzgy...</span>
        </p>
      </div>
    </motion.div>
  )
}

/**
 * 手机模拟器主组件
 */
export function PhoneMockup({ smsVisible = true, className }: PhoneMockupProps) {
  return (
    <div className={cn('relative', className)}>
      {/* 手机外壳 */}
      <div
        className={cn(
          'relative mx-auto w-[280px] overflow-hidden rounded-[3rem] border-4 border-gray-800',
          'bg-gradient-to-b from-gray-900 to-gray-950',
          'shadow-2xl shadow-black/50'
        )}
      >
        {/* 外壳高光效果 */}
        <div className="pointer-events-none absolute inset-0 rounded-[2.75rem] border border-white/10" />

        {/* 手机屏幕 */}
        <div className="relative min-h-[500px] overflow-hidden rounded-[2.5rem] bg-gradient-to-b from-gray-800 to-gray-900">
          {/* 动态岛 */}
          <DynamicIsland />

          {/* 状态栏 */}
          <div className="pt-10">
            <StatusBar />
          </div>

          {/* 短信通知 */}
          <AnimatePresence>
            {smsVisible && <SMSNotificationCard />}
          </AnimatePresence>

          {/* 屏幕底部装饰 - 模拟锁屏界面 */}
          <div className="absolute bottom-0 left-0 right-0 p-6">
            {/* 底部横条（Home Indicator） */}
            <div className="mx-auto h-1 w-32 rounded-full bg-white/30" />
          </div>
        </div>
      </div>

      {/* 手机侧边按钮装饰 */}
      {/* 左侧：静音开关 + 音量键 */}
      <div className="absolute -left-1 top-24 h-6 w-1 rounded-l-sm bg-gray-700" />
      <div className="absolute -left-1 top-36 h-12 w-1 rounded-l-sm bg-gray-700" />
      <div className="absolute -left-1 top-52 h-12 w-1 rounded-l-sm bg-gray-700" />

      {/* 右侧：电源键 */}
      <div className="absolute -right-1 top-40 h-16 w-1 rounded-r-sm bg-gray-700" />
    </div>
  )
}
