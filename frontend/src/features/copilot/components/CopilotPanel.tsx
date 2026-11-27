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
 *
 * 宽度是抽屉的固有约束（多 agent 并排时每栏放不下）：需要全宽时去独立页
 * `/assistant`（AssistantPage）——同一批对话组件、同一个 store，只换布局。
 * 会话装配（恢复会话/后端清单/待审/标题与能力）两处共用 useActiveSession。
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import { useMediaQuery } from '@/hooks/use-media'

import { useActiveSession } from '../hooks/use-active-session'
import { useCopilotDrop } from '../hooks/use-copilot-drop'
import { usePanelResize } from '../hooks/use-panel-resize'
import { readStoredRailOpen, storeRailOpen } from '../persistence'
import { useCopilot } from '../store'

import { Composer } from './Composer'
import { CopilotHeader } from './CopilotHeader'
import { FileDropHint } from './FileDropHint'
import { FolderTreeDrawer } from './FolderTreeDrawer'
import { MessageList } from './MessageList'
import { SessionSidebar } from './SessionSidebar'
import { UiActionBanner } from './UiActionBanner'
import { UiToolHost } from './UiToolHost'

export function CopilotPanel({
  open,
  onClose,
  dockCapable = false,
  docked = false,
  onDockToggle,
  onExpand,
}: {
  open: boolean
  onClose: () => void
  /** 宽屏（≥1280）才提供并排切换 */
  dockCapable?: boolean
  /** 当前是否处于并排模式（open && 偏好 && 宽屏） */
  docked?: boolean
  onDockToggle?: () => void
  /**
   * 跳到全屏助手页；由壳层注入（面板本身不依赖 router，否则单测渲染就要包
   * MemoryRouter，而这个组件对路由本无兴趣）。
   */
  onExpand?: () => void
}) {
  const context = useCopilot((s) => s.context)
  const switchSession = useCopilot((s) => s.switchSession)
  const exitContext = useCopilot((s) => s.exitContext)
  const { currentTitle, currentModel, currentAgentKind, currentCapabilities } = useActiveSession()
  // AI 操作页面的执行端口（导航 / toast / 跨域事件）+ 运行横幅。
  // 挂在这里而不是 AppShell：`useNavigate()` 只能从 Router 下的组件拿（main.tsx 是声明式
  // `<BrowserRouter>`，08 §4.1），而面板与助手页是仅有的两个 copilot 宿主。两处都挂时
  // 由 `setUiToolPorts` 做归属校验，先后卸载不会互相清空（见 store/ui-tools.ts）。
  // 端口注入拆成组件（{@link UiToolHost}）：面板不依赖 router，无 Router 时它渲染 null
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
  // 常驻会话栏开关（持久化，与独立页共用一份）；窄屏/收窄时的覆盖式列表开关（瞬态）
  const [railOpen, setRailOpen] = useState(readStoredRailOpen)
  const [listOverlayOpen, setListOverlayOpen] = useState(false)

  const railVisible = railOpen && railCapable
  const draggingFiles = useCopilot((s) => s.draggingFiles)
  const [treeDrawerOpen, setTreeDrawerOpen] = useState(false)
  // 面板级拖拽投放（双通道）：与详情页嵌入面板共用 use-copilot-drop
  const drop = useCopilotDrop()

  const toggleList = () => {
    if (railCapable) {
      setRailOpen((v) => {
        storeRailOpen(!v)
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
        onDragEnter={drop.onDragEnter}
        onDragOver={drop.onDragOver}
        onDragLeave={drop.onDragLeave}
        onDrop={drop.onDrop}
      >
        {draggingFiles && <FileDropHint />}
        {/* 拖拽把手：面板锚定右侧，向左拖变宽 */}
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="调整面板宽度"
          className="absolute top-0 bottom-0 left-0 z-30 hidden w-1.5 -translate-x-1/2 cursor-col-resize touch-none transition-colors hover:bg-foreground/25 sm:block"
          onPointerDown={onHandlePointerDown}
        />

        <CopilotHeader
          railVisible={railVisible}
          onToggleRail={toggleList}
          context={context}
          onExitContext={() => void exitContext()}
          treeDrawerOpen={treeDrawerOpen}
          onToggleTreeDrawer={() => setTreeDrawerOpen((v) => !v)}
          dockCapable={dockCapable}
          docked={docked}
          onDockToggle={onDockToggle}
          currentTitle={currentTitle}
          currentModel={currentModel}
          currentAgentKind={currentAgentKind}
          onNewSession={() => {
            void switchSession(null)
            setListOverlayOpen(false)
          }}
          onClose={onClose}
          onExpand={onExpand}
        />

        <div className="relative flex min-h-0 flex-1">
          {railVisible && <SessionSidebar variant="rail" panelWidth={width} />}
          {listOverlayOpen && (
            <SessionSidebar variant="overlay" onClose={() => setListOverlayOpen(false)} />
          )}
          {/* AI 操作页面的端口注入 + 运行横幅。端口注入做成组件是为了让面板在无 Router 的
              单测环境里也能渲染（面板本身不依赖 router，见 onExpand 注释）。 */}
          <UiToolHost />
          <UiActionBanner />
          <MessageList />
          {treeDrawerOpen && context?.origin === 'contract' && (
            <FolderTreeDrawer contractId={context.refId} onClose={() => setTreeDrawerOpen(false)} />
          )}
        </div>
        <Composer steerEnabled={currentCapabilities.steer !== false} />
    </aside>
  )
}
