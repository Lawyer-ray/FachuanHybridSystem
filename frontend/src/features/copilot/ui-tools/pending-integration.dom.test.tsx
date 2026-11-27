// @vitest-environment jsdom
/**
 * 跨页续跑的**集成**证明：`runUiTool` 发现路径不对 → 入队 + 导航 → 目标页挂载 →
 * `useUiPendingAction` 取走 → 页面执行器真的跑。
 *
 * 为什么需要这一条：`pending.node.test.ts`（纯逻辑）与 `use-ui-pending-action.dom.test.tsx`
 * （hook 单测）各自都绿，但两段之间「键是 `spec.route`、页面用同一 route 取」这个约定
 * 没有任何一条测试同时盯着。约定断掉的表现是「AI 说已打开并继续执行，页面毫无反应」，
 * 没有任何报错——所以这里把整条链路串起来跑真实现，只把浏览器端口换成 spy
 * （navigate / currentPath）。页面执行器也是 spy：它被调用几次、参数是不是原对象，
 * 正是要钉死的东西。
 *
 * 三个场景对应三种真实结局：
 * A. 正常续跑（当前在别的页）：先排队 + 跳，页面挂载后才执行，且只执行一次；
 * B. 已经在目标页（含 query）：直接执行，不排队、不多跳；
 * C. 未登录被 `RequireAuth` 前转到 `/login`：队列不丢，登录后页面挂载即消费。
 */

import { render } from '@testing-library/react'
import { useCallback } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ROUTES } from '@/app/paths'
import { useUiPendingAction } from '../hooks/use-ui-pending-action'
import { COLLECTED_PAGE_EXECUTORS, collectExecutors } from './discover'
import { takePageActions } from './pending'
import { runUiTool, setPageExecutors } from './registry'
import type { UiActionRequest, UiToolPorts } from './types'

/**
 * 队列键 = 清单里 `ui_material_prep_set_stage` 的 `spec.route`（唯一带 route 的动作）。
 * 页面侧必须用**同一个值**消费（门禁：`manifest-route.node.test.ts` 保证它对应真实路由）。
 */
const PAGE = ROUTES.materialPrep
const MODULE = '/src/features/fake-material-prep/ui-actions.ts'

function request(callId: string, args: Record<string, unknown>): UiActionRequest {
  return { callId, action: 'ui_material_prep_set_stage', args, route: PAGE }
}

/** 端口桩：执行层之外的浏览器能力全换成 spy（ui-tools 内部一律真实现） */
function makePorts(overrides: Partial<UiToolPorts> = {}): UiToolPorts {
  return {
    navigate: vi.fn(),
    currentPath: vi.fn(() => '/'),
    toast: vi.fn(),
    dispatch: vi.fn(),
    openCopilot: vi.fn(),
    ...overrides,
  }
}

/**
 * 把清单里那条带 route 的动作装成「页面自己声明的」。
 * 只有页面声明的执行器才会走「路径不匹配就排队」分支（内置三条是 URL 直达，不排队，
 * 见 registry.ts），所以这条注入是场景 A/C 的前提。
 */
function installPageExecutor() {
  const execute = vi.fn((_args: Record<string, unknown>, _ports: UiToolPorts) => ({
    ok: true as const,
    detail: '页面执行器跑过了',
  }))
  setPageExecutors(collectExecutors({ [MODULE]: { uiActions: [{ action: 'ui_material_prep_set_stage', execute }] } }))
  return execute
}

/**
 * 目标页的最小探针：真实 `useUiPendingAction` + 页面自己的处理函数。
 * `onRequest` 用 `useCallback` 固定（hook 的 effect 依赖它，与约定写法一致）。
 */
function TargetPage({ page, onRequest }: { page: string; onRequest: (request: UiActionRequest) => void }) {
  const handle = useCallback((pendingRequest: UiActionRequest) => onRequest(pendingRequest), [onRequest])
  useUiPendingAction(page, handle)
  return null
}

beforeEach(() => {
  // 页面实现覆盖了内置执行器，registry 在收集期会 warn 一句（预期的，不是本文件的被测对象）
  vi.spyOn(console, 'warn').mockImplementation(() => {})
})

afterEach(() => {
  setPageExecutors(COLLECTED_PAGE_EXECUTORS)
  // 失败用例可能留下残留，清掉免得带进下一个；/login 用于场景 C 的反向断言
  takePageActions(PAGE)
  takePageActions(ROUTES.login)
  vi.restoreAllMocks()
})

