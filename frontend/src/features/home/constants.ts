/**
 * 首页模块常量定义
 * @module features/home/constants
 */

import {
  Archive,
  BarChart3,
  Bell,
  Bot,
  Download,
  FileText,
  FolderOpen,
  Link,
  MessageSquare,
  Pencil,
  Shield,
  Sparkles,
  Users,
  Zap,
  Activity,
} from 'lucide-react'

import type {
  BentoCardData,
  FloatingCardData,
  NavLink,
  ProcessNodeData,
  StatItem,
  TechCategory,
} from './types'

// ============================================================================
// Framer Motion 动画配置
// ============================================================================

export const springConfig = {
  type: 'spring' as const,
  stiffness: 100,
  damping: 15,
}

export const fadeInUp = {
  initial: { opacity: 0, y: 40 },
  animate: { opacity: 1, y: 0 },
  transition: springConfig,
}

export const staggerContainer = {
  animate: {
    transition: {
      staggerChildren: 0.1,
    },
  },
}

export const floatAnimation = {
  animate: {
    y: [0, -20, 0],
    rotate: [0, 2, 0],
  },
  transition: {
    duration: 6,
    repeat: Infinity,
    ease: 'easeInOut' as const,
  },
}

export const orbAnimation = (delay: number) => ({
  animate: {
    x: [0, 50, 20, -30, 0],
    y: [0, 30, -40, 20, 0],
  },
  transition: {
    duration: 20 + delay * 5,
    repeat: Infinity,
    ease: 'easeInOut' as const,
  },
})

export const pulseAnimation = {
  animate: {
    scale: [1, 1.2, 1],
    opacity: [1, 0.5, 1],
  },
  transition: {
    duration: 2,
    repeat: Infinity,
  },
}

export const gradientAnimation = {
  animate: {
    backgroundPosition: ['0% 50%', '100% 50%', '0% 50%'],
  },
  transition: {
    duration: 6,
    repeat: Infinity,
    ease: 'linear' as const,
  },
}

// ============================================================================
// 导航链接
// ============================================================================

export const NAV_LINKS: NavLink[] = [
  { href: '/tutorial', label: '教程' },
  { href: '/pricing', label: '价格' },
]

// ============================================================================
// Hero 区域数据
// ============================================================================

export const STATS_DATA: StatItem[] = [
  { value: 10, label: '核心功能模块' },
  { value: 200, label: 'API 接口' },
  { value: 24, label: '小时自动化' },
]

export const FLOATING_CARDS: FloatingCardData[] = [
  {
    icon: Archive,
    title: '案件自动归档',
    description: '智能分类整理',
    position: 'left',
    colorScheme: 'purple',
  },
  {
    icon: Bot,
    title: 'AI 文书生成',
    description: '一键生成诉状',
    position: 'right',
    colorScheme: 'cyan',
  },
  {
    icon: BarChart3,
    title: '数据可视化',
    description: '案件进度追踪',
    position: 'bottom',
    colorScheme: 'pink',
  },
]

// ============================================================================
// Bento Grid 功能数据
// ============================================================================

export const FEATURES_DATA: BentoCardData[] = [
  {
    icon: FolderOpen,
    title: '案件管理',
    description:
      '全生命周期案件管理，从立案到结案。支持案件创建、分配、进度跟踪、案号管理，多维度数据统计分析。',
    size: 'large',
    colorScheme: 'style-1',
    hasVisual: true,
  },
  {
    icon: Sparkles,
    title: 'AI 文书生成',
    description:
      '基于 LangChain + LangGraph 的智能文书生成，支持起诉状、答辩状、代理词、财产保全申请书等，对话式交互引导。',
    size: 'default',
    colorScheme: 'style-2',
  },
  {
    icon: FileText,
    title: '合同管理',
    description: '合同创建、补充协议、付款跟踪、律师分配、收费进度，完整的合同生命周期管理。',
    size: 'default',
    colorScheme: 'style-3',
  },
  {
    icon: Zap,
    title: '自动化引擎',
    description:
      '法院短信智能解析与文书自动下载、法院文书定时抓取、财产保全保险自动询价、飞书群消息实时通知、验证码自动识别。7×24 小时无人值守运行。',
    size: 'wide',
    colorScheme: 'style-1',
  },
  {
    icon: Users,
    title: '客户管理',
    description: '客户信息、身份证件 OCR 识别、财产线索管理，一站式 CRM 解决方案。',
    size: 'default',
    colorScheme: 'style-2',
  },
  {
    icon: FileText,
    title: '文档模板系统',
    description: '可视化模板配置，支持占位符、条件渲染、案件类型匹配、批量生成 Word 文档。',
    size: 'default',
    colorScheme: 'style-3',
  },
  {
    icon: MessageSquare,
    title: '聊天记录取证',
    description: '微信/QQ 聊天记录视频录制、智能截帧、OCR 文字提取，一键生成证据材料。',
    size: 'default',
    colorScheme: 'style-1',
  },
  {
    icon: Shield,
    title: '数据安全',
    description: '端到端加密传输，支持本地私有化部署，数据完全掌控在您手中。',
    size: 'default',
    colorScheme: 'style-2',
  },
]

