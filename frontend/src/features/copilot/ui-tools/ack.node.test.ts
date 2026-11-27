/**
 * 界面动作回执（node）：只发一次 / 重试一次 / 永不抛 / detail 截断 / observed_location 取当次地址。
 *
 * 为什么要为「一段 fire-and-forget 的 POST」写五条用例：这条回执是模型唯一能看见
 * 「页面真的变了」的通道。它坏掉的方式全是静默的——多发一次是后端的脏 pending，
 * 少发一次是模型永远 `observed: false`，抛出去是律师侧凭空多一个错误。
 *
 * 只替身 HTTP 边界（`../api`），其余全是真实现。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { submitUiActionResult } from '../api'
import { ackUiActionResult } from './ack'

vi.mock('../api', () => ({ submitUiActionResult: vi.fn() }))

/** 后端的正常回执（`success=false` 也走这条，不是失败） */
const RECEIPT = { accepted: true, success: true }
/** 与 `ack.ts` 的 RETRY_DELAY_MS 对齐：不变式写在这里，改那边就得看这条用例 */
const RETRY_DELAY_MS = 300

/** 把微任务队列抽干（整个 ack 链路没有真定时任务，只有 300ms 那一次重试） */
async function flushMicrotasks(): Promise<void> {
  for (let i = 0; i < 6; i += 1) await Promise.resolve()
}

/** 发出去的那份 payload（缺失即说明根本没发，给出可读失败信息而不是 TypeError） */
function sentPayload(index = 0) {
  const call = vi.mocked(submitUiActionResult).mock.calls[index]
  if (!call) throw new Error(`没有第 ${index + 1} 次回执：submitUiActionResult 没被调用`)
  return call[0]
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(submitUiActionResult).mockResolvedValue(RECEIPT)
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('界面动作回执', () => {
  it('成功路径：只发一次，payload 是「结算事实 + 执行后的地址」', async () => {
    await ackUiActionResult(
      { call_id: 'c-ok-1', outcome: 'ok', detail: '已跳转到 /projects' },
      { currentLocation: () => '/projects' },
    )

    expect(submitUiActionResult).toHaveBeenCalledTimes(1)
    expect(sentPayload()).toEqual({
      call_id: 'c-ok-1',
      outcome: 'ok',
      detail: '已跳转到 /projects',
      observed_location: '/projects',
    })
  })

  it('第一次失败会重试一次；第二次成功就不再重试', async () => {
    vi.useFakeTimers()
    vi.mocked(submitUiActionResult).mockRejectedValueOnce(new Error('网络抖动')).mockResolvedValueOnce(RECEIPT)

    const done = ackUiActionResult({ call_id: 'c-retry-1', outcome: 'ok' }, { currentLocation: () => '/' })
    await flushMicrotasks()

    expect(submitUiActionResult).toHaveBeenCalledTimes(1)
    // 重试真的排在 300ms 之后（不是立刻打两枪：瞬时抖动要留缓冲，否则等于没重试）
    expect(vi.getTimerCount()).toBe(1)

    await vi.advanceTimersByTimeAsync(RETRY_DELAY_MS)
    await done

    expect(submitUiActionResult).toHaveBeenCalledTimes(2)
    // 第二次成功即收工：再往后推一秒也不再发第三次
    await vi.advanceTimersByTimeAsync(1_000)
    expect(submitUiActionResult).toHaveBeenCalledTimes(2)
  })

  it('两次都失败：只 warn 一句、不抛（回执是尽力而为，不能让页面动作变成失败）', async () => {
    vi.useFakeTimers()
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    vi.mocked(submitUiActionResult).mockRejectedValue(new Error('后端那一跳不在了'))

    const done = ackUiActionResult({ call_id: 'c-fail-1', outcome: 'error', code: 'route_unreachable' })
    await flushMicrotasks()
    await vi.advanceTimersByTimeAsync(RETRY_DELAY_MS)

    await expect(done).resolves.toBeUndefined()
    expect(submitUiActionResult).toHaveBeenCalledTimes(2)
    expect(warn).toHaveBeenCalledTimes(1)
    expect(String(warn.mock.calls[0]?.[0])).toContain('后端那一跳不在了')
    // 只 warn 不 error：这是旁路证据，不该被错误上报当成页面事故
    expect(warn.mock.calls[0]?.[0]).toContain('c-fail-1')
  })

  it('detail 超过 200 字被截断（契约上限），短的原文不动', async () => {
    await ackUiActionResult({ call_id: 'c-long-1', outcome: 'error', detail: '错'.repeat(260) })
    expect(sentPayload().detail).toHaveLength(200)
    expect(sentPayload().detail).toBe('错'.repeat(200))

    await ackUiActionResult({ call_id: 'c-short-1', outcome: 'ok', detail: '已跳到 /projects' })
    expect(sentPayload(1).detail).toBe('已跳到 /projects')
  })

  it('observed_location 取「调用这一刻」的真实地址（不是启动时的快照，也不是模型给的目标）', async () => {
    // ① 默认读 window：执行器可能被 replace、被路由改写，只有此刻地址能自证
    vi.stubGlobal('window', { location: { pathname: '/material-prep', search: '?stage=todo' } })
    await ackUiActionResult({ call_id: 'c-loc-1', outcome: 'ok' })
    expect(sentPayload().observed_location).toBe('/material-prep?stage=todo')

    // ② 页面又跳了：下一次回执必须报新地址（读模块加载期的值就会永远报第一条）
    vi.stubGlobal('window', { location: { pathname: '/projects', search: '' } })
    await ackUiActionResult({ call_id: 'c-loc-2', outcome: 'ok' })
    expect(sentPayload(1).observed_location).toBe('/projects')

    // ③ 宿主/单测可注入读法（生产不传，走 ①）
    await ackUiActionResult({ call_id: 'c-loc-3', outcome: 'aborted' }, { currentLocation: () => '/cases/812?tab=docs' })
    expect(sentPayload(2).observed_location).toBe('/cases/812?tab=docs')
  })
})
