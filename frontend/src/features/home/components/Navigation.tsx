/**
 * 导航栏组件
 * @module features/home/components/Navigation
 *
 * 固定顶部导航栏，具有毛玻璃效果和滚动状态切换
 * Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6
 */

import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router'
import { motion, AnimatePresence } from 'framer-motion'
import { Menu, X, ArrowUpRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useScrollPosition } from '../hooks/use-scroll-position'
import { NAV_LINKS } from '../constants'
import type { NavigationProps } from '../types'

/**
 * 判断链接是否为页面跳转链接（非锚点）
 */
function isPageLink(href: string): boolean {
  return !href.startsWith('#') && !href.startsWith('http') && !href.startsWith('/api')
}

/**
 * 平滑滚动到锚点
 * @param href - 锚点链接
 */
function scrollToAnchor(href: string) {
  const targetId = href.slice(1)
  const targetElement = document.getElementById(targetId)

  if (targetElement) {
    targetElement.scrollIntoView({
      behavior: 'smooth',
      block: 'start',
    })
  }
}

/**
 * 导航栏组件
 *
 * 功能：
 * - 固定在页面顶部 (position: fixed)
 * - 毛玻璃效果 (backdrop-filter: blur)
 * - 滚动超过 50px 时切换为紧凑样式
 * - 包含 logo、导航链接和 CTA 按钮
 * - 点击导航链接平滑滚动到对应区域
 * - 移动端显示汉堡菜单按钮，点击展开导航抽屉
 */