describe('跨页续跑的集成路径（真 runUiTool + 真队列 + 真 hook，只 mock 端口）', () => {
  it('场景 A：当前在别的页 → 入队 + 跳转；页面挂载后执行器恰好跑一次，参数原样', async () => {
    const pageExecutor = installPageExecutor()
    const args = { stage: 'todo' }
    const req = request('call-a', args)
    // 模拟 SPA：navigate 只改「浏览器地址」这一个事实来源
    let currentPath = '/projects'
    const ports = makePorts({
      currentPath: vi.fn(() => currentPath),
      navigate: vi.fn((to: string) => {
        currentPath = to
      }),
    })

    const outcome = await runUiTool(req, ports)

    // ① ok + detail 说明「跳过去了、页面就绪后继续」，而不是假装已经做完
    expect(outcome).toEqual({ ok: true, detail: `已跳转到 ${PAGE}，页面就绪后继续` })
    // ② 跳的正是清单声明的 route（拼错一个字母就会静默落到不存在的页面）
    expect(ports.navigate).toHaveBeenCalledTimes(1)
    expect(ports.navigate).toHaveBeenCalledWith(PAGE)
    // ③ 页面还没挂载，执行器一次都不许跑（跑了就是对一个不存在的组件做操作）
    expect(pageExecutor).not.toHaveBeenCalled()

    const handler = vi.fn((pendingRequest: UiActionRequest) => pageExecutor(pendingRequest.args, ports))
    render(<TargetPage page={PAGE} onRequest={handler} />)

    // 挂载即取走：handler 恰好一次，拿到的就是排队时那条请求（同一个对象，没被重建）
    expect(handler).toHaveBeenCalledTimes(1)
    expect(handler.mock.calls[0]?.[0]).toBe(req)
    // 执行器恰好一次，参数是原始 args 对象（队列不做序列化，写类动作的参数不能被改写）
    expect(pageExecutor).toHaveBeenCalledTimes(1)
    expect(pageExecutor.mock.calls[0]?.[0]).toBe(args)
    // 取出即清：页面重挂载不会把同一条指令再执行一遍
    expect(takePageActions(PAGE)).toEqual([])
  })

  it('场景 B：已经在目标页（含 query）→ 直接执行，不入队、不导航', async () => {
    const pageExecutor = installPageExecutor()
    const args = { stage: 'done' }
    const ports = makePorts({ currentPath: vi.fn(() => `${PAGE}?stage=todo`) })

    const outcome = await runUiTool(request('call-b', args), ports)

    expect(outcome).toEqual({ ok: true, detail: '页面执行器跑过了' })
    expect(pageExecutor).toHaveBeenCalledTimes(1)
    expect(pageExecutor.mock.calls[0]?.[0]).toBe(args)
    expect(ports.navigate).not.toHaveBeenCalled()
    expect(takePageActions(PAGE)).toEqual([])
  })

  it('场景 C：navigate 被 RequireAuth 前转到 /login 时队列不丢，目标页挂载仍能取走', async () => {
    const pageExecutor = installPageExecutor()
    const req = request('call-c', { stage: 'todo' })
    // 未登录：navigate 之后地址仍停在 /login（RequireAuth 的 <Navigate> 覆盖了目标地址）
    const ports = makePorts({ currentPath: vi.fn(() => ROUTES.login) })

    const outcome = await runUiTool(req, ports)

    expect(outcome).toEqual({ ok: true, detail: `已跳转到 ${PAGE}，页面就绪后继续` })
    expect(ports.navigate).toHaveBeenCalledWith(PAGE)
    // 队列没丢，而且没有挂到「前转后的当前地址」名下：/login 取不到任何东西
    expect(takePageActions(ROUTES.login)).toEqual([])

    // 关键语义：队列键是 manifest 的 `spec.route`，不是「navigate 之后当前停在哪」。
    // RequireAuth 前转只是因为没登录；登录后目标页挂载，hook 第一帧就消费这条请求，
    // 不需要 AI 再发一次（再发一次 = 同一条指令执行两遍，写类动作就是事故）。
    const handler = vi.fn((pendingRequest: UiActionRequest) => pageExecutor(pendingRequest.args, ports))
    render(<TargetPage page={PAGE} onRequest={handler} />)

    expect(handler).toHaveBeenCalledTimes(1)
    expect(handler.mock.calls[0]?.[0]).toBe(req)
    expect(pageExecutor).toHaveBeenCalledTimes(1)
    expect(takePageActions(PAGE)).toEqual([])
  })
})
