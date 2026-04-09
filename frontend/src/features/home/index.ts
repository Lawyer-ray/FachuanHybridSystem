/**
 * 首页模块导出
 * @module features/home
 */

// ============================================================================
// 类型导出
// ============================================================================

export type {
  // 导航栏
  NavigationProps,
  NavLink,
  // Hero 区域
  HeroSectionProps,
  StatItem,
  FloatingCardData,
  // Bento Grid
  BentoCardSize,
  BentoCardColorScheme,
  BentoCardProps,
  BentoCardData,
  // 短信流程演示
  ProcessNodeData,
  NodeStatus,
  SMSFlowState,
  // 聊天记录演示
  AITaskStatus,
  ChatFlowState,
  // 技术栈
  TechItem,
  TechCategory,
  // CTA 区域
  QRCodeData,
  // 通用
  AnimationConfig,
} from './types'

// ============================================================================
// 常量导出
// ============================================================================

export {
  // 动画配置
  springConfig,
  fadeInUp,
  staggerContainer,
  floatAnimation,
  orbAnimation,
  pulseAnimation,
  gradientAnimation,
  // 导航
  NAV_LINKS,
  // Hero 数据
  STATS_DATA,
  FLOATING_CARDS,
  // Bento Grid 数据
  FEATURES_DATA,
  // 短信流程数据
  SMS_PROCESS_NODES,
  SMS_RESULT_CARDS,
  // 聊天记录数据
  CHAT_AI_TASKS,
  // 技术栈数据
  TECH_STACK,
  ARCH_HIGHLIGHTS,
  // CTA 数据
  QR_CODES,
  // 配置
  BREAKPOINTS,
  SCROLL_THRESHOLD,
} from './constants'

// ============================================================================
// 组件导出
// ============================================================================

export { Navigation } from './components/Navigation'
export { HeroSection } from './components/HeroSection'
export { FeaturesSection, BentoCard, BentoGrid, CaseListMockUI } from './components/FeaturesSection'
export { SMSFlowDemo } from './components/SMSFlowDemo'
export { ChatRecordDemo } from './components/ChatRecordDemo'
export { TechStackSection } from './components/TechStackSection'
export { CTASection } from './components/CTASection'
export { Footer } from './components/Footer'

// ============================================================================
// Hooks 导出
// ============================================================================

export { useScrollPosition } from './hooks/use-scroll-position'
export { useCounterAnimation } from './hooks/use-counter-animation'
export { useFlowAnimation } from './hooks/use-flow-animation'
export { useReducedMotion } from './hooks/use-reduced-motion'
