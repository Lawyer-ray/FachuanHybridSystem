/**
 * 首页模块类型定义
 * @module features/home/types
 */

import type { LucideIcon } from 'lucide-react'

// ============================================================================
// 导航栏类型
// ============================================================================

export interface NavigationProps {
  className?: string
}

export interface NavLink {
  href: string
  label: string
}

// ============================================================================
// Hero 区域类型
// ============================================================================

export interface HeroSectionProps {
  className?: string
}

export interface StatItem {
  value: number
  suffix?: string
  label: string
}

export interface FloatingCardData {
  icon: LucideIcon
  title: string
  description: string
  position: 'left' | 'right' | 'bottom'
  colorScheme: 'purple' | 'cyan' | 'pink'
}

// ============================================================================
// Bento Grid 类型
// ============================================================================

export type BentoCardSize = 'default' | 'large' | 'wide' | 'tall'
export type BentoCardColorScheme = 'style-1' | 'style-2' | 'style-3'

export interface BentoCardProps {
  icon: LucideIcon
  title: string
  description: string
  size?: BentoCardSize
  colorScheme?: BentoCardColorScheme
  children?: React.ReactNode
}

export interface BentoCardData {
  icon: LucideIcon
  title: string
  description: string
  size: BentoCardSize
  colorScheme: BentoCardColorScheme
  hasVisual?: boolean
}

// ============================================================================
// 短信流程演示类型
// ============================================================================

export interface ProcessNodeData {
  id: string
  icon: LucideIcon
  title: string
  colorScheme: string
}

export type NodeStatus = 'idle' | 'processing' | 'completed'

export interface SMSFlowState {
  currentStep: number
  phoneVisible: boolean
  smsVisible: boolean
  forwardVisible: boolean
  arrowActive: boolean
  nodeStatuses: Record<string, NodeStatus>
  resultCardsVisible: boolean[]
  isPlaying: boolean
}

// ============================================================================
// 聊天记录演示类型
// ============================================================================

export type AITaskStatus = 'idle' | 'processing' | 'completed'

export interface ChatFlowState {
  currentStep: number
  uploadProgress: number
  uploadComplete: boolean
  aiTaskStatuses: Record<string, AITaskStatus>
  visibleFrames: number[]
  exportVisible: boolean
  isPlaying: boolean
}

// ============================================================================
// 技术栈类型
// ============================================================================

export interface TechItem {
  name: string
  description: string
  icon: string // emoji or icon name
}

export interface TechCategory {
  title: string
  icon: string
  items: TechItem[]
}

// ============================================================================
// CTA 区域类型
// ============================================================================

export interface QRCodeData {
  src: string
  alt: string
  title: string
}

// ============================================================================
// 通用动画类型
// ============================================================================

export interface AnimationConfig {
  initial?: Record<string, unknown>
  animate?: Record<string, unknown>
  transition?: Record<string, unknown>
}
