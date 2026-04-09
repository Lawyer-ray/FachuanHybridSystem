/**
 * 首页入口组件
 * 组装所有首页区域组件
 *
 * Requirements: 11.1, 11.2, 9.6
 */

import { lazy, Suspense } from 'react'
import { Navigation } from '@/features/home/components/Navigation'
import { HeroSection } from '@/features/home/components/HeroSection'
import { FeaturesSection } from '@/features/home/components/FeaturesSection'
import { CaseFlowDemo } from '@/features/home/components/CaseFlowDemo'
import { SMSFlowDemo } from '@/features/home/components/SMSFlowDemo'
import { ChatRecordDemo } from '@/features/home/components/ChatRecordDemo'

// 懒加载非首屏组件
const TechStackSection = lazy(
  () => import('@/features/home/components/TechStackSection').then((m) => ({ default: m.TechStackSection }))
)
const CTASection = lazy(
  () => import('@/features/home/components/CTASection').then((m) => ({ default: m.CTASection }))
)
const Footer = lazy(
  () => import('@/features/home/components/Footer').then((m) => ({ default: m.Footer }))
)

/**
 * 加载骨架组件
 */
function SectionSkeleton() {
  return (
    <div className="flex min-h-[300px] items-center justify-center bg-gray-950">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-cyan-500 border-t-transparent" />
    </div>
  )
}

export function HomePage() {
  return (
    <div className="min-h-screen bg-gray-950">
      {/* 导航栏 - 固定顶部 */}
      <Navigation />

      {/* Hero 区域 - 首屏视觉 */}
      <HeroSection />

      {/* 功能特性 - Bento Grid */}
      <FeaturesSection />

      {/* 案件全流程管理与智能文书生成演示 */}
      <CaseFlowDemo />

      {/* 短信处理流程演示 */}
      <SMSFlowDemo />

      {/* 聊天记录取证流程演示 */}
      <ChatRecordDemo />

      {/* 懒加载的非首屏组件 */}
      <Suspense fallback={<SectionSkeleton />}>
        <TechStackSection />
      </Suspense>

      <Suspense fallback={<SectionSkeleton />}>
        <CTASection />
      </Suspense>

      <Suspense fallback={<SectionSkeleton />}>
        <Footer />
      </Suspense>
    </div>
  )
}
