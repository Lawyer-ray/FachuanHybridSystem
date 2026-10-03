/**
 * 全局错误兜底：window 级 unhandledrejection / error 监听，覆盖 ErrorBoundary
 * 管不到的事件回调、异步 rejection 等。结构化前缀输出，方便在日志里过滤。
 */
function report(kind: 'rejection' | 'error', detail: unknown): void {
  // 上报点位：接入 Sentry/GlitchTip 等时只改这里补 transport
  console.error(`[unhandled] ${kind}:`, detail)
}

let installed = false

/** main.tsx 启动时调用一次；重复调用幂等。 */
export function setupGlobalErrorLogging(): void {
  if (installed) return
  installed = true
  window.addEventListener('unhandledrejection', (e) => report('rejection', e.reason))
  window.addEventListener('error', (e) => report('error', e.error ?? e.message))
}
