/**
 * Copilot 右侧常驻面板：导航栏图标唤起，AppShell 懒加载挂载。
 *
 * 布局：md+ 为**双栏**（左侧 180px 会话栏常驻 + 右侧对话区，面板加宽到
 * 600px，会话切换/重命名/删除一步直达）；sm 以下为单栏 + 覆盖式会话列表
 * （从左滑入）。非模态 dock：z-[100] 高于页面与全屏阅读器（z-[80]），
 * 低于菜单类 portal（z-[120]）与弹窗基线（z-[130]）。
 * 路由切换不影响本面板（挂在壳层），流式收发归 store，收起面板流不断。
 * 开/收带滑入滑出动画：AppShell 在 animate-out 播完前保持挂载。
 */

import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { PanelLeft, Plus, X } from 'lucide-react'

import { listSessions } from '../api'
import { useCopilot } from '../store'
import { Composer } from './Composer'
import { MessageList } from './MessageList'
import { SessionSidebar } from './SessionSidebar'

const RAIL_KEY = 'copilot:rail'

function readRailOpen(): boolean {
  try {
    return localStorage.getItem(RAIL_KEY) !== '0'
  } catch {
    return true
  }
}

export function CopilotPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const sessionId = useCopilot((s) => s.sessionId)
  const streaming = useCopilot((s) => s.streaming)
  const switchSession = useCopilot((s) => s.switchSession)
  const queryClient = useQueryClient()
  // md+ 常驻会话栏的开关（持久化）；窄屏覆盖式列表的开关（瞬态）
  const [railOpen, setRailOpen] = useState(readRailOpen)
  const [listOverlayOpen, setListOverlayOpen] = useState(false)

  // 恢复上次会话的历史（StrictMode 双挂载幂等：同 id 重拉无害）
  useEffect(() => {
    void switchSession(sessionId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 面板标题取当前会话标题：会话列表缓存里查（缓存由侧栏/流结束刷新）
  const sessionsQuery = useQuery({
    queryKey: ['copilot', 'sessions'],
    queryFn: () => listSessions(50),
    enabled: Boolean(sessionId),
    staleTime: 30_000,
    retry: false,
  })
  const currentTitle = sessionId ? sessionsQuery.data?.find((s) => s.session_id === sessionId)?.title : ''

  // 每轮流结束后刷新会话列表：首条消息会自动生成标题，标题要能浮上来
  useEffect(() => {
    if (!streaming && sessionId) {
      void queryClient.invalidateQueries({ queryKey: ['copilot', 'sessions'] })
    }
  }, [streaming, sessionId, queryClient])

  const toggleList = () => {
    if (window.matchMedia('(min-width: 768px)').matches) {
      setRailOpen((v) => {
        try {
          localStorage.setItem(RAIL_KEY, v ? '0' : '1')
        } catch {
          /* 忽略持久化失败 */
        }
        return !v
      })
    } else {
      setListOverlayOpen((v) => !v)
    }
  }

  return (
    <aside
      className={`fixed top-(--app-navbar-h) right-0 bottom-0 z-[100] flex w-full flex-col border-l border-border bg-card shadow-[-8px_0_24px_rgba(0,0,0,0.06)] duration-200 fill-mode-both sm:w-[404px] ${
        railOpen ? 'md:w-[600px]' : 'md:w-[404px]'
      } ${open ? 'animate-in slide-in-from-right' : 'animate-out slide-out-to-right'}`}
      aria-label="AI 助手"
    >
      <header className="flex h-12 flex-none items-center gap-1.5 border-b border-border px-2.5">
        <button
          type="button"
          className="flex h-7 w-7 flex-none items-center justify-center rounded-[8px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          onClick={toggleList}
          aria-label="对话列表"
        >
          <PanelLeft className="h-4 w-4" />
        </button>
        <span className="min-w-0 flex-1 truncate px-0.5 text-[13px] font-semibold text-foreground">
          {currentTitle || 'AI 助手'}
        </span>
        <button
          type="button"
          className="flex h-7 flex-none items-center gap-1 rounded-[8px] px-2 text-[12.5px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          onClick={() => {
            void switchSession(null)
            setListOverlayOpen(false)
          }}
        >
          <Plus className="h-3.5 w-3.5" strokeWidth={2.5} />
          新对话
        </button>
        <button
          type="button"
          className="flex h-7 w-7 flex-none items-center justify-center rounded-[8px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          onClick={onClose}
          aria-label="收起 AI 助手"
        >
          <X className="h-4 w-4" />
        </button>
      </header>

      <div className="relative flex min-h-0 flex-1">
        {railOpen && <SessionSidebar variant="rail" />}
        {listOverlayOpen && (
          <SessionSidebar variant="overlay" onClose={() => setListOverlayOpen(false)} />
        )}
        <MessageList />
      </div>
      <Composer />
    </aside>
  )
}
