/** 工作台页面 */

import { useEffect, useCallback, useState, useRef } from 'react'
import { useParams, useNavigate } from 'react-router'
import { Bot, Plus, Trash2, Loader2, Pencil, Search, X, PanelLeftClose, PanelLeft, Menu, History, Download, AlertTriangle } from 'lucide-react'
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
import { BatchHistoryPanel } from './components/BatchHistoryPanel'
import { SuggestedPrompts } from './components/SuggestedPrompts'
import { WorkbenchCommandPalette } from './components/WorkbenchCommandPalette'
import { useContextUsage } from './hooks/use-context-usage'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet'
import { deleteSession, updateSession } from './api'
import { exportToMarkdown, downloadFile } from './utils/export'
import { toast } from 'sonner'
import { generatePath } from '@/routes/paths'

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
    messages,
    messagesLoading,
    abortStream,
  } = useWorkbenchStore()

  const { percent: contextPercent } = useContextUsage()

  const { sessionId } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()
  const adminSidebarCollapsed = useUIStore((s) => s.sidebarCollapsed)
  const setAdminSidebarCollapsed = useUIStore((s) => s.setSidebarCollapsed)

  const [isCreating, setIsCreating] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [commandOpen, setCommandOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [isMobile, setIsMobile] = useState(() => window.innerWidth < 768)
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try { return localStorage.getItem('workbench_sidebar_collapsed') === 'true' } catch { return false }
  })
  // 记录收起前的 admin 侧边栏状态，用于展开时恢复
  const prevAdminCollapsedRef = useRef(adminSidebarCollapsed)

  // 监听视口宽度
  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth < 768)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  useEffect(() => {
    fetchSessions()
    fetchModels()
  }, [fetchSessions, fetchModels])

  // URL 中的 sessionId 与会话列表同步
  useEffect(() => {
    if (!sessions.length) return
    if (sessionId) {
      const target = sessions.find((s) => s.session_id === sessionId)
      if (target && target.id !== currentSession?.id) {
        setCurrentSession(target)
      }
    } else if (currentSession) {
      // URL 无 sessionId 但有选中会话，清除选中
      setCurrentSession(null)
    }
  }, [sessionId, sessions]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleNewSession = useCallback(async () => {
    setIsCreating(true)
    try {
      const session = await createSession()
      navigate(generatePath.workbenchSession(session.session_id))
    } finally {
      setIsCreating(false)
    }
  }, [createSession, navigate])

  // 全局快捷键
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey
      if (mod && e.shiftKey && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setCommandOpen((prev) => !prev)
      }
      if (mod && e.key === '.') {
        e.preventDefault()
        if (isStreaming) abortStream()
      }
      if (mod && e.key === 'n') {
        e.preventDefault()
        handleNewSession()
      }
      if (mod && e.key === 'e') {
        e.preventDefault()
        if (currentSession && messages.length > 0) {
          const md = exportToMarkdown(messages, currentSession.title || '对话')
          downloadFile(md, `${currentSession.title || '对话'}.md`, 'text/markdown;charset=utf-8')
          toast.success('已导出 Markdown')
        }
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [isStreaming, abortStream, currentSession, messages, handleNewSession])

  const handleDeleteSession = useCallback(
    async (id: number) => {
      await deleteSession(id)
      if (currentSession?.id === id) {
        navigate('/admin/workbench')
      }
      fetchSessions()
    },
    [currentSession, navigate, fetchSessions],
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

  const sidebarContent = (
    <>
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
            {!isMobile && (
              <Button
                size="icon"
                variant="ghost"
                onClick={() => {
                  setSidebarCollapsed((prev) => {
                    const next = !prev
                    try { localStorage.setItem('workbench_sidebar_collapsed', String(next)) } catch { /* ignore */ }
                    if (next) {
                      prevAdminCollapsedRef.current = adminSidebarCollapsed
                      if (!adminSidebarCollapsed) setAdminSidebarCollapsed(true)
                    } else {
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
            )}
            {isMobile && (
              <Button
                size="icon"
                variant="ghost"
                onClick={() => setMobileSidebarOpen(false)}
                className="size-7"
              >
                <X className="size-3.5" />
              </Button>
            )}
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
                    onClick={() => navigate(generatePath.workbenchSession(session.session_id))}
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
    </>
  )

  return (
    <div className="flex h-[calc(100vh-7rem)] overflow-hidden rounded-lg border bg-card">
      {/* 移动端抽屉遮罩 */}
      {isMobile && mobileSidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50"
          onClick={() => setMobileSidebarOpen(false)}
        />
      )}

      {/* 侧边栏：会话列表 */}
      {isMobile ? (
        /* 移动端抽屉 */
        mobileSidebarOpen && (
          <div className="fixed inset-y-0 left-0 z-50 flex w-[260px] flex-col border-r bg-card shadow-lg">
            {sidebarContent}
          </div>
        )
      ) : (
        /* 桌端侧边栏 */
        <div
          className={cn(
            'flex flex-col overflow-hidden border-r bg-muted/30 transition-[width] duration-200',
            sidebarCollapsed ? 'w-[42px]' : 'w-[260px]',
          )}
        >
          {sidebarContent}
        </div>
      )}
      {/* 主区域 */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* 顶部栏 */}
        <div className="flex h-10 shrink-0 items-center gap-2 md:gap-4 border-b px-3 md:px-4">
          {isMobile && (
            <Button
              size="icon"
              variant="ghost"
              onClick={() => setMobileSidebarOpen(true)}
              className="size-7 shrink-0"
            >
              <Menu className="size-4" />
            </Button>
          )}
          <div className="flex-1 min-w-0">
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
          {currentSession && (
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setHistoryOpen(true)}
              className="size-7"
              title="批量分析历史"
            >
              <History className="size-3.5" />
            </Button>
          )}
          {currentSession && messages.length > 0 && (
            <Button
              variant="ghost"
              size="icon"
              onClick={() => {
                const md = exportToMarkdown(messages, currentSession.title || '对话')
                downloadFile(md, `${currentSession.title || '对话'}.md`, 'text/markdown;charset=utf-8')
                toast.success('已导出 Markdown')
              }}
              className="size-7"
              title="导出对话"
            >
              <Download className="size-3.5" />
            </Button>
          )}
          <ModelSelector disabled={isStreaming} />
        </div>

        {/* 消息列表 */}
        {currentSession ? (
          <>
            <MessageList />

            {/* 空状态建议提示 */}
            {messages.length === 0 && !messagesLoading && !isStreaming && (
              <SuggestedPrompts onSelect={handleSend} />
            )}

            {/* 批量分析进度 */}
            {batchProgress && (
              <div className="px-4 pb-2">
                <BatchProgressCard
                  job={batchProgress.job}
                  items={batchProgress.items}
                  onCancel={cancelBatchAnalysis}
                  failedItemsDetail={batchProgress.failed_items_detail}
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

            {/* 上下文窗口溢出警告 */}
            {contextPercent >= 90 && (
              <div className="mx-4 mb-2 flex items-center gap-2 rounded-md bg-yellow-500/10 border border-yellow-500/20 px-3 py-2 text-xs text-yellow-700 dark:text-yellow-400">
                <AlertTriangle className="size-3.5 shrink-0" />
                <span>上下文窗口已使用 {contextPercent}%，建议新建会话以获得更好的回复质量</span>
                <Button size="sm" variant="outline" onClick={handleNewSession} className="ml-auto text-xs h-6">
                  新建会话
                </Button>
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

      {/* 批量分析历史侧边面板 */}
      {currentSession && (
        <Sheet open={historyOpen} onOpenChange={setHistoryOpen}>
          <SheetContent className="w-[360px] sm:w-[400px]">
            <SheetHeader>
              <SheetTitle>批量分析历史</SheetTitle>
              <SheetDescription>查看当前会话的批量分析任务记录</SheetDescription>
            </SheetHeader>
            <div className="mt-4 overflow-y-auto max-h-[calc(100vh-8rem)]">
              <BatchHistoryPanel sessionId={currentSession.id} />
            </div>
          </SheetContent>
        </Sheet>
      )}

      {/* 命令面板 */}
      <WorkbenchCommandPalette
        open={commandOpen}
        onOpenChange={setCommandOpen}
        onNewSession={() => {
          setCommandOpen(false)
          handleNewSession()
        }}
      />
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
