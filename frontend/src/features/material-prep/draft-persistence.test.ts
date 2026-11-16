/**
 * draft-persistence（scheduleSave 防抖落盘）纯逻辑单测（node 环境）。
 * mock 只打 ./api 的 saveDraft 与 sonner toast；计时器用 vitest 假计时器。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { saveDraftMock, toastMock } = vi.hoisted(() => ({
  saveDraftMock: vi.fn(),
  toastMock: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}))

vi.mock('sonner', () => ({ toast: toastMock }))

vi.mock('./api', () => ({
  saveDraft: saveDraftMock,
}))

import { discardPendingSave, flushPendingSave, scheduleSave } from './draft-persistence'
import type { DraftState } from './types'

const draftOf = (mark: string): DraftState => ({ mats: [], segs: [], infos: [], mark } as unknown as DraftState)

beforeEach(() => {
  vi.useFakeTimers()
  vi.clearAllMocks()
  // 每个用例从干净的单例状态开始：先丢弃可能残留的待存草稿与计时器
  discardPendingSave()
})

afterEach(() => {
  // 收尾清计时器，避免假计时器泄漏到其他文件
  discardPendingSave()
  vi.useRealTimers()
})

describe('scheduleSave 防抖落盘', () => {
  it('连续排队只落最后一次：450ms 内多次 schedule 只打一次 saveDraft，且是最新草稿', async () => {
    saveDraftMock.mockResolvedValue(undefined)
    scheduleSave(draftOf('a'), 1)
    vi.advanceTimersByTime(200)
    scheduleSave(draftOf('b'), 1)
    vi.advanceTimersByTime(200)
    scheduleSave(draftOf('c'), 1)
    expect(saveDraftMock).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(60)
    expect(saveDraftMock).toHaveBeenCalledExactlyOnceWith(1, draftOf('c'))
  })

  it('已排队时再 schedule 返回 null（并入现有批次，不重复建计时器）', () => {
    const first = scheduleSave(draftOf('a'), 1)
    expect(first).toBeInstanceOf(Promise)
    expect(scheduleSave(draftOf('b'), 1)).toBeNull()
  })

  it('immediate：取消防抖马上落盘（关阅读器 / 打标状态的口径）', async () => {
    saveDraftMock.mockResolvedValue(undefined)
    scheduleSave(draftOf('a'), 1)
    const p = scheduleSave(draftOf('b'), 1, true)
    expect(p).toBeInstanceOf(Promise)
    await vi.advanceTimersByTimeAsync(0)
    expect(saveDraftMock).toHaveBeenCalledExactlyOnceWith(1, draftOf('b'))
    // 原防抖计时器已被取消：再等一个周期也不会有第二次落盘
    await vi.advanceTimersByTimeAsync(500)
    expect(saveDraftMock).toHaveBeenCalledTimes(1)
  })

  it('落盘失败：toast 报错且 promise reject', async () => {
    const boom = new Error('backend down')
    saveDraftMock.mockRejectedValue(boom)
    const p = scheduleSave(draftOf('a'), 1)
    // 先挂上 rejection 断言再走计时器：reject 发生在 advanceTimers 内，
    // 后挂会先形成一次 unhandled rejection
    const expectReject = expect(p).rejects.toBe(boom)
    await vi.advanceTimersByTimeAsync(500)
    await expectReject
    expect(toastMock.error).toHaveBeenCalledWith('拆分草稿保存失败，请检查后端连接')
  })

  it('discardPendingSave：登出丢弃未落盘草稿，不再发 saveDraft', async () => {
    saveDraftMock.mockResolvedValue(undefined)
    scheduleSave(draftOf('secret'), 1)
    discardPendingSave()
    await vi.advanceTimersByTimeAsync(500)
    expect(saveDraftMock).not.toHaveBeenCalled()
    // 丢弃后新排队照常工作（计时器槽位已清）
    scheduleSave(draftOf('next'), 2)
    await vi.advanceTimersByTimeAsync(500)
    expect(saveDraftMock).toHaveBeenCalledExactlyOnceWith(2, draftOf('next'))
  })
})

/**
 * P3-5：登出前 flush。防抖窗口（450ms）内的最后一次编辑以前会被 discardPendingSave
 * 直接丢掉——律师改完最后一个字就点退出，那次改动谁也没保存。
 */
describe('flushPendingSave：登出前把待存草稿立刻落盘', () => {
  it('不等防抖到点就存最新草稿，且原计时器被取消（不会存第二次）', async () => {
    saveDraftMock.mockResolvedValue(undefined)
    scheduleSave(draftOf('a'), 7)
    vi.advanceTimersByTime(200)
    scheduleSave(draftOf('b'), 7)
    const p = flushPendingSave()
    expect(p).toBeInstanceOf(Promise)
    expect(saveDraftMock).toHaveBeenCalledExactlyOnceWith(7, draftOf('b'))
    await p
    await vi.advanceTimersByTimeAsync(500)
    expect(saveDraftMock).toHaveBeenCalledTimes(1)
  })

  it('没有待存草稿时返回 null，不发请求', () => {
    expect(flushPendingSave()).toBeNull()
    expect(saveDraftMock).not.toHaveBeenCalled()
    scheduleSave(draftOf('a'), 1)
    flushPendingSave()
    expect(flushPendingSave()).toBeNull()
  })

  it('flush 失败只 reject 不 toast（登出路径上凭证可能已清，报错文案会误导）', async () => {
    const boom = new Error('401')
    saveDraftMock.mockRejectedValue(boom)
    scheduleSave(draftOf('a'), 1)
    const p = flushPendingSave()!
    const expectReject = expect(p).rejects.toBe(boom)
    await expectReject
    expect(toastMock.error).not.toHaveBeenCalled()
  })

  it('flush 之后新排队照常工作（单例状态已清干净）', async () => {
    saveDraftMock.mockResolvedValue(undefined)
    scheduleSave(draftOf('old'), 1)
    flushPendingSave()
    scheduleSave(draftOf('new'), 2)
    await vi.advanceTimersByTimeAsync(500)
    expect(saveDraftMock).toHaveBeenLastCalledWith(2, draftOf('new'))
  })
})
