/**
 * Copilot 右侧常驻面板：导航栏图标唤起，AppShell 懒加载挂载。
 *
 * 布局：宽度可拖拽调整（左缘把手，`--copilot-w` 变量驱动，松手持久化）；
 * 宽度 ≥560px 时左侧 180px 会话栏常驻（双栏），收窄或窄屏用覆盖式列表。
 * 非模态 dock：z-[100] 高于页面与全屏阅读器（z-[80]），低于菜单类
 * portal（z-[120]）与弹窗基线（z-[130]）。路由切换不影响本面板（挂在
 * 壳层），流式收发归 store，收起面板流不断；开/收带滑入滑出动画。
 * 背景由 PanelBackdrop 压暗一档拉开主次层次（任何视口都生效）。遮罩的
 * 生命周期跟 copilotMounted 走（AppShell 负责），不随面板一同卸载，
 * 收起时才能和滑出动画同步淡出。
 *
 * 并排模式（宽屏，AppShell 传入 dockCapable/docked）：遮罩关闭，主内容
 * 区让出等宽 padding，本面板与页面同屏对照；切换按钮在 header 右侧。
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Columns2, FolderTree, PanelLeftClose, PanelLeftOpen, Paperclip, Plus, SquareStack, X } from 'lucide-react'

import { listSessions } from '../api'
import { COPILOT_LAUNCH_EVENT, takePendingLaunchContext, type CopilotLaunchContext } from '../launch'
import { usePanelResize } from '../hooks/use-panel-resize'
import { useCopilot } from '../store'
import { FOLDER_REF_MIME, type FolderRefDraft } from '../types'
import { Composer } from './Composer'
import { FolderTreeDrawer } from './FolderTreeDrawer'
import { MessageList } from './MessageList'
import { SessionSidebar } from './SessionSidebar'
import { useMediaQuery } from '@/hooks/use-media'

const RAIL_KEY = 'copilot:rail'

function readRailOpen(): boolean {
  try {
    return localStorage.getItem(RAIL_KEY) !== '0'
  } catch {
    return true
  }
}

export function CopilotPanel({
  open,
  onClose,
  dockCapable = false,
  docked = false,
  onDockToggle,
}: {
  open: boolean
  onClose: () => void
  /** 宽屏（≥1280）才提供并排切换 */
  dockCapable?: boolean
  /** 当前是否处于并排模式（open && 偏好 && 宽屏） */
  docked?: boolean
  onDockToggle?: () => void
}) {
  const sessionId = useCopilot((s) => s.sessionId)
  const streaming = useCopilot((s) => s.streaming)
  const context = useCopilot((s) => s.context)
  const switchSession = useCopilot((s) => s.switchSession)
  const enterContext = useCopilot((s) => s.enterContext)
  const exitContext = useCopilot((s) => s.exitContext)
  const loadPendingApprovals = useCopilot((s) => s.loadPendingApprovals)
  const refreshHistory = useCopilot((s) => s.refreshHistory)
  const queryClient = useQueryClient()
  const isSmUp = useMediaQuery('(min-width: 640px)')
  const { width, railCapable, setPanelRef, onHandlePointerDown } = usePanelResize(isSmUp)

  // 滚轮囚闭：面板是 fixed 浮层，wheel 事件在非滚动区（头部/输入框）或滚动区
  // 到边界时会「链」到下层页面。React 的 onWheel 是 passive 监听无法 preventDefault，
  // 必须原生 non-passive 监听：从 target 向上找面板内能消费该滚动的容器
  //（消息区/会话列表/工具详情嵌套），能滚则放行、到边界则继续向外层、
  // 面板内无人能消费则阻断——主页面内容不再被带动。
  const panelRef = useRef<HTMLElement | null>(null)
  const setRefs = useCallback(
    (node: HTMLElement | null) => {
      panelRef.current = node
      setPanelRef(node)
    },
    [setPanelRef],
  )
  useEffect(() => {
    const el = panelRef.current
    if (!el) return
    const canScroll = (node: HTMLElement, deltaY: number): boolean => {
      const overflowY = window.getComputedStyle(node).overflowY
      if (!['auto', 'scroll', 'overlay'].includes(overflowY)) return false
      const { scrollTop, scrollHeight, clientHeight } = node
      // 内容不超出时任何方向都消费不了
      if (scrollHeight <= clientHeight + 1) return false
      if (deltaY < 0) return scrollTop > 0
      return scrollTop + clientHeight < scrollHeight - 1
    }
    const onWheel = (e: WheelEvent) => {
      // ctrl+wheel 是浏览器缩放，不接管
      if (e.ctrlKey || e.defaultPrevented) return
      let node = e.target as HTMLElement | null
      while (node && node !== el) {
        if (canScroll(node, e.deltaY)) return
        node = node.parentElement
      }
      e.preventDefault()
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [])
  // 常驻会话栏开关（持久化）；窄屏/收窄时的覆盖式列表开关（瞬态）
  const [railOpen, setRailOpen] = useState(readRailOpen)
  const [listOverlayOpen, setListOverlayOpen] = useState(false)

  // 恢复上次会话的历史（StrictMode 双挂载幂等：同 id 重拉无害）
  useEffect(() => {
    void switchSession(sessionId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 业务页打开入口（案件/合同页的「AI 助手」按钮）：
  // ①面板尚未挂载时 chunk 加载完从这里取走 pending；②已打开时监听后续事件切上下文
  useEffect(() => {
    const pending = takePendingLaunchContext()
    if (pending) void enterContext(pending)
    const onLaunch = (e: Event) => {
      const detail = (e as CustomEvent<CopilotLaunchContext | null>).detail
      if (detail) void enterContext(detail)
    }
    window.addEventListener(COPILOT_LAUNCH_EVENT, onLaunch)
    return () => window.removeEventListener(COPILOT_LAUNCH_EVENT, onLaunch)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 离线审批入口：面板打开、每轮流结束、切会话后拉一次待审列表。
 // 后台任务挂起的高危工具调用由此浮出水面，而不是默默超时。
  useEffect(() => {
    if (!streaming) void loadPendingApprovals()
  }, [streaming, sessionId, loadPendingApprovals])

  // 面板标题取当前会话标题：会话列表缓存里查（缓存由侧栏/流结束刷新）
  // 会话列表按业务范围取：context（案件/合同页打开）时只列该范围的会话；
  // scopeKey 进 queryKey 保证两套列表缓存互不串
  const scopeKey = context ? `${context.origin}:${context.refId}` : 'all'
  const scope = context ? { origin: context.origin, refId: context.refId } : undefined
  const sessionsQuery = useQuery({
    queryKey: ['copilot', 'sessions', scopeKey],
    queryFn: () => listSessions(50, scope),
    enabled: Boolean(sessionId) || Boolean(context),
    staleTime: 30_000,
    retry: false,
  })
  const currentSession = sessionId ? sessionsQuery.data?.find((s) => s.session_id === sessionId) : undefined
  const currentTitle = currentSession?.title ?? ''
  const currentModel = currentSession?.llm_model ?? ''

  // 每轮流结束后刷新会话列表：首条消息会自动生成标题，标题要能浮上来
  useEffect(() => {
    if (!streaming && (sessionId || context)) {
      void queryClient.invalidateQueries({ queryKey: ['copilot', 'sessions'] })
    }
  }, [streaming, sessionId, context, queryClient])

  // 后台任务跑完（updated_at 变化）自动重拉转录：任务的通知消息/产出
  // 不在面板的流式路径里，只能靠轮询发现的 updated_at 变化来刷新。
  // 对话式会话不走这里（store 已实时追加，重拉只会浪费一次请求）。
  const prevTaskUpdatedRef = useRef('')
  useEffect(() => {
    if (currentSession?.origin !== 'task') return
    const updatedAt = currentSession.updated_at
    if (!updatedAt || updatedAt === prevTaskUpdatedRef.current) return
    const isFirst = prevTaskUpdatedRef.current === ''
    prevTaskUpdatedRef.current = updatedAt
    if (!isFirst && !streaming) void refreshHistory()
  }, [currentSession, streaming, refreshHistory])

  const railVisible = railOpen && railCapable
  const draggingFiles = useCopilot((s) => s.draggingFiles)
  const addAttachmentFiles = useCopilot((s) => s.addAttachmentFiles)
  const addFolderRef = useCopilot((s) => s.addFolderRef)
  const [treeDrawerOpen, setTreeDrawerOpen] = useState(false)
  // 面板级拖拽投放：拖入高亮 + 松手收件。dragenter/over 必须 preventDefault
  // 才能触发 drop；计数器法处理子元素间的 enter/leave 抖动。
  // 流式/上传在途不加附件（与回形针按钮同口径）。
  const filesDropAllowed = () => {
    const { streaming, uploadingAttachments } = useCopilot.getState()
    return !(streaming || uploadingAttachments)
  }
  const dragDepth = useRef(0)
  const onDragEnter = (e: React.DragEvent) => {
    if (!e.dataTransfer?.types?.includes('Files')) return
    e.preventDefault()
    if (!filesDropAllowed()) return
    dragDepth.current += 1
    if (!useCopilot.getState().draggingFiles) useCopilot.setState({ draggingFiles: true })
  }
  const onDragOver = (e: React.DragEvent) => {
    if (!e.dataTransfer?.types?.includes('Files')) return
    e.preventDefault()
  }
  const onDragLeave = (e: React.DragEvent) => {
    if (!e.dataTransfer?.types?.includes('Files')) return
    e.preventDefault()
    dragDepth.current = Math.max(0, dragDepth.current - 1)
    if (dragDepth.current === 0) useCopilot.setState({ draggingFiles: false })
  }
  const onDrop = (e: React.DragEvent) => {
    // 无条件 preventDefault + 复位：拖文件夹（files 为空列表）或非文件投放，
    // 既不能让浏览器直接打开被拖入的文件，也不能让高亮层残留
    e.preventDefault()
    dragDepth.current = 0
    useCopilot.setState({ draggingFiles: false })
    // 内部拖拽（目录树 → 输入区）：自定义 MIME 携带引用，优先于 Files 通道
    const raw = e.dataTransfer.getData(FOLDER_REF_MIME)
    if (raw) {
      if (!filesDropAllowed()) return
      try {
        const draft = JSON.parse(raw) as FolderRefDraft
        if (typeof draft.contractId === 'number' && typeof draft.subpath === 'string' && draft.subpath) {
          addFolderRef({ contractId: draft.contractId, subpath: draft.subpath, name: String(draft.name ?? '') })
        }
      } catch {
        // 非法 JSON 静默丢弃：不当作文件处理，也不打断 drop
      }
      return
    }
    if (!e.dataTransfer?.files?.length || !filesDropAllowed()) return
    addAttachmentFiles(e.dataTransfer.files)
  }

  const toggleList = () => {
    if (railCapable) {
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
      ref={setRefs}
        style={{ '--copilot-w': `${width}px` } as React.CSSProperties}
        className={`fixed top-(--app-navbar-h) right-0 bottom-0 z-[100] flex w-full flex-col border-l border-border bg-card shadow-[-8px_0_24px_rgba(0,0,0,0.06)] duration-200 fill-mode-both transition-none sm:w-(--copilot-w) ${
          open ? 'animate-in slide-in-from-right' : 'animate-out slide-out-to-right'
        }`}
        aria-label="AI 助手"
        onDragEnter={onDragEnter}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
      >
        {draggingFiles && (
          <div className="pointer-events-none absolute inset-0 z-40 flex items-center justify-center bg-background/70 backdrop-blur-[1px]">
            <div className="flex flex-col items-center gap-2 rounded-[14px] border-2 border-dashed border-primary/60 bg-card px-8 py-6 text-center shadow-lg">
              <Paperclip className="h-6 w-6 text-primary" />
              <p className="text-[14px] font-semibold text-foreground">松手添加附件</p>
              <p className="text-[12px] leading-relaxed text-muted-foreground">
                PDF / Word / 图片（PNG·JPG·TIFF）/ TXT · 单个 ≤ 20MB
                <br />
                附件随下一条消息一起发送，AI 会自动读取内容
              </p>
            </div>
          </div>
        )}
        {/* 拖拽把手：面板锚定右侧，向左拖变宽 */}
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="调整面板宽度"
          className="absolute top-0 bottom-0 left-0 z-30 hidden w-1.5 -translate-x-1/2 cursor-col-resize touch-none transition-colors hover:bg-foreground/25 sm:block"
          onPointerDown={onHandlePointerDown}
        />

        <header className="flex h-12 flex-none items-center gap-1.5 border-b border-border px-2.5">
          <button
            type="button"
            className="flex h-7 w-7 flex-none items-center justify-center rounded-[8px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            onClick={toggleList}
            aria-label={railVisible ? '收起会话栏' : '展开会话列表'}
            title={railVisible ? '收起会话栏' : '展开会话列表'}
          >
            {railVisible ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeftOpen className="h-4 w-4" />}
          </button>
          <span className="min-w-0 flex-1 truncate px-0.5 text-[13px] font-semibold text-foreground">
            {context ? `AI 助手 · ${context.title}` : currentTitle || 'AI 助手'}
          </span>
          {context && (
            <button
              type="button"
              className="flex h-7 max-w-40 flex-none items-center gap-1 rounded-[8px] bg-secondary px-2 text-[11.5px] text-muted-foreground transition-colors hover:text-foreground"
              onClick={() => void exitContext()}
              aria-label="退出业务范围，回到全部会话"
              title={`当前只看「${context.title}」的会话，点击回到全部`}
            >
              <SquareStack className="h-3 w-3 flex-none" />
              <span className="truncate">{context.origin === 'case' ? '本案' : '本委托'}</span>
              <X className="h-3 w-3 flex-none" />
            </button>
          )}
          {context?.origin === 'contract' && (
            <button
              type="button"
              className={`flex h-7 flex-none items-center gap-1 rounded-[8px] px-2 text-[12px] transition-colors hover:bg-secondary hover:text-foreground ${
                treeDrawerOpen ? 'bg-secondary text-foreground' : 'text-muted-foreground'
              }`}
              onClick={() => setTreeDrawerOpen((v) => !v)}
              aria-label={treeDrawerOpen ? '收起合同材料目录' : '展开合同材料目录'}
              aria-pressed={treeDrawerOpen}
              title="合同绑定文件夹目录树：把文件拖到输入区即可引用"
            >
              <FolderTree className="h-3.5 w-3.5" />
              材料
            </button>
          )}
          {dockCapable && onDockToggle && (
            <button
              type="button"
              className={`flex h-7 w-7 flex-none items-center justify-center rounded-[8px] transition-colors hover:bg-secondary hover:text-foreground ${
                docked ? 'bg-secondary text-foreground' : 'text-muted-foreground'
              }`}
              onClick={onDockToggle}
              aria-pressed={docked}
              aria-label={docked ? '切换为悬浮模式' : '切换为并排模式'}
              title={
                docked
                  ? '并排模式中：页面内容让位同屏显示，点击切回悬浮覆盖'
                  : '并排模式：页面内容自动让位，可与合同详情页并排对照'
              }
            >
              <Columns2 className="h-4 w-4" />
            </button>
          )}
          {currentModel && (
            <span
              className="hidden max-w-28 flex-none truncate rounded-[6px] bg-secondary px-1.5 py-0.5 text-[10.5px] text-muted-foreground sm:block"
              title={`当前模型：${currentModel}`}
            >
              {currentModel}
            </span>
          )}
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
          {railVisible && <SessionSidebar variant="rail" />}
          {listOverlayOpen && (
            <SessionSidebar variant="overlay" onClose={() => setListOverlayOpen(false)} />
          )}
          <MessageList />
          {treeDrawerOpen && context?.origin === 'contract' && (
            <FolderTreeDrawer contractId={context.refId} onClose={() => setTreeDrawerOpen(false)} />
          )}
        </div>
        <Composer />
    </aside>
  )
}
