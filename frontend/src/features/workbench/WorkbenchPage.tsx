/** 工作台页面 */

import { useEffect, useCallback, useState, useRef } from 'react'
import { Bot, Plus, Trash2, Loader2, Pencil, Search, X, PanelLeftClose, PanelLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import { useUIStore } from '@/stores/ui'
import { useWorkbenchStore } from './stores/workbench-store'
import { MessageList } from './components/MessageList'
import { ChatInput } from './components/ChatInput'
import { ModelSelector } from './components/ModelSelector'
import { ContextUsageBar } from './components/ContextUsageBar'
import { ApprovalDialog } from './components/ApprovalDialog'
import { BatchAnalysisDialog } from './components/BatchAnalysisDialog'
import { BatchProgressCard } from './components/BatchProgressCard'
import { deleteSession, updateSession } from './api'

export function WorkbenchPage() {
  const {
    sessions,
    currentSession,
    fetchSessions,
    createSession,
    setCurrentSession,
    fetchModels,
    pendingApproval,
    respondApproval,
    isStreaming,
    sendMessage,
    selectedModel,
    models,
    batchProgress,
    submitBatchAnalysis,
    cancelBatchAnalysis,
  } = useWorkbenchStore()

  const adminSidebarCollapsed = useUIStore((s) => s.sidebarCollapsed)
  const setAdminSidebarCollapsed = useUIStore((s) => s.setSidebarCollapsed)

  const [isCreating, setIsCreating] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try { return localStorage.getItem('workbench_sidebar_collapsed') === 'true' } catch { return false }
  })
  // 记录收起前的 admin 侧边栏状态，用于展开时恢复
  const prevAdminCollapsedRef = useRef(adminSidebarCollapsed)

  useEffect(() => {
    fetchSessions()
    fetchModels()
  }, [fetchSessions, fetchModels])

  const handleNewSession = useCallback(async () => {
    setIsCreating(true)
    try {
      await createSession()
    } finally {
      setIsCreating(false)
    }
  }, [createSession])

  const handleDeleteSession = useCallback(
    async (id: number) => {
      await deleteSession(id)
      if (currentSession?.id === id) {
        setCurrentSession(null)
      }
      fetchSessions()
    },
    [currentSession, setCurrentSession, fetchSessions],
  )

  const handleSend = useCallback(
    (content: string) => {
      if (!currentSession) return
      sendMessage(content)
    },
    [currentSession, sendMessage],
  )

  const handleTitleUpdate = useCallback(
    async (title: string) => {
      if (!currentSession) return
      await updateSession(currentSession.id, { title })
      fetchSessions()
    },
    [currentSession, fetchSessions],
  )

  const filteredSessions = searchQuery
    ? sessions.filter((s) => (s.title || '新会话').toLowerCase().includes(searchQuery.toLowerCase()))
    : sessions

  return (
    <div className="flex h-[calc(100vh-7rem)] overflow-hidden rounded-lg border bg-card">
      {/* 侧边栏：会话列表 */}
      <div
        className={cn(
          'flex flex-col overflow-hidden border-r bg-muted/30 transition-[width] duration-200',
          sidebarCollapsed ? 'w-[42px]' : 'w-[260px]',
        )}
      >
        <div className="flex h-10 shrink-0 items-center justify-between border-b px-2">
          {!sidebarCollapsed && <span className="text-sm font-medium pl-1">会话</span>}
          <div className="flex items-center gap-0.5">
            {!sidebarCollapsed && (
              <Button
                size="icon"
                variant="ghost"
                onClick={handleNewSession}
                disabled={isCreating}
                className="size-7"
              >
                {isCreating ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <Plus className="size-3.5" />
                )}
              </Button>
            )}
            <Button
              size="icon"
              variant="ghost"
              onClick={() => {
                setSidebarCollapsed((prev) => {
                  const next = !prev
                  try { localStorage.setItem('workbench_sidebar_collapsed', String(next)) } catch { /* ignore */ }
                  if (next) {
                    // 收起：记住当前 admin 侧边栏状态，然后一起收起
                    prevAdminCollapsedRef.current = adminSidebarCollapsed
                    if (!adminSidebarCollapsed) setAdminSidebarCollapsed(true)
                  } else {
                    // 展开：恢复之前的 admin 侧边栏状态
                    if (!prevAdminCollapsedRef.current) setAdminSidebarCollapsed(false)
                  }
                  return next
                })
              }}
              className="size-7"
            >
              {sidebarCollapsed ? (
                <PanelLeft className="size-3.5" />
              ) : (
                <PanelLeftClose className="size-3.5" />
              )}
            </Button>
          </div>
        </div>

        {!sidebarCollapsed && (
          <>
            {/* 搜索框 */}
            <div className="border-b px-2 py-1.5">
              <div className="relative">
                <Search className="absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="搜索会话..."
                  className="h-7 pl-7 pr-7 text-xs"
                />
                {searchQuery && (
                  <button
                    onClick={() => setSearchQuery('')}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    <X className="size-3" />
                  </button>
                )}
              </div>
            </div>

            <div className="flex-1 overflow-y-auto overflow-x-hidden">
              <div className="space-y-0.5 p-2">
                {filteredSessions.map((session) => (
                  <div
                    key={session.id}
                    onClick={() => setCurrentSession(session)}
                    className={cn(
                      'group flex items-center rounded-md px-2.5 py-2 text-sm cursor-pointer hover:bg-accent',
                      currentSession?.id === session.id && 'bg-accent',
                    )}
                  >
                    <span className="flex-1 min-w-0 truncate">{session.title || '新会话'}</span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        handleDeleteSession(session.id)
                      }}
                      className="shrink-0 ml-1 opacity-0 text-muted-foreground hover:text-destructive group-hover:opacity-100"
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  </div>
                ))}
                {filteredSessions.length === 0 && (
                  <div className="py-8 text-center text-xs text-muted-foreground">
                    {searchQuery ? '无匹配会话' : '暂无会话'}
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </div>

      {/* 主区域 */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* 顶部栏 */}
        <div className="flex h-10 shrink-0 items-center gap-4 border-b px-4">
          <div className="flex-1">
            <EditableTitle
              title={currentSession?.title || '工作台'}
              editable={!!currentSession}
              onSave={handleTitleUpdate}
            />
          </div>
          {currentSession && <ContextUsageBar />}
          {currentSession && (
            <BatchAnalysisDialog
              modelName={models.find((m) => m.id === selectedModel)?.name || selectedModel}
              onSubmit={submitBatchAnalysis}
              disabled={isStreaming}
            />
          )}
          <ModelSelector disabled={isStreaming} />
        </div>

        {/* 消息列表 */}
        {currentSession ? (
          <>
            <MessageList />

            {/* 批量分析进度 */}
            {batchProgress && (
              <div className="px-4 pb-2">
                <BatchProgressCard
                  job={batchProgress.job}
                  items={batchProgress.items}
                  onCancel={cancelBatchAnalysis}
                />
              </div>
            )}

            {/* 审批对话框 */}
            {pendingApproval && (
              <div className="px-4 pb-2">
                <ApprovalDialog
                  approval={pendingApproval}
                  onRespond={respondApproval}
                />
              </div>
            )}

            <ChatInput
              onSend={handleSend}
              disabled={!currentSession}
            />
          </>
        ) : (
          <div className="flex flex-1 items-center justify-center text-muted-foreground">
            <div className="text-center space-y-3">
              <Bot className="mx-auto size-12 text-muted-foreground/50" />
              <div>
                <p className="text-sm font-medium">欢迎使用工作台</p>
                <p className="text-xs mt-1">创建一个新会话开始对话</p>
              </div>
              <Button onClick={handleNewSession} disabled={isCreating}>
                {isCreating ? (
                  <Loader2 className="size-4 animate-spin mr-2" />
                ) : (
                  <Plus className="size-4 mr-2" />
                )}
                新建会话
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

/** 可编辑标题 */
function EditableTitle({
  title,
  editable,
  onSave,
}: {
  title: string
  editable: boolean
  onSave: (title: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(title)
  const inputRef = useRef<HTMLInputElement>(null)

  // Sync title when not editing
  useEffect(() => {
    if (!editing) setValue(title)
  }, [title, editing])

  useEffect(() => {
    if (editing) inputRef.current?.focus()
  }, [editing])

  const handleSave = () => {
    const trimmed = value.trim()
    if (trimmed && trimmed !== title) {
      onSave(trimmed)
    }
    setEditing(false)
  }

  if (!editable) {
    return <h2 className="text-sm font-medium">{title}</h2>
  }

  if (editing) {
    return (
      <Input
        ref={inputRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={handleSave}
        onKeyDown={(e) => {
          if (e.key === 'Enter') handleSave()
          if (e.key === 'Escape') { setValue(title); setEditing(false) }
        }}
        className="h-7 text-sm font-medium"
      />
    )
  }

  return (
    <div className="group flex items-center gap-1.5">
      <h2 className="text-sm font-medium truncate">{title}</h2>
      <button
        onClick={() => setEditing(true)}
        className="hidden text-muted-foreground hover:text-foreground group-hover:block"
      >
        <Pencil className="size-3" />
      </button>
    </div>
  )
}

export default WorkbenchPage
