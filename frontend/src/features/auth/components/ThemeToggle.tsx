'use client'

import { Moon, Sun } from 'lucide-react'
import { useTheme } from 'next-themes'
import { Button } from '@/components/ui/button'

/**
 * ThemeToggle - 主题切换按钮组件
 *
 * 使用 next-themes 的 useTheme hook 实现明暗主题切换
 *
 * 功能说明:
 * - 点击按钮切换明暗模式
 * - 使用 Lucide 图标显示当前主题状态
 * - Sun 图标在明亮模式下显示，Moon 图标在暗黑模式下显示
 * - 使用 CSS transition 实现平滑的图标切换动画
 *
 * @validates Requirements 7.2 - WHEN 用户点击主题切换按钮 THEN THE Theme_System SHALL 切换明暗模式
 */
export function ThemeToggle() {
  const { theme, setTheme } = useTheme()

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}
      aria-label="切换主题"
    >
      <Sun className="h-5 w-5 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
      <Moon className="absolute h-5 w-5 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
      <span className="sr-only">切换主题</span>
    </Button>
  )
}
