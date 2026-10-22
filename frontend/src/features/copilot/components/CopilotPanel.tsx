/**
 * Copilot 右侧常驻面板：导航栏图标唤起，AppShell 懒加载挂载。
 *
 * 非模态 dock（不用 Sheet：那会盖遮罩锁滚动），覆盖在内容区右侧；
 * z-[100] 高于页面与全屏阅读器（z-[80]），低于弹窗基线 z-[130]。
 * 路由切换不影响本面板（挂在壳层），流式收发归 store，收起面板流不断。
 */

import { useEffect } from 'react'
import { X } from 'lucide-react'

import { useCopilot } from '../store'
import { Composer } from './Composer'
import { MessageList } from './MessageList'
import { SessionMenu } from './SessionMenu'

export function CopilotPanel({ onClose }: { onClose: () => void }) {
  const sessionId = useCopilot((s) => s.sessionId)
  const switchSession = useCopilot((s) => s.switchSession)

  // 恢复上次会话的历史（StrictMode 双挂载幂等：同 id 重拉无害）
  useEffect(() => {
    void switchSession(sessionId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <aside
      className="fixed top-(--app-navbar-h) right-0 bottom-0 z-[100] flex w-full flex-col border-l border-border bg-card shadow-[-8px_0_24px_rgba(0,0,0,0.06)] sm:w-[404px]"
      aria-label="AI 助手"
    >
      <header className="flex h-12 flex-none items-center gap-2 border-b border-border px-3">
        <SessionMenu />
        <span className="text-[13px] font-semibold text-foreground">AI 助手</span>
        <span className="ml-auto" />
        <button
          type="button"
          className="flex h-7 w-7 items-center justify-center rounded-[8px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          onClick={onClose}
          aria-label="收起 AI 助手"
        >
          <X className="h-4 w-4" />
        </button>
      </header>

      <MessageList />
      <Composer />
    </aside>
  )
}
