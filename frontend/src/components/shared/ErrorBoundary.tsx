import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'

interface ErrorBoundaryProps {
  children: ReactNode
}

interface ErrorBoundaryState {
  error: Error | null
}

/**
 * 路由级错误边界：捕获渲染期异常与懒加载 chunk 拉取失败，给一个可恢复的
 * 兜底页而不是白屏。「重新加载」走整页刷新——边界内没有可靠的局部恢复手段。
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // 上报点位：接入 Sentry/GlitchTip 等时在这里补 transport
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    const isChunkError = /Loading chunk|Failed to fetch dynamically imported module/i.test(this.state.error.message)
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-background px-6 text-center">
        <p className="text-[15px] font-semibold">
          {isChunkError ? '页面资源加载失败' : '页面出错了'}
        </p>
        <p className="max-w-[420px] text-[12.5px] leading-relaxed text-secondary-foreground">
          {isChunkError
            ? '可能是应用刚发布了新版本，本地缓存的旧资源已失效。刷新一次通常即可恢复。'
            : '渲染时发生异常，刷新重试；若持续出现请反馈给开发。'}
        </p>
        <Button onClick={() => window.location.reload()}>重新加载</Button>
      </div>
    )
  }
}
