/**
 * 「先跳过去，再由目标页面接着做」的队列：入队 / 取出即清 / 上限 / 不串页，
 * 以及 registry 侧的判断——**路径不匹配才排队**，匹配就直接跑。
 *
 * 后半段（`runUiTool` 的那几条）才是这个机制真正的失败点：判错的后果不是报错，
 * 而是「跳过去了但什么都没发生」——所以「段前缀不误判」「内置三条不排队」都单独钉死。
 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import { COLLECTED_PAGE_EXECUTORS, collectExecutors } from './discover'
import { MAX_PENDING_PAGE_ACTIONS, queuePageAction, takePageActions } from './pending'
import { runUiTool, setPageExecutors } from './registry'
import type { PageUiAction, UiActionRequest, UiExecutor, UiToolPorts } from './types'

/** 页面键 = 清单里 `ui_material_prep_set_stage` 的 `route`（执行器入队时用的就是它） */
const PAGE = '/material-prep'
const MODULE_A = '/src/features/fake-a/ui-actions.ts'

function request(callId: string): UiActionRequest {
  return { callId, action: 'ui_material_prep_set_stage', args: { stage: 'todo' }, route: PAGE }
}

function pageAction(action: string, execute: UiExecutor): PageUiAction {
  return { action, execute } as PageUiAction
}

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

/** 把清单里那条带 route 的动作「装成页面自己声明的」（看板实现是 spy，能断言有没有真跑） */
function installPageAction(): UiExecutor {
  const impl = vi.fn(() => ({ ok: true as const, detail: '页面实现' }))
  setPageExecutors(collectExecutors({ [MODULE_A]: { uiActions: [pageAction('ui_material_prep_set_stage', impl)] } }))
  return impl
}

afterEach(() => {
  setPageExecutors(COLLECTED_PAGE_EXECUTORS)
  // 本文件只碰 PAGE 这一个键；取空即清，免得失败用例把残留带进下一个
  takePageActions(PAGE)
  vi.restoreAllMocks()
})

describe('队列：入队 / 取出即清 / 不串页 / 上限', () => {
  it('入队后能按顺序取回，且**取出即清**（页面重挂载不会重复执行同一个请求）', () => {
    const first = request('call-1')
    const second = request('call-2')
    queuePageAction(PAGE, first)
    queuePageAction(PAGE, second)

    expect(takePageActions(PAGE)).toEqual([first, second])
    expect(takePageActions(PAGE)).toEqual([])
  })

  it('没入过队的页面取到空数组（不返回 undefined，调用方不必判空）', () => {
    expect(takePageActions('/never-queued')).toEqual([])
  })

  it('不同页面互不串（取走 A 页的不会顺手动到 B 页）', () => {
    queuePageAction(PAGE, request('call-a'))
    queuePageAction('/projects', request('call-b'))

    expect(takePageActions(PAGE).map((r) => r.callId)).toEqual(['call-a'])
    expect(takePageActions('/projects').map((r) => r.callId)).toEqual(['call-b'])
  })

  it(`每页最多 ${MAX_PENDING_PAGE_ACTIONS} 条，超限丢最旧的（保最新一条：那才是律师刚看到的）`, () => {
    const total = MAX_PENDING_PAGE_ACTIONS + 3
    for (let i = 0; i < total; i += 1) queuePageAction(PAGE, request(`call-${i}`))

    const taken = takePageActions(PAGE)
    expect(taken).toHaveLength(MAX_PENDING_PAGE_ACTIONS)
    expect(taken[0]?.callId).toBe(`call-${total - MAX_PENDING_PAGE_ACTIONS}`)
    expect(taken.at(-1)?.callId).toBe(`call-${total - 1}`)
  })
})

describe('registry：路径不匹配 → 排队 + 跳过去；匹配 → 直接执行', () => {
  it('不在目标页时：先把请求排进队列、再 navigate，页面执行器这次不跑', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    const impl = installPageAction()
    const ports = makePorts({ currentPath: vi.fn(() => '/projects/393') })

    const outcome = await runUiTool(request('call-1'), ports)

    expect(outcome).toMatchObject({ ok: true, detail: `已跳转到 ${PAGE}，页面就绪后继续` })
    expect(ports.navigate).toHaveBeenCalledWith(PAGE)
    expect(impl).not.toHaveBeenCalled()
    // 目标页挂载后由 hooks/use-ui-pending-action 取走，取到的必须是同一条请求
    expect(takePageActions(PAGE).map((r) => r.callId)).toEqual(['call-1'])
  })

  it('已经在目标页（含 query / 子路径）：直接执行，不排队也不多跳一次', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    const impl = installPageAction()
    for (const currentPath of [PAGE, `${PAGE}?stage=todo`, `${PAGE}/393`]) {
      const ports = makePorts({ currentPath: vi.fn(() => currentPath) })
      const outcome = await runUiTool(request(`call-${currentPath}`), ports)
      expect(outcome).toMatchObject({ ok: true, detail: '页面实现' })
      expect(ports.navigate).not.toHaveBeenCalled()
    }
    expect(impl).toHaveBeenCalledTimes(3)
    expect(takePageActions(PAGE)).toEqual([])
  })

  it('段前缀按段比：/material-prep-x 不算已经在 /material-prep 上（否则动作落在错页）', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    const impl = installPageAction()
    const ports = makePorts({ currentPath: vi.fn(() => '/material-prep-x') })

    await runUiTool(request('call-1'), ports)

    expect(impl).not.toHaveBeenCalled()
    expect(ports.navigate).toHaveBeenCalledWith(PAGE)
    expect(takePageActions(PAGE)).toHaveLength(1)
  })

  it('内置三条动作（不是页面声明的）不排队：切阶段仍是 URL 直达 + replace', async () => {
    const ports = makePorts({ currentPath: vi.fn(() => '/projects/393') })

    const outcome = await runUiTool(
      { callId: 'call-1', action: 'ui_material_prep_set_stage', args: { stage: 'todo' }, route: PAGE },
      ports,
    )

    expect(outcome).toMatchObject({ ok: true, detail: `${PAGE}?stage=todo` })
    expect(ports.navigate).toHaveBeenCalledWith(`${PAGE}?stage=todo`, { replace: true })
    expect(takePageActions(PAGE)).toEqual([])
  })
})
