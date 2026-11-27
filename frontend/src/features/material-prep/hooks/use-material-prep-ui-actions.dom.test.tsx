// @vitest-environment jsdom
/**
 * 接线 hook 的真实行为。DeskPage 的三个编排用例文件把本 hook **整块打桩**了
 * （`desk-page-test-harness.tsx` 里那句 `vi.mock`），所以这三件事只能在这里证明：
 *
 * 1. 挂载时把页面状态登记进 `readPageState('material-prep')`（AI 读到的就是这份）；
 * 2. 收到 `PACK_STATUS_CHANGED_EVENT` 后真的重拉材料包列表（执行器在 copilot 那侧写完库的路径）；
 * 3. `useUiPendingAction` 队列里的请求会被消费（「跳过来再继续做」的路径）。
 *
 * 缺任何一条，对应的链路都表现为「AI 说做完了、页面一动不动」——而且不会有任何报错。
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { toast } from 'sonner'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ROUTES } from '@/app/paths'
import { queuePageAction, readPageState, takePageActions } from '@/features/copilot/ui-tools/contract'

import { setPackStatusRemote } from '../api/inbox-packs'
import type { PrepStage } from '../stages'
import { PACK_STATUS_CHANGED_EVENT } from '../ui-actions'
import { PACKS_KEY } from './use-material-packs'
import { useMaterialPrepUiActions } from './use-material-prep-ui-actions'

// 判决动作会真的写库（PUT /inbox/messages/{id}/draft）：这里只关心「有没有走到 feature 的
// api 层」，网络留给 api 模块自己的测试。
vi.mock('../api/inbox-packs', () => ({ setPackStatusRemote: vi.fn() }))

// sonner 在 jsdom 里要 Toaster 才渲染；这里只断言「说了一句什么」，直接替掉实现。
vi.mock('sonner', () => {
  const fn = vi.fn()
  return { toast: Object.assign(fn, { success: vi.fn(), error: vi.fn() }) }
})

const COUNTS = { inbox: 2, todo: 3, done: 4, filed: 5 }

/** 被测 hook 的最小宿主：它没有返回值，渲染结果无关，只挂副作用 */
function Host({ stage, selected }: { stage: PrepStage; selected: number | null }) {
  useMaterialPrepUiActions({ stage, selected, counts: COUNTS })
  return null
}

let queryClient: QueryClient

beforeEach(() => {
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  vi.mocked(setPackStatusRemote).mockReset()
})

afterEach(() => {
  cleanup()
  queryClient.clear()
  vi.restoreAllMocks()
  // 挂起队列是模块级 Map：用例之间必须清空，否则上一条的请求会漏到下一条
  takePageActions(ROUTES.materialPrep)
})

function renderHost(stage: PrepStage = 'todo', selected: number | null = 812) {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`${ROUTES.materialPrep}?stage=${stage}`]}>
        <Host stage={stage} selected={selected} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('① 页面状态登记（AI 读到的就是这份快照）', () => {
  it('挂载后 readPageState 读得到 stage / selected / counts 与真实地址', () => {
    const { unmount } = renderHost('todo', 812)

    const read = readPageState('material-prep')
    expect(read).toMatchObject({
      page: 'material-prep',
      // route 取的是**当前地址**（含 ?stage=），不是路由模板：模型据此确认自己在哪一页
      state: { page: 'material-prep', route: '/material-prep?stage=todo', stage: 'todo', selected: 812 },
    })
    expect(read?.state.counts).toEqual(COUNTS)

    unmount()
    // 卸载即注销：页面没了还回旧快照，等于让模型对着不存在的页面下指令
    expect(readPageState('material-prep')).toBeNull()
  })
})

describe('② 判决广播 → 重拉列表 + toast', () => {
  it('收到 PACK_STATUS_CHANGED_EVENT 后用 PACKS_KEY invalidate，并说清改成了什么', async () => {
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    const { unmount } = renderHost()

    window.dispatchEvent(
      new CustomEvent(PACK_STATUS_CHANGED_EVENT, { detail: { packId: 812, status: 'done' } }),
    )

    await waitFor(() => expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: PACKS_KEY }))
    expect(toast).toHaveBeenCalledWith('材料包 812 已判为已归案')

    unmount()
  })

  it('卸载后不再响应广播（否则离场页面也会拉一次列表）', async () => {
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    const { unmount } = renderHost()
    unmount()

    window.dispatchEvent(new CustomEvent(PACK_STATUS_CHANGED_EVENT, { detail: { packId: 9, status: 'filed' } }))
    await Promise.resolve()

    expect(invalidateSpy).not.toHaveBeenCalled()
  })
})

describe('③ 挂起队列：跳过来之后由本页接着做', () => {
  it('队列里的 ui_material_prep_judge 在挂载时被执行：真的调 api、取出即清、并刷新列表', async () => {
    vi.mocked(setPackStatusRemote).mockResolvedValue(undefined)
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    queuePageAction(ROUTES.materialPrep, {
      callId: 'call-queued',
      action: 'ui_material_prep_judge',
      args: { packId: 812, target: 'done' },
      route: ROUTES.materialPrep,
    })

    const { unmount } = renderHost()

    await waitFor(() => expect(setPackStatusRemote).toHaveBeenCalledWith(812, 'done'))
    await waitFor(() => expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: PACKS_KEY }))
    expect(toast).toHaveBeenCalledWith('材料包 812 已判为已归案')
    // 取出即清：页面重挂载（StrictMode 双跑 / 前后台切换）不能把写库动作再跑一遍
    expect(takePageActions(ROUTES.materialPrep)).toEqual([])

    unmount()
  })

  it('队列里的判决失败 → 弹错误、不刷新（失败的刷新只会白跑一次请求）', async () => {
    vi.mocked(setPackStatusRemote).mockRejectedValue(new Error('后端 500'))
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    queuePageAction(ROUTES.materialPrep, {
      callId: 'call-queued-fail',
      action: 'ui_material_prep_judge',
      args: { packId: 812, target: 'filed' },
      route: ROUTES.materialPrep,
    })

    const { unmount } = renderHost()

    await waitFor(() => expect(toast.error).toHaveBeenCalled())
    expect(invalidateSpy).not.toHaveBeenCalled()

    unmount()
  })

  it('队列里的别家动作只 warn 不执行（队列键是路由，不是动作名）', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    queuePageAction(ROUTES.materialPrep, {
      callId: 'call-foreign',
      action: 'ui_navigate',
      args: { path: '/projects' },
      route: ROUTES.materialPrep,
    })

    const { unmount } = renderHost()

    await waitFor(() => expect(warn).toHaveBeenCalled())
    expect(setPackStatusRemote).not.toHaveBeenCalled()

    unmount()
  })
})
