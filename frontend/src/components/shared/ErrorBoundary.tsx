import { Component, type ErrorInfo, type ReactNode } from 'react'
import { useLocation } from 'react-router'
import { Button } from '@/components/ui/button'

interface ErrorBoundaryProps {
  children: ReactNode
  /** app = 整页兜底；page = 页内块级兜底（导航栏存活、路由切换自动复位） */
  variant?: 'app' | 'page'
  /**
   * 变化时清除已捕获的错误（无错误时不做任何事，children 实例原样保留）。
   * 不要用 key 达成同样目的：key 变化会把整棵健康子树卸载重挂，
   * 路由级用法下每次 pathname 变化都整页重建，正是切页闪烁的源头之一。
   */
  resetKey?: unknown
}

interface ErrorBoundaryState {
  error: Error | null
  /** 上次看到的 resetKey，用于在派生 state 时判断是否该清错 */
  resetKey: unknown
}

/**
 * 错误边界：捕获渲染期异常与懒加载 chunk 拉取失败，给一个可恢复的
 * 兜底页而不是白屏。「重新加载」走整页刷新——边界内没有可靠的局部恢复手段。
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null, resetKey: this.props.resetKey }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return { error }
  }

  static getDerivedStateFromProps(
    props: ErrorBoundaryProps,
    state: ErrorBoundaryState,
  ): Partial<ErrorBoundaryState> | null {
    if (Object.is(props.resetKey, state.resetKey)) return null
    return { resetKey: props.resetKey, error: null }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // 上报点位：接入 Sentry/GlitchTip 等时在这里补 transport
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    const isChunkError = /Loading chunk|Failed to fetch dynamically imported module/i.test(this.state.error.message)
    const isPage = this.props.variant === 'page'
    return (
      <div
        className={
          isPage
            ? 'flex min-h-[60vh] flex-col items-center justify-center gap-3 px-6 text-center'
            : 'flex min-h-screen flex-col items-center justify-center gap-3 bg-background px-6 text-center'
        }
      >
        <p className="text-[15px] font-semibold">
          {isChunkError ? '页面资源加载失败' : '页面出错了'}
        </p>
        <p className="max-w-[420px] text-[12.5px] leading-relaxed text-secondary-foreground">
          {isChunkError
            ? '可能是应用刚发布了新版本，本地缓存的旧资源已失效。刷新一次通常即可恢复。'
            : '渲染时发生异常，可返回其他页面或刷新重试；若持续出现请反馈给开发。'}
        </p>
        <Button onClick={() => window.location.reload()}>重新加载</Button>
      </div>
    )
  }
}

/**
 * 路由页面级边界：以 pathname 作 resetKey——单个页面渲染崩溃只损失该页，
 * 切到其他路由时边界自动复位，不掀掉整个应用（全局边界退居兜底）。
 * 页面健康时 pathname 变化不会触碰子树：同一页面在列表 / 详情子路由间
 * 切换（如 /material-prep ↔ /material-prep/:id）保持组件实例与本地状态。
 */
export function PageErrorBoundary({ children }: { children: ReactNode }) {
  const { pathname } = useLocation()
  return (
    <ErrorBoundary variant="page" resetKey={pathname}>
      {children}
    </ErrorBoundary>
  )
}
