/**
 * AI 助手独立页（/assistant 与 /assistant/:sessionId）：抽屉面板的全宽宿主。
 *
 * 为什么要它：抽屉宽 600~1200px，多 agent 并排（2~4 栏）时每栏只剩一百多像素，
 * 工具行也挤成两行。本页把宽度交还给屏幕——左侧会话列表（可折叠）+ 右侧对话区，
 * 窄屏列表收起、对话区独占全宽。
 *
 * 复用而不是重写：对话组件（MessageList / Composer / SessionSidebar）与全局 store
 * 原样使用，会话装配走 useActiveSession（与抽屉同一份，见该文件头）。本文件只管
 * 布局，不碰流式、会话与消息逻辑。
 *
 * 与抽屉共存：抽屉仍在壳层，两边共用 store —— 页面里切到的会话，回业务页按 ⌘J
 * 打开抽屉看到的就是同一个（反之亦然）。`/assistant` 上壳层不渲染抽屉：同一段
 * 对话在一屏出现两次、两个输入框谁都能发，用户不知道该跟哪个说（与复审页
 * 「两个 AI 助手并排」那条取舍同源，见 use-copilot-shell）。
 *
 * 布局也**不搬抽屉的约束**：没有 `--copilot-w`、没有 max-w-[600px]、不做 fixed
 * 定位与滚轮囚闭——本页在文档流里，滚动归自己。
 *
 * 会话在 URL 里（`/assistant/<sessionId>`，可复制 / 可刷新 / 可贴给别人）：双向
 * 同步全部在 useSessionRoute，本文件只负责调用它——抽屉没有 URL，所以那个 hook
 * 不能搬进 useActiveSession 让抽屉也吃一份。
 */

import { useRef, useState } from 'react'

import { useElementWidth } from '@/hooks/use-element-width'
import { useMediaQuery } from '@/hooks/use-media'

import { useActiveSession } from '../hooks/use-active-session'
import { useCopilotDrop } from '../hooks/use-copilot-drop'
import { useSessionRoute } from '../hooks/use-session-route'
import { readStoredRailOpen, storeRailOpen } from '../persistence'
import { useCopilot } from '../store'

import { Composer } from './Composer'
import { ROUTES } from '@/app/paths'
import { useLocation, useNavigate } from 'react-router'

import { CopilotHeader } from './CopilotHeader'
import { FileDropHint } from './FileDropHint'
import { FolderTreeDrawer } from './FolderTreeDrawer'
import { MessageList } from './MessageList'
import { SessionSidebar } from './SessionSidebar'
import { UiActionBanner } from './UiActionBanner'
import { UiToolHost } from './UiToolHost'

/** 并排的断点：低于此宽度会话列表让位（覆盖式），对话区独占全宽 */
const WIDE_QUERY = '(min-width: 768px)'

export function AssistantPage() {
  const context = useCopilot((s) => s.context)
  const exitContext = useCopilot((s) => s.exitContext)
  const switchSession = useCopilot((s) => s.switchSession)
  const draggingFiles = useCopilot((s) => s.draggingFiles)
  const { currentTitle, currentModel, currentAgentKind, currentCapabilities } = useActiveSession()
  // 会话进 URL（双向同步）。**必须排在 useActiveSession 之后**：挂载期它先
  // switchSession(store 里那个 id)，本 hook 的首帧 seed 随后用 URL 里的 id 覆盖——
  // 顺序反过来就变成「贴过来的链接被换成自己上次的会话」。
  useSessionRoute()
  const navigate = useNavigate()
  const location = useLocation()

  /**
   * 本页这次打开时站内有没有历史栈 —— **首帧就要记下来**。
   *
   * 直接打开 / 刷新时 `location.key === 'default'`（站内没有历史栈），此时
   * `navigate(-1)` 会把用户弹出应用，所以「退出全屏」要退回首页。不判这一下的话，
   * 用户刷新一次再点「退出全屏」就会掉到浏览器空白页。
   *
   * 为什么不能用 `location.key` 现算：会话进 URL 后本页首帧会把 `/assistant`
   * `replace` 成 `/assistant/<id>`，而 replace 会**换掉 location.key** —— 之后再读就
   * 不是 'default' 了，正是上面那个坑。存进 ref 则全程保持首帧的判断。
   */
  const openedDirectly = useRef(location.key === 'default')
  const exitFullscreen = () => {
    if (openedDirectly.current) void navigate(ROUTES.home)
    else void navigate(-1)
  }

  // 会话列表：宽屏常驻可折叠（偏好与抽屉共用一份），窄屏收成覆盖层
  const isWideUp = useMediaQuery(WIDE_QUERY)
  const [railOpen, setRailOpen] = useState(readStoredRailOpen)
  const [listOverlayOpen, setListOverlayOpen] = useState(false)
  const [treeDrawerOpen, setTreeDrawerOpen] = useState(false)
  // 正文净宽：会话栏可拖宽，上限按「净宽 - 对话区最小宽度」钳制（useRailResize）
  const [bodyRef, bodyWidth] = useElementWidth<HTMLDivElement>()
  const railVisible = railOpen && isWideUp

  const toggleList = () => {
    if (!isWideUp) {
      setListOverlayOpen((v) => !v)
      return
    }
    setRailOpen((v) => {
      storeRailOpen(!v)
      return !v
    })
  }

  // 页面级拖拽投放（双通道）：与抽屉共用 use-copilot-drop，拖进来的文件同样进上传流
  const drop = useCopilotDrop()

  return (
    <main
      className="app-page-enter relative flex h-[calc(100dvh-var(--app-navbar-h))] w-full flex-col overflow-hidden"
      aria-label="AI 助手"
      onDragEnter={drop.onDragEnter}
      onDragOver={drop.onDragOver}
      onDragLeave={drop.onDragLeave}
      onDrop={drop.onDrop}
    >
      {draggingFiles && <FileDropHint />}

      <CopilotHeader
        railVisible={railVisible}
        onToggleRail={toggleList}
        context={context}
        onExitContext={() => void exitContext()}
        treeDrawerOpen={treeDrawerOpen}
        onToggleTreeDrawer={() => setTreeDrawerOpen((v) => !v)}
        dockCapable={false}
        docked={false}
        currentTitle={currentTitle}
        currentModel={currentModel}
        currentAgentKind={currentAgentKind}
        onNewSession={() => {
          void switchSession(null)
          setListOverlayOpen(false)
        }}
        onExitFullscreen={exitFullscreen}
      />

      <div ref={bodyRef} className="relative flex min-h-0 flex-1">
        {railVisible && <SessionSidebar variant="rail" panelWidth={bodyWidth} />}
        {listOverlayOpen && <SessionSidebar variant="overlay" onClose={() => setListOverlayOpen(false)} />}
        {/* 对话区：min-w-0 + flex-1 —— 宽度全给消息与多栏并排，不设 max-w */}
        <div className="flex min-w-0 flex-1 flex-col">
          {/* 与面板同一套宿主端口（两处挂载由 releaseUiToolPorts 的归属校验防互清） */}
          <UiToolHost />
          <UiActionBanner />
          <MessageList wide />
          <Composer steerEnabled={currentCapabilities.steer !== false} />
        </div>
        {treeDrawerOpen && context?.origin === 'contract' && (
          <FolderTreeDrawer contractId={context.refId} onClose={() => setTreeDrawerOpen(false)} />
        )}
      </div>
    </main>
  )
}
