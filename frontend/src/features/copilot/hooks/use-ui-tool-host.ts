/**
 * 把 React 世界的导航 / 提示能力注入界面动作执行器（端口注入点）。
 *
 * ## 为什么必须在组件里做
 *
 * `main.tsx:49` 是声明式 `<BrowserRouter>`，**React 之外拿不到 router 实例**
 * （08 §4.1）：store 里的执行器是纯函数（无 React），它要跳页只能拿到一个函数。
 * 所以只能在挂载于 Router 内部的组件里 `useNavigate()` 捕获一次，再交给 store 的
 * 模块级端口槽（`setUiToolPorts`）。
 *
 * 挂载点：`CopilotPanel` 与 `AssistantPage`（两者已共用 `useActiveSession`，同一处
 * 装配）。面板收起时不必撤销端口——`navigate` 在 Router 生命周期内始终有效，卸载
 * 才传 null。
 *
 * ## 为什么 toast 直接用 sonner 的函数
 *
 * 本仓的全局提示没有 Provider 里的 hook（`main.tsx` 直接 `import { toast } from
 * 'sonner'`），再包一层 hook 只是多一次订阅。
 *
 * ## dispatch 为什么走 window
 *
 * 需要别的 feature「做点什么」时不能 import 它（跨 feature 边界），`window` 自定义
 * 事件是既定模式（`launch.ts` 同款）。
 */

import { useEffect } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'

import { openCopilot } from '../launch'
import { releaseUiToolPorts, setUiToolPorts } from '../store/ui-tools'
import type { UiToolPorts } from '../ui-tools'

export function useUiToolHost(): void {
  const navigate = useNavigate()

  useEffect(() => {
    const ports: UiToolPorts = {
      // react-router v8 的 navigate 返回 Promise（数据路由的就绪信号）：端口签名是
      // void，这里显式丢弃，不让一个 pending promise 随着动作记录一起漏出去。
      navigate: (to, opts) => {
        void navigate(to, opts)
      },
      // 当前地址从 window 读而不是 useLocation()：端口的调用方是毫秒级的执行器，
      // 拿「此刻浏览器里的真实地址」比拿某次渲染的快照更准（执行器常在两帧之间跑）。
      currentPath: () => window.location.pathname + window.location.search,
      toast: (message) => {
        toast(message)
      },
      dispatch: (event, detail) => {
        window.dispatchEvent(new CustomEvent(event, { detail }))
      },
      openCopilot: (ctx) => {
        openCopilot(ctx)
      },
    }
    setUiToolPorts(ports)
    // 卸载时按归属撤销（不是无条件置空）：宿主有两处（面板 / 助手页），无条件清会把
    // 另一处刚注入的端口干掉；同时避免把 navigate 调到已卸载的路由器上（静默无效）。
    return () => releaseUiToolPorts(ports)
  }, [navigate])
}
