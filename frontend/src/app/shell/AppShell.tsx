import { Suspense, useEffect, type CSSProperties } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router'
import { toast } from 'sonner'

import { AppNavbar } from '@/components/shared/AppNavbar'
import { PageErrorBoundary } from '@/components/shared/ErrorBoundary'
import { CopilotPanelLazy, preloadAllRoutes, preloadRoute, whenIdle } from '../preload'
import { assistant, assistantSession, isAssistantPath } from '../paths'
import { RouteFallback } from './route-fallback'
import { useCopilotShell } from './use-copilot-shell'

/**
 * 已登录区域的持久壳层：导航栏跨页面常驻，只有 <Outlet /> 里的内容区随路由换。
 *
 * 此前每个页面各自渲染一份 AppNavbar，且路由级 Suspense 的 fallback 是全屏
 * spinner——首次点开一个未缓存的标签，整页（含导航栏）先被替换成转圈，chunk
 * 到了再整页重挂，肉眼就是一次闪烁。现在：
 * - AppNavbar 在壳层，任何路由切换都不碰它；
 * - Suspense 边界常驻且已显示内容，react-router 把导航包在 startTransition 里，
 *   React 会保住旧页面直到新 chunk 可渲染，不再退回 fallback（fallback 只在
 *   壳层首次挂载、首个页面 chunk 还没到时出现一次）；
 * - PageErrorBoundary 以 pathname 作 resetKey 而非 key，健康页面不随 pathname
 *   重挂，/material-prep ↔ /material-prep/:id 保持同一个 DeskPage 实例。
 * 入场过渡由各页面自己的 <main className="app-page-enter"> 承担：换页=组件
 * 换类型=main 重挂=播一次；同页子路由=实例不变=不重播。
 *
 * 壳层是普通块级布局（不用 flex 列：flex item 上的 mx-auto 会让 main 收缩到
 * 内容宽度，max-w 失效）。需要撑满导航栏以下视口的页面（DeskPage 拖放）用
 * --app-navbar-h 自己算最小高度。
 *
 * AI 助手与 ⌘K 检索的全部开关状态在 useCopilotShell（与路由无关）；本文件只做
 * 布局装配。
 *
 * /assistant 及其会话子路径 /assistant/:sessionId（AI 助手独立页）例外：那一页
 * 自己就是全屏助手，本层不再叠抽屉，也不给内容区留并排 padding——见下面
 * copilotPanelVisible 的注释。
 */
export function AppShell() {
  // 登录后空闲时把三个主入口的 chunk 预载进来：切标签不再等下载。
  // 悬停预取（AppNavbar）兜住预载还没完成就点进来的情况。
  useEffect(() => whenIdle(preloadAllRoutes), [])

  // 页面感知兜底：路由一变就把页面描述写进 copilot store（通用助手注入
  // 「[当前页面：…]」锚点用）。详情页挂载后会写更精确的描述（实体名+id）
  // 覆盖；动态 import 保持 copilot 域的懒加载边界。
  const { pathname } = useLocation()
  const navigate = useNavigate()
  useEffect(() => {
    let cancelled = false
    void Promise.all([import('@/features/copilot/store'), import('@/features/copilot/domain')]).then(
      ([storeMod, domainMod]) => {
        if (!cancelled) storeMod.useCopilot.getState().setPageHint(domainMod.describeLocation(pathname))
      },
    )
    return () => {
      cancelled = true
    }
  }, [pathname])

  const {
    copilotOpen,
    copilotMounted,
    effectiveDocked,
    isXlUp,
    toggleCopilot,
    toggleCopilotDock,
    searchOpen,
    setSearchOpen,
  } = useCopilotShell()

  // AI 助手独立页（/assistant 与 /assistant/:sessionId）自己就是全屏助手：壳层不再
  // 叠一层抽屉——同一段对话出现两个输入框，用户不知道该跟哪个说（与复审页「两个
  // AI 助手并排」同一取舍，见 use-copilot-shell）。抽屉的开关状态原样保留，离开本页
  // 即恢复；并排 padding 同理要停，否则页面会被一个看不见的面板让出一截。
  //
  // 判据必须走 isAssistantPath（含子路径）：会话进 URL 后写回 `=== ROUTES.assistant`
  // 的精确等号，`/assistant/<id>` 就会重新叠出抽屉。
  const onAssistantPage = isAssistantPath(pathname)
  const copilotPanelVisible = copilotMounted && !onAssistantPage
  const contentDocked = effectiveDocked && !onAssistantPage

  return (
    <div className="min-h-screen bg-background">
      <AppNavbar
        onNotify={(msg) => toast.info(msg)}
        onPrefetch={preloadRoute}
        onToggleCopilot={toggleCopilot}
        searchOpen={searchOpen}
        onSearchOpenChange={setSearchOpen}
      />
      {/*
        AI 助手没有压暗遮罩（故此处不渲染 PanelBackdrop）：它是常驻侧边栏，
        不是模态对话框。遮罩只会造成两个问题——点页面任何地方（包括右栏的
        合同文件）先命中遮罩、触发 onClose 把刚打开的助手收回去；律师也看不到
        被遮的合同内容，而那恰好是他要对照着改的对象。收起走面板自己的关闭
        按钮与 ⌘J。曾经用「dock 或详情页豁免」去猜哪些页面不需要遮，但答案是
        全都不需要。
      */}
      {copilotPanelVisible && (
        <Suspense fallback={null}>
          <CopilotPanelLazy
            open={copilotOpen}
            onClose={toggleCopilot}
            dockCapable={isXlUp}
            docked={effectiveDocked}
            onDockToggle={toggleCopilotDock}
            onExpand={() => {
              // 先收抽屉再跳页：留着抽屉会让独立页叠在一起（同一段对话两个输入框）。
              toggleCopilot()
              // 带着**当前会话**跳（会话进 URL）：到独立页看到的还是同一段对话，刷新、
              // 复制链接、贴给别人都是它。没有会话才落 `assistant()` 新对话。
              // store 走动态 import：本文件在首屏包里，静态引入 copilot 域会把 markdown /
              // 语法高亮一起拖进来（见 ../preload 为何 AssistantPageLazy 不进预载）。
              void import('@/features/copilot/store').then(({ useCopilot }) => {
                const sessionId = useCopilot.getState().sessionId
                void navigate(sessionId ? assistantSession(sessionId) : assistant())
              })
            }}
          />
        </Suspense>
      )}
      <div
        className="transition-[padding-right] duration-200"
        style={
          contentDocked
            ? ({
                paddingRight: 'var(--copilot-w-app, 0px)',
                // 并排让位的净宽对 fixed 定位的全屏层（材料预处理阅读器）同样生效：
                // 它们不吃父级 padding，只能用 CSS 变量把自己的右缘收进来。
                '--copilot-docked-w': 'var(--copilot-w-app, 0px)',
              } as CSSProperties)
            : undefined
        }
      >
        <PageErrorBoundary>
          <Suspense fallback={<RouteFallback />}>
            <Outlet />
          </Suspense>
        </PageErrorBoundary>
      </div>
    </div>
  )
}