export function Navigation({ className }: NavigationProps) {
  const { isScrolled } = useScrollPosition()
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()

  /**
   * 处理导航链接点击
   * 锚点链接滚动，路由链接导航
   */
  function handleNavClick(href: string) {
    setIsMobileMenuOpen(false)

    // 外部链接
    if (href.startsWith('http') || href.startsWith('/api')) {
      window.open(href, '_blank')
      return
    }

    // 锚点链接
    if (href.startsWith('#')) {
      // 如果不在首页，先导航到首页再滚动
      if (location.pathname !== '/') {
        navigate('/')
        // 延迟滚动，等待页面加载
        setTimeout(() => scrollToAnchor(href), 100)
      } else {
        scrollToAnchor(href)
      }
      return
    }

    // 内部路由链接
    navigate(href)
  }

  return (
    <motion.header
      initial={{ y: -100, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ type: 'spring', stiffness: 100, damping: 20 }}
      className={cn(
        // 固定定位
        'fixed top-0 left-0 right-0 z-50',
        // 毛玻璃效果
        'backdrop-blur-xl',
        // 过渡动画
        'transition-all duration-300 ease-out',
        // 根据滚动状态切换样式
        isScrolled
          ? 'py-3 bg-home-bg-dark/90 border-b border-home-border/50 shadow-lg shadow-black/10'
          : 'py-5 bg-transparent border-b border-transparent',
        className
      )}
    >
      <div className="container mx-auto px-4 sm:px-6 lg:px-8">
        <nav className="flex items-center justify-between">
          {/* Logo */}
          <motion.button
            onClick={() => navigate('/')}
            className="flex items-center gap-2 group"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            <span className={cn(
              'font-bold bg-gradient-to-r from-home-primary to-home-accent bg-clip-text text-transparent transition-all duration-300',
              isScrolled ? 'text-xl' : 'text-2xl'
            )}>
              法穿AI
            </span>
          </motion.button>

          {/* 导航链接 - 桌面端显示 */}
          <div className="hidden md:flex items-center gap-1">
            {NAV_LINKS.map((link) => {
              const isPage = isPageLink(link.href)
              return (
                <motion.button
                  key={link.href}
                  onClick={() => handleNavClick(link.href)}
                  className={cn(
                    'px-4 py-2 rounded-lg text-sm font-medium',
                    'transition-colors duration-200',
                    isPage
                      ? // 页面跳转链接 - 带边框和箭头图标
                        'flex items-center gap-1 border border-home-border/50 text-home-text hover:border-home-primary/50 hover:bg-home-primary/10'
                      : // 锚点链接 - 普通样式
                        'text-home-text-muted hover:text-home-text hover:bg-home-bg-card/50'
                  )}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                >
                  {link.label}
                  {isPage && <ArrowUpRight className="h-3.5 w-3.5 opacity-60" />}
                </motion.button>
              )
            })}
          </div>

          {/* CTA 按钮和移动端菜单按钮 */}
          <div className="flex items-center gap-3">
            <motion.div
              whileHover={{ scale: 1.05, y: -2 }}
              whileTap={{ scale: 0.95 }}
            >
              <Button
                variant="ghost"
                size={isScrolled ? 'sm' : 'default'}
                className={cn(
                  'hidden sm:inline-flex',
                  'text-home-text-muted hover:text-home-text',
                  'hover:bg-home-bg-card/50',
                  'transition-all duration-300'
                )}
                onClick={() => window.open('https://github.com/fachuan-ai/fachuan-ai', '_blank')}
              >
                GitHub
              </Button>
            </motion.div>

            <motion.div
              whileHover={{
                scale: 1.05,
                y: -2,
                boxShadow: '0 0 20px rgba(var(--home-primary), 0.4)'
              }}
              whileTap={{ scale: 0.95 }}
              className="hidden sm:block"
            >
              <Button
                size={isScrolled ? 'sm' : 'default'}
                className={cn(
                  'bg-gradient-to-r from-home-primary to-home-accent',
                  'hover:from-home-primary-light hover:to-home-accent-light',
                  'text-white font-medium',
                  'shadow-lg shadow-home-primary/25',
                  'transition-all duration-300'
                )}
                onClick={() => window.location.href = '/login'}
              >
                立即体验
              </Button>
            </motion.div>

            {/* 移动端菜单按钮 - 仅在 < 768px 显示 */}
            <motion.button
              whileTap={{ scale: 0.9 }}
              onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
              className={cn(
                'md:hidden flex items-center justify-center',
                'w-10 h-10 rounded-lg',
                'text-home-text hover:text-home-text',
                'hover:bg-home-bg-card/50',
                'transition-colors duration-200'
              )}
              aria-label={isMobileMenuOpen ? '关闭菜单' : '打开菜单'}
            >
              <AnimatePresence mode="wait">
                {isMobileMenuOpen ? (
                  <motion.div
                    key="close"
                    initial={{ rotate: -90, opacity: 0 }}
                    animate={{ rotate: 0, opacity: 1 }}
                    exit={{ rotate: 90, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                  >
                    <X className="w-6 h-6" />
                  </motion.div>
                ) : (
                  <motion.div
                    key="menu"
                    initial={{ rotate: 90, opacity: 0 }}
                    animate={{ rotate: 0, opacity: 1 }}
                    exit={{ rotate: -90, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                  >
                    <Menu className="w-6 h-6" />
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.button>
          </div>
        </nav>
      </div>

      {/* 移动端导航抽屉 */}
      <AnimatePresence>
        {isMobileMenuOpen && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.3, ease: 'easeInOut' }}
            className={cn(
              'md:hidden overflow-hidden',
              'bg-home-bg-dark/95 backdrop-blur-xl',
              'border-t border-home-border/30'
            )}
          >
            <div className="container mx-auto px-4 py-4">
              <div className="flex flex-col gap-2">
                {NAV_LINKS.map((link, index) => {
                  const isPage = isPageLink(link.href)
                  return (
                    <motion.button
                      key={link.href}
                      initial={{ opacity: 0, x: -20 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: index * 0.05 }}
                      onClick={() => handleNavClick(link.href)}
                      className={cn(
                        'w-full px-4 py-3 rounded-lg text-left',
                        'transition-colors duration-200',
                        isPage
                          ? 'flex items-center justify-between border border-home-border/50 text-home-text hover:border-home-primary/50 hover:bg-home-primary/10'
                          : 'text-home-text-muted hover:text-home-text hover:bg-home-bg-card/50'
                      )}
                    >
                      {link.label}
                      {isPage && <ArrowUpRight className="h-4 w-4 opacity-60" />}
                    </motion.button>
                  )
                })}

                {/* 移动端 CTA 按钮 */}
                <div className="flex flex-col gap-2 mt-4 pt-4 border-t border-home-border/30">
                  <Button
                    variant="outline"
                    className={cn(
                      'w-full justify-center',
                      'border-home-border text-home-text-muted',
                      'hover:bg-home-bg-card/50 hover:text-home-text'
                    )}
                    onClick={() => {
                      window.open('https://github.com/fachuan-ai/fachuan-ai', '_blank')
                      setIsMobileMenuOpen(false)
                    }}
                  >
                    GitHub
                  </Button>
                  <Button
                    className={cn(
                      'w-full justify-center',
                      'bg-gradient-to-r from-home-primary to-home-accent',
                      'hover:from-home-primary-light hover:to-home-accent-light',
                      'text-white font-medium'
                    )}
                    onClick={() => {
                      window.location.href = '/login'
                      setIsMobileMenuOpen(false)
                    }}
                  >
                    立即体验
                  </Button>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.header>
  )
}
