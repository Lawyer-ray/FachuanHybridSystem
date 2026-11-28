// @vitest-environment jsdom
/**
 * 保存之后必须**核实到底有没有落盘**。
 *
 * 这是「静默数据丢失」唯一的用户可见出口：过期画布的保存会被后端主动丢弃，
 * 但应答仍是 `error:0`（不让 DS 无限重试同一份旧内容）。不查、不提示，律师
 * 看到的就是「已提交保存」，而那次编辑已经永久丢失。
 *
 * 三条断言各自守一件事：
 * 1. 真的丢了 → 必须弹 `error`（不是 success 一了百了）；
 * 2. 同一份丢弃只提示一次（`dropped_at` 是持久信号，不去重会每按一次 ⌘S 弹一次）；
 * 3. 查状态本身失败 → 不打扰律师（保存主链路的结果不受它影响）。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const getCanvasState = vi.hoisted(() =>
  vi.fn(async () => ({ stale: true, reason: '', dropped_at: null as string | null })),
)
vi.mock('@/components/shared/onlyoffice/api', () => ({ getCanvasState }))

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }))
vi.mock('sonner', () => ({ toast }))

vi.mock('@/lib/download-ticket', () => ({ withDownloadTicket: vi.fn(async (u: string) => u) }))
vi.mock('@/lib/download', () => ({ downloadUrl: vi.fn() }))
// 另存为链路不在本文件职责内（use-save-as.test.ts 已覆盖）
vi.mock('./use-save-as', () => ({
  intentSubpath: (_k: string, _o: number, s: string) => s,
  canSaveAs: () => false,
  useSaveAs: () => async () => {},
}))

import { useFolderSave } from './use-folder-save'

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

function mount(requestSave = vi.fn(() => true), over: { canSave?: boolean; ready?: boolean } = {}) {
  return renderHook(
    () =>
      useFolderSave({
        kind: 'contract',
        ownerId: 393,
        file: { subpath: '1-合同/a.docx', name: 'a.docx' },
        requestSave,
        canSave: over.canSave ?? true,
        saveAsEnabled: false,
        ready: over.ready ?? true,
      }),
    { wrapper },
  )
}

/** 模拟一次 ⌘S（监听挂在 document 上） */
function pressCmdS() {
  act(() => {
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 's', metaKey: true, bubbles: true }))
  })
}

async function pressSaveThenFlush(hook: ReturnType<typeof mount>) {
  act(() => hook.result.current.save())
  // 保存后延迟 2500ms 才刷新与核实（落盘发生在 DS 回调里）
  await act(async () => {
    await vi.advanceTimersByTimeAsync(2500)
  })
  // 让 getCanvasState 的 promise 链跑完
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
}

beforeEach(() => {
  vi.useFakeTimers()
  toast.success.mockClear()
  toast.error.mockClear()
  getCanvasState.mockClear()
  getCanvasState.mockResolvedValue({ stale: true, reason: '', dropped_at: null })
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useFolderSave：保存入口的反馈', () => {
  it('连按两次 ⌘S 只发一次 forcesave（busy 是 state，拦不住同一帧的重入）', () => {
    const requestSave = vi.fn(() => true)
    const hook = mount(requestSave)

    pressCmdS()
    pressCmdS()

    expect(requestSave).toHaveBeenCalledTimes(1)
    hook.unmount()
  })

  it('只读格式按 ⌘S 不再是死键：不保存，但明确说一句', () => {
    const requestSave = vi.fn(() => true)
    toast.info.mockClear()
    // 只读文档（pdf/图片）不给原地保存，但也不能让按键无声消失
    const hook = mount(requestSave, { canSave: false })

    pressCmdS()

    expect(requestSave).not.toHaveBeenCalled()
    expect(String(toast.info.mock.calls[0]?.[0])).toContain('不支持原地保存')
    hook.unmount()
  })
})

describe('useFolderSave：保存后核实落盘', () => {
  it('保存被丢弃时必须弹 error，而不是让「已提交保存」蒙混过关', async () => {
    getCanvasState.mockResolvedValue({
      stale: true,
      reason: '文档已被 AI 改写（磁盘内容新于当前画布）…',
      dropped_at: '2026-11-26T00:30:00Z',
    })
    const hook = mount()

    await pressSaveThenFlush(hook)

    expect(getCanvasState).toHaveBeenCalledTimes(1)
    expect(toast.error).toHaveBeenCalledTimes(1)
    expect(String(toast.error.mock.calls[0]?.[0])).toContain('已被丢弃')
    hook.unmount()
  })

  it('正常落盘（dropped_at 为空）不该弹错', async () => {
    getCanvasState.mockResolvedValue({ stale: false, reason: '', dropped_at: null })
    const hook = mount()

    await pressSaveThenFlush(hook)

    expect(toast.error).not.toHaveBeenCalled()
    hook.unmount()
  })

  it('同一次丢弃只提示一次（dropped_at 是持久信号，不按下去重会反复弹）', async () => {
    getCanvasState.mockResolvedValue({
      stale: true,
      reason: 'r',
      dropped_at: '2026-11-26T00:30:00Z',
    })
    const hook = mount()

    await pressSaveThenFlush(hook)
    await pressSaveThenFlush(hook)

    expect(toast.error).toHaveBeenCalledTimes(1)
    hook.unmount()
  })

  it('查状态失败不打扰律师（保存主链路结果不受影响）', async () => {
    getCanvasState.mockRejectedValue(new Error('network'))
    const hook = mount()

    await pressSaveThenFlush(hook)

    expect(toast.error).not.toHaveBeenCalled()
    // 「已提交保存」照旧提示，不能因为核实接口挂了就什么都不说
    expect(toast.success).toHaveBeenCalled()
    hook.unmount()
  })

  it('编辑器未就绪时不发保存、也不去核实', async () => {
    const requestSave = vi.fn(() => false)
    const hook = mount(requestSave)

    act(() => hook.result.current.save())
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000)
    })

    expect(getCanvasState).not.toHaveBeenCalled()
    expect(toast.error).toHaveBeenCalledTimes(1) // 「编辑器尚未就绪」
    hook.unmount()
  })
})
