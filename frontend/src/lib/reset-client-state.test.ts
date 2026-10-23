/**
 * reset-client-state 测试（node 环境）。
 *
 * 这是「主动退出」与「会话过期被踢」共用的唯一清理入口（2026-10 审查 I-P1-2）。
 * 核心不变量：
 * - 一定先清 token（凭证是最敏感的）
 * - 调用方注入的 queryCache 清理器必须被执行
 * - 三条 feature 清理链（material-prep / copilot / pdf）都走动态 import
 * - 任一条清理失败都不得让整个重置抛错（否则登出会被卡住）
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const clearTokensMock = vi.hoisted(() => vi.fn())
const resetMatMock = vi.hoisted(() => vi.fn())
const resetCopilotMock = vi.hoisted(() => vi.fn())
const clearPdfMock = vi.hoisted(() => vi.fn())

vi.mock('@/lib/token', () => ({ clearTokens: clearTokensMock }))
vi.mock('@/features/material-prep', () => ({ resetMaterialPrepState: resetMatMock }))
vi.mock('@/features/copilot', () => ({ resetCopilotState: resetCopilotMock }))
vi.mock('@/lib/pdf', () => ({ clearPdfCache: clearPdfMock }))

import { resetAllClientState } from './reset-client-state'

beforeEach(() => {
  vi.clearAllMocks()
  resetMatMock.mockReturnValue(undefined)
  resetCopilotMock.mockReturnValue(undefined)
  clearPdfMock.mockReturnValue(undefined)
})

describe('resetAllClientState', () => {
  it('清 token 并执行三条 feature 清理链', async () => {
    await resetAllClientState()

    expect(clearTokensMock).toHaveBeenCalled()
    expect(resetMatMock).toHaveBeenCalled()
    expect(resetCopilotMock).toHaveBeenCalled()
    expect(clearPdfMock).toHaveBeenCalled()
  })

  it('调用方注入的 queryCache 清理器被执行', async () => {
    const clearCache = vi.fn()
    await resetAllClientState(clearCache)
    expect(clearCache).toHaveBeenCalled()
  })

  it('未注入清理器时不抛错', async () => {
    await expect(resetAllClientState()).resolves.toBeUndefined()
  })

  it('token 清理先于 feature 清理执行（顺序敏感）', async () => {
    const order: string[] = []
    clearTokensMock.mockImplementation(() => order.push('token'))
    resetMatMock.mockImplementation(() => order.push('mat'))

    await resetAllClientState()
    expect(order[0]).toBe('token')
  })

  it('某条 feature 清理抛同步异常时整体仍 resolve', async () => {
    resetMatMock.mockImplementation(() => {
      throw new Error('material-prep 清理失败')
    })
    await expect(resetAllClientState()).resolves.toBeUndefined()
  })

  it('copilot 清理抛错不影响其他链', async () => {
    resetCopilotMock.mockImplementation(() => {
      throw new Error('copilot 清理失败')
    })
    await resetAllClientState()

    expect(clearTokensMock).toHaveBeenCalled()
    expect(resetMatMock).toHaveBeenCalled()
    expect(clearPdfMock).toHaveBeenCalled()
  })

  it('pdf 清理抛错同样不中断', async () => {
    clearPdfMock.mockImplementation(() => {
      throw new Error('pdf 清理失败')
    })
    await expect(resetAllClientState()).resolves.toBeUndefined()
    expect(resetMatMock).toHaveBeenCalled()
  })

  it('清理器自身抛错时不影响 token 与 feature 清理', async () => {
    const clearCache = vi.fn(() => {
      throw new Error('query cache 清理失败')
    })
    await expect(resetAllClientState(clearCache)).resolves.toBeUndefined()
    expect(clearTokensMock).toHaveBeenCalled()
  })
})
