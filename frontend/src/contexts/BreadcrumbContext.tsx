/**
 * BreadcrumbContext - 面包屑上下文
 *
 * 提供动态面包屑功能，允许页面组件覆盖默认的面包屑项。
 * 用于显示动态内容如当事人姓名、案件名称等。
 *
 * @validates Requirements 2.4 - THE Breadcrumb SHALL 在当事人详情页显示「首页 / 当事人 / {当事人姓名}」
 * @validates Requirements 2.5 - THE Breadcrumb SHALL 在当事人编辑页显示「首页 / 当事人 / {当事人姓名} / 编辑」
 */

import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  type ReactNode,
} from 'react'
import type { BreadcrumbItem } from '@/layouts/components/Breadcrumb'

// ============================================================================
// Types
// ============================================================================

interface BreadcrumbContextValue {
  /** 自定义面包屑项（如果设置，将覆盖默认生成的面包屑） */
  customItems: BreadcrumbItem[] | null
  /** 设置自定义面包屑项 */
  setCustomItems: (items: BreadcrumbItem[] | null) => void
}

// ============================================================================
// Context
// ============================================================================

const BreadcrumbContext = createContext<BreadcrumbContextValue | null>(null)

// ============================================================================
// Provider
// ============================================================================

interface BreadcrumbProviderProps {
  children: ReactNode
}

/**
 * BreadcrumbProvider - 面包屑上下文提供者
 *
 * 包裹在 AdminLayout 中，为子组件提供动态面包屑功能。
 */
export function BreadcrumbProvider({ children }: BreadcrumbProviderProps) {
  const [customItems, setCustomItems] = useState<BreadcrumbItem[] | null>(null)

  const value: BreadcrumbContextValue = {
    customItems,
    setCustomItems,
  }

  return (
    <BreadcrumbContext.Provider value={value}>
      {children}
    </BreadcrumbContext.Provider>
  )
}

// ============================================================================
// Hooks
// ============================================================================

/**
 * useBreadcrumbContext - 获取面包屑上下文
 *
 * @returns 面包屑上下文值
 * @throws 如果在 BreadcrumbProvider 外部使用
 */
export function useBreadcrumbContext(): BreadcrumbContextValue {
  const context = useContext(BreadcrumbContext)
  if (!context) {
    throw new Error('useBreadcrumbContext must be used within a BreadcrumbProvider')
  }
  return context
}

/**
 * useBreadcrumb - 设置自定义面包屑的 Hook
 *
 * 在页面组件中使用此 Hook 来设置自定义面包屑项。
 * 组件卸载时会自动清除自定义面包屑。
 *
 * @param items - 面包屑项数组，传入 null 使用默认面包屑
 *
 * @example
 * ```tsx
 * // 在当事人详情页中使用
 * function ClientDetailPage() {
 *   const { data: client } = useClient(id)
 *
 *   useBreadcrumb(client ? [
 *     { label: '首页', path: '/admin/dashboard' },
 *     { label: '当事人', path: '/admin/clients' },
 *     { label: client.name }
 *   ] : null)
 *
 *   return <ClientDetail clientId={id} />
 * }
 * ```
 */
export function useBreadcrumb(items: BreadcrumbItem[] | null): void {
  const { setCustomItems } = useBreadcrumbContext()

  useEffect(() => {
    setCustomItems(items)

    // 组件卸载时清除自定义面包屑
    return () => {
      setCustomItems(null)
    }
  }, [items, setCustomItems])
}

/**
 * useSetBreadcrumb - 获取设置面包屑的函数
 *
 * 用于需要在回调中动态设置面包屑的场景。
 *
 * @returns 设置面包屑的函数
 */
export function useSetBreadcrumb(): (items: BreadcrumbItem[] | null) => void {
  const { setCustomItems } = useBreadcrumbContext()
  return useCallback(
    (items: BreadcrumbItem[] | null) => setCustomItems(items),
    [setCustomItems]
  )
}

export default BreadcrumbProvider
