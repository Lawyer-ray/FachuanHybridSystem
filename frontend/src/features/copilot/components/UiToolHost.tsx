/**
 * 端口注入组件：`useUiToolHost()` 的「有路由才装」外壳。
 *
 * ## 为什么需要这一层，而不是让宿主直接调 hook
 *
 * `useUiToolHost()` 内部必须 `useNavigate()`，而 React 的规则不允许「先判断再调 hook」。
 * 但 `CopilotPanel` 有一条刻意的架构约束（见其 `onExpand` 注释）：**面板本身不依赖
 * router**，单测渲染不该被迫包 `MemoryRouter`。
 *
 * 拆成组件后两件事同时成立：
 * - 在 Router 下（生产：`AppShell` 里的面板、`/assistant` 页）→ 注入端口，AI 能操作页面；
 * - 不在 Router 下（面板的单测、Storybook 之类）→ 渲染 null，不抛 `useNavigate() may be
 *   used only in the context of a <Router>`，也不影响面板原有断言。
 *
 * 用 `useInRouterContext()` 而不是 try/catch：React 里捕获渲染期异常会把整棵子树卸载，
 * 面板会凭空消失；这里的「没有路由」是**正常态**，不是错误。
 *
 * 挂载两处（面板 / 助手页）是必须的：`/assistant` 与抽屉是两个宿主，律师可能直接打开其中
 * 任意一个。两处同时挂载由 `releaseUiToolPorts()` 的归属校验兜住，先后卸载不会互相清空。
 */

import { useInRouterContext } from 'react-router'

import { useUiToolHost } from '../hooks/use-ui-tool-host'

/** 真正注入端口的空组件（只可能渲染在 Router 下） */
function UiToolHostInner() {
  useUiToolHost()
  return null
}

export function UiToolHost() {
  const inRouter = useInRouterContext()
  return inRouter ? <UiToolHostInner /> : null
}