// ============================================================================
// 短信处理流程节点
// ============================================================================

export const SMS_PROCESS_NODES: ProcessNodeData[] = [
  { id: 'receive', icon: Activity, title: '接收短信', colorScheme: 'receive' },
  { id: 'parse', icon: Link, title: '解析链接', colorScheme: 'parse' },
  { id: 'download', icon: Download, title: '下载文书', colorScheme: 'download' },
  { id: 'match', icon: FolderOpen, title: '匹配案件', colorScheme: 'match' },
  { id: 'rename', icon: Pencil, title: '重命名归档', colorScheme: 'rename' },
  { id: 'analyze', icon: Sparkles, title: '智能分析', colorScheme: 'analyze' },
  { id: 'notify', icon: Bell, title: '推送通知', colorScheme: 'notify' },
]

// ============================================================================
// 短信处理结果卡片数据
// ============================================================================

export const SMS_RESULT_CARDS = [
  {
    id: 'archived',
    title: '文书已归档',
    description: '民事判决书.pdf',
    icon: FolderOpen,
    colorScheme: 'green',
  },
  {
    id: 'renamed',
    title: '已重命名',
    description: '(2024)粤0106民初12345号_民事判决书.pdf',
    icon: Pencil,
    colorScheme: 'blue',
  },
  {
    id: 'reminder',
    title: '开庭提醒',
    description: '已创建日历事件',
    icon: Bell,
    colorScheme: 'yellow',
  },
  {
    id: 'alert',
    title: '费用异常',
    description: '检测到诉讼费差异',
    icon: Shield,
    colorScheme: 'red',
  },
]

// ============================================================================
// 聊天记录处理 AI 任务
// ============================================================================

export const CHAT_AI_TASKS = [
  { id: 'decode', title: '视频解码', icon: Activity },
  { id: 'scene', title: '场景检测', icon: Sparkles },
  { id: 'dedup', title: '去重过滤', icon: Shield },
  { id: 'ocr', title: 'OCR识别', icon: FileText },
]

// ============================================================================
// 技术栈数据
// ============================================================================

export const TECH_STACK: TechCategory[] = [
  {
    title: '后端框架',
    icon: '🔧',
    items: [
      { name: 'Django 6.0', description: 'Python Web 框架', icon: '🐍' },
      { name: 'Django Ninja', description: '高性能 API 框架', icon: '⚡' },
      { name: 'Celery', description: '异步任务队列', icon: '🥬' },
    ],
  },
  {
    title: '数据存储',
    icon: '💾',
    items: [
      { name: 'PostgreSQL', description: '关系型数据库', icon: '🐘' },
      { name: 'Redis', description: '缓存与消息队列', icon: '🔴' },
      { name: 'MinIO', description: '对象存储', icon: '📦' },
    ],
  },
  {
    title: 'AI / 自动化',
    icon: '🤖',
    items: [
      { name: 'LangChain', description: 'LLM 应用框架', icon: '🦜' },
      { name: 'Playwright', description: '浏览器自动化', icon: '🎭' },
      { name: 'PaddleOCR', description: '文字识别', icon: '👁️' },
    ],
  },
]

// ============================================================================
// 架构亮点统计
// ============================================================================

export const ARCH_HIGHLIGHTS = [
  { value: 4, label: '层架构设计', suffix: '' },
  { value: 99.9, label: '系统可用性', suffix: '%' },
  { value: 100, label: '测试覆盖率', suffix: '%' },
]

// ============================================================================
// CTA 区域数据
// ============================================================================

export const QR_CODES = [
  {
    src: '/images/qr-wechat-personal.png',
    alt: '个人微信二维码',
    title: '联系作者',
  },
]

// ============================================================================
// 响应式断点
// ============================================================================

export const BREAKPOINTS = {
  mobile: 768,
  tablet: 1024,
  desktop: 1280,
} as const

// ============================================================================
// 滚动阈值
// ============================================================================

export const SCROLL_THRESHOLD = 50
