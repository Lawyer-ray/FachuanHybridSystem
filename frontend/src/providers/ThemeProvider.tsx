'use client'

import { ThemeProvider as NextThemesProvider } from 'next-themes'

interface ThemeProviderProps {
  children: React.ReactNode
}

/**
 * ThemeProvider - 主题系统提供者
 *
 * 使用 next-themes 实现明暗主题切换功能
 *
 * 配置说明:
 * - attribute="class": 使用 class 属性切换主题，配合 Tailwind CSS dark mode
 * - defaultTheme="light": 默认使用明亮模式 (Requirement 7.1)
 * - enableSystem={false}: 禁用系统主题检测，确保默认为明亮模式
 * - storageKey="theme": 将主题偏好持久化到 localStorage (Requirement 7.3, 7.4)
 *
 * @validates Requirements 7.1, 7.2, 7.3, 7.4
 */
export function ThemeProvider({ children }: ThemeProviderProps) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="light"
      enableSystem={false}
      storageKey="theme"
    >
      {children}
    </NextThemesProvider>
  )
}
