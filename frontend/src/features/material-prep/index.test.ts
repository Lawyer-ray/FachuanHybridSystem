/**
 * material-prep 对外出口单测（node 环境）。
 *
 * 出口只承诺两件事，都写在同一处以防有人「顺手改成静态引」：
 * 1. resetMaterialPrepState 走动态 import（链路带 pdfjs-dist，静态引会把整个
 *    材料预处理域拖进首屏包），调用后阅读器状态真的被清空；
 * 2. 收件箱消息内容仍然经出口对外（home 的收件箱卡免于穿透内部目录）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const tokenMock = vi.hoisted(() => ({ hasToken: vi.fn(() => true) }))
const persistenceMock = vi.hoisted(() => ({
  flushPendingSave: vi.fn((): Promise<void> | null => null),
  scheduleSave: vi.fn(() => null),
  discardPendingSave: vi.fn(),
}))
vi.mock('@/lib/token', () => tokenMock)
vi.mock('./draft-persistence', () => persistenceMock)

import { InboxMessageContent, resetMaterialPrepState } from './index'
import { useReader } from './store'

describe('material-prep index 出口', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    tokenMock.hasToken.mockReturnValue(true)
    useReader.getState().resetAll()
    vi.clearAllMocks()
  })

  it('resetMaterialPrepState 清空阅读器会话状态（登出换账号不得残留上一位的材料）', async () => {
    useReader.setState({ openId: 42, assignOpen: true, selPages: [{ mi: 0, p: 0 }] })
    expect(useReader.getState().openId).toBe(42)

    await resetMaterialPrepState()

    expect(useReader.getState().openId).toBeNull()
    expect(useReader.getState().assignOpen).toBe(false)
    expect(useReader.getState().selPages).toEqual([])
    expect(useReader.getState().status).toBe('idle')
  })

  it('复用收件箱消息内容组件（home 不穿透内部目录）', () => {
    expect(typeof InboxMessageContent).toBe('function')
  })

  it('resetMaterialPrepState 返回 Promise（调用方可 await，不阻塞渲染）', async () => {
    await expect(resetMaterialPrepState()).resolves.toBeUndefined()
  })

  /**
   * P3-5：登出前必须先把防抖窗口（450ms）内的最后一次编辑落盘，再丢弃/重置。
   * 顺序反了就是把律师刚改完的字直接丢掉。
   */
  it('凭证仍在时：先 flush 待存草稿，再重置阅读器', async () => {
    await resetMaterialPrepState()
    expect(persistenceMock.flushPendingSave).toHaveBeenCalledTimes(1)
    expect(persistenceMock.discardPendingSave).toHaveBeenCalledTimes(1)
    expect(persistenceMock.flushPendingSave.mock.invocationCallOrder[0]).toBeLessThan(
      persistenceMock.discardPendingSave.mock.invocationCallOrder[0]!,
    )
  })

  it('凭证已清时不发注定 401 的保存（调用方先清了 token 的兜底）', async () => {
    tokenMock.hasToken.mockReturnValue(false)
    await resetMaterialPrepState()
    expect(persistenceMock.flushPendingSave).not.toHaveBeenCalled()
    expect(useReader.getState().openId).toBeNull()
  })

  it('flush 失败不阻断登出清理', async () => {
    persistenceMock.flushPendingSave.mockReturnValueOnce(Promise.reject(new Error('backend down')))
    await expect(resetMaterialPrepState()).resolves.toBeUndefined()
    expect(useReader.getState().status).toBe('idle')
  })
})
