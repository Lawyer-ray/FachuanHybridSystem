'use client'

import { Outlet } from 'react-router'
import { motion } from 'framer-motion'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { ThemeToggle } from '@/features/auth/components/ThemeToggle'

/**
 * AuthLayout - 认证页面共享布局组件
 *
 * 作为登录和注册页面的共享布局，提供：
 * - 居中卡片布局
 * - 主题切换按钮（右上角）
 * - Framer Motion 入场动画
 * - 响应式设计（适配移动端和桌面端）
 * - 简约高级的设计风格
 *
 * @validates Requirements 9.1 - 使用 Shadcn/ui 组件库
 * @validates Requirements 9.2 - 使用 Framer Motion 实现流畅的动画效果
 * @validates Requirements 9.3 - 采用简约高级的设计风格
 * @validates Requirements 9.4 - 支持响应式布局，适配移动端和桌面端
 * @validates Requirements 9.5 - 作为登录和注册页面的共享布局组件
 */

interface AuthLayoutProps {
  children?: React.ReactNode
  title?: string
  description?: string
}

/**
 * AuthLayoutCard - 带动画的认证卡片组件
 * 用于包装登录/注册表单，提供统一的卡片样式和入场动画
 */
export function AuthLayoutCard({ children, title, description }: AuthLayoutProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: 0.4,
        ease: [0.25, 0.46, 0.45, 0.94] // easeOutQuad for smooth deceleration
      }}
      className="w-full max-w-md"
    >
      <Card className="shadow-lg border-border/50 backdrop-blur-sm">
        {(title || description) && (
          <CardHeader className="space-y-1 pb-4">
            {title && (
              <CardTitle className="text-2xl font-semibold tracking-tight text-center">
                {title}
              </CardTitle>
            )}
            {description && (
              <CardDescription className="text-center text-muted-foreground">
                {description}
              </CardDescription>
            )}
          </CardHeader>
        )}
        <CardContent className={title || description ? '' : 'pt-6'}>
          {children}
        </CardContent>
      </Card>
    </motion.div>
  )
}

/**
 * AuthLayout - 主布局组件
 * 使用 Outlet 渲染子路由，支持作为 React Router 布局使用
 */
export function AuthLayout() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-background via-background to-muted/20 p-4 sm:p-6 lg:p-8">
      {/* 背景装饰 - 简约的渐变效果 */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-1/2 -right-1/2 w-full h-full bg-gradient-to-bl from-primary/5 via-transparent to-transparent rounded-full blur-3xl" />
        <div className="absolute -bottom-1/2 -left-1/2 w-full h-full bg-gradient-to-tr from-primary/5 via-transparent to-transparent rounded-full blur-3xl" />
      </div>

      {/* 主题切换按钮 - 固定在右上角 */}
      <motion.div
        className="fixed top-4 right-4 z-50"
        initial={{ opacity: 0, scale: 0.8 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.2, duration: 0.3 }}
      >
        <ThemeToggle />
      </motion.div>

      {/* 内容区域 - 使用 Outlet 渲染子路由 */}
      <div className="relative z-10 w-full flex items-center justify-center">
        <Outlet />
      </div>
    </div>
  )
}

export default AuthLayout
