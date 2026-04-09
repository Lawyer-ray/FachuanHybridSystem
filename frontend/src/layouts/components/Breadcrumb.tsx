'use client'

import { Link } from 'react-router'
import { ChevronRight, Home } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * 面包屑项接口
 */
export interface BreadcrumbItem {
  /** 显示标签 */
  label: string
  /** 路由路径（可选，最后一项无链接） */
  path?: string
}

/**
 * Breadcrumb 组件属性
 */
export interface BreadcrumbProps {
  /** 面包屑项数组 */
  items: BreadcrumbItem[]
}

/**
 * Breadcrumb - 面包屑导航组件
 *
 * 实现后台管理系统的面包屑导航，支持：
 * - 显示从首页到当前页面的完整路径
 * - 点击导航到对应页面
 * - 最后一项无链接（当前页面）
 * - 明亮/暗夜主题支持
 * - 响应式设计
 *
 * @validates Requirements 2.1 - THE Breadcrumb SHALL 显示从首页到当前页面的完整路径
 * @validates Requirements 2.2 - WHEN 用户点击面包屑中的某一层级 THEN THE System SHALL 导航到对应页面
 * @validates Requirements 2.3 - THE Breadcrumb SHALL 在当事人列表页显示「首页 / 当事人」
 * @validates Requirements 2.4 - THE Breadcrumb SHALL 在当事人详情页显示「首页 / 当事人 / {当事人姓名}」
 * @validates Requirements 2.5 - THE Breadcrumb SHALL 在当事人编辑页显示「首页 / 当事人 / {当事人姓名} / 编辑」
 * @validates Requirements 2.6 - THE Breadcrumb SHALL 在新建当事人页显示「首页 / 当事人 / 新建」
 *
 * @example
 * // 当事人列表页
 * <Breadcrumb items={[
 *   { label: '首页', path: '/admin/dashboard' },
 *   { label: '当事人' }
 * ]} />
 *
 * @example
 * // 当事人详情页
 * <Breadcrumb items={[
 *   { label: '首页', path: '/admin/dashboard' },
 *   { label: '当事人', path: '/admin/clients' },
 *   { label: '张三' }
 * ]} />
 */
export function Breadcrumb({ items }: BreadcrumbProps) {
  if (!items || items.length === 0) {
    return null
  }

  return (
    <nav
      aria-label="面包屑导航"
      className={cn(
        'flex items-center',
        'text-sm',
        'py-2'
      )}
    >
      <ol className="flex items-center flex-wrap gap-1">
        {items.map((item, index) => {
          const isLast = index === items.length - 1
          const isFirst = index === 0

          return (
            <li
              key={`${item.label}-${index}`}
              className="flex items-center"
            >
              {/* 分隔符（非首项显示） */}
              {!isFirst && (
                <ChevronRight
                  className={cn(
                    'w-4 h-4 mx-1.5',
                    'text-muted-foreground/50',
                    'shrink-0'
                  )}
                  aria-hidden="true"
                />
              )}

              {/* 面包屑项 */}
              {isLast || !item.path ? (
                // 最后一项或无路径：纯文本
                <span
                  className={cn(
                    'flex items-center gap-1.5',
                    'text-foreground font-medium',
                    'truncate max-w-[200px]'
                  )}
                  aria-current={isLast ? 'page' : undefined}
                >
                  {isFirst && (
                    <Home
                      className={cn(
                        'w-4 h-4 shrink-0',
                        'text-muted-foreground'
                      )}
                      aria-hidden="true"
                    />
                  )}
                  {item.label}
                </span>
              ) : (
                // 可点击链接
                <Link
                  to={item.path}
                  className={cn(
                    'flex items-center gap-1.5',
                    'text-muted-foreground',
                    'hover:text-foreground',
                    'transition-colors duration-200',
                    'truncate max-w-[200px]',
                    // 触摸设备友好的点击区域
                    'py-0.5 -my-0.5'
                  )}
                >
                  {isFirst && (
                    <Home
                      className={cn(
                        'w-4 h-4 shrink-0'
                      )}
                      aria-hidden="true"
                    />
                  )}
                  {item.label}
                </Link>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}

export default Breadcrumb
