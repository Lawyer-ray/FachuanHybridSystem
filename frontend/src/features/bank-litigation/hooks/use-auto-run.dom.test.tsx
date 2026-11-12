// @vitest-environment jsdom
/**
 * 「提交 → 轮询」状态机单测（jsdom）。
 *
 * 这条由 OA / 一张网四个动作共用，它是界面上「真的在跑」的唯一证据来源，
 * 所以每个分支都要钉住：
 * - 提交成功 → running → 轮询到终态停（success / failed / finished / completed / error）
 * - 后端没给 session_id（同步完成或直接失败）→ 不假装成功，status 原样透出
 * - 提交抛错 → done + error，不进入轮询
 * - 轮询偶发失败 < 宽限 → 继续轮询，不判死
 * - 轮询连续失败到宽限 → done + error，停
 * - 轮询永不终态 → 到上限判 timeout
 * - 组件卸载后不再写状态（卸载后 setState 会 React 警告，且逻辑上已无意义）
 *
 * 时间控制：POLL_MS = 2000，轮询上限 450 拍。为免真的等十几分钟，
 * 这里把全局 setTimeout 换成「立刻推进」的桩，只保留事件循环让出。
 * 注意轮询用的是 `await new Promise(setTimeout)`，桩里不能同步 resolve
 * 成死循环风险 —— 用 setImmediate 让出一轮宏任务即可。
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return {
    ...actual,
    executeOAFiling: vi.fn(),
    getOAFilingSession: vi.fn(),
    getStampSession: vi.fn(),
    applyStamp: vi.fn(),
    getArchiveSession: vi.fn(),
    applyArchive: vi.fn(),
    executeCourtFiling: vi.fn(),
    getCourtFilingSession: vi.fn(),
  }
})

import {
  applyArchive,
  applyStamp,
  executeCourtFiling,
  executeOAFiling,
  getArchiveSession,
  getCourtFilingSession,
  getOAFilingSession,
  getStampSession,
} from '../api'
import { useCourtFiling, useOAArchive, useOAFiling, useOAStamp } from './use-auto-run'

const execOA = vi.mocked(executeOAFiling)
const pollOA = vi.mocked(getOAFilingSession)
const applyStampMock = vi.mocked(applyStamp)
const pollStamp = vi.mocked(getStampSession)
const applyArchiveMock = vi.mocked(applyArchive)
const pollArchive = vi.mocked(getArchiveSession)
const execCourt = vi.mocked(executeCourtFiling)
const pollCourt = vi.mocked(getCourtFilingSession)

const realSetTimeout = globalThis.setTimeout

/** 让出一轮宏任务（等价于 await 一次 setImmediate） */
const setImmediatePromise = () => new Promise<void>((r) => setImmediate(r))

beforeEach(() => {
  vi.clearAllMocks()
  // 轮询间隔与进度推进一律立刻触发：本 hook 的所有等待都只关心「发生了没有」，
  // 不关心真实时长（节奏由常量决定，换常量不需要改这些断言）。
  vi.stubGlobal('setTimeout', ((fn: () => void) => setImmediate(fn)) as unknown as typeof setTimeout)
})

afterEach(() => {
  vi.unstubAllGlobals()
  globalThis.setTimeout = realSetTimeout
})

describe('useOAFiling', () => {
  it('提交成功 → running → 轮询到 success 后停，ticks 记录轮询拍了多少下', async () => {
    execOA.mockResolvedValue({ id: 9, status: 'pending' } as never)
    pollOA
      .mockResolvedValueOnce({ id: 9, status: 'running' } as never)
      .mockResolvedValueOnce({ id: 9, status: 'success' } as never)

    const { result } = renderHook(() => useOAFiling())
    expect(result.current.state.phase).toBe('idle')

    await act(async () => {
      await result.current.run({ contract_id: 3 } as never)
    })

    expect(result.current.state.phase).toBe('done')
    expect(result.current.state.status).toBe('success')
    expect(result.current.state.error).toBeNull()
    expect(result.current.state.ticks).toBe(2)
    expect(result.current.state.session).toEqual({ id: 9, status: 'success' })
    // 载荷原样交给 api 层（hook 对内容一无所知）
    expect(execOA).toHaveBeenCalledWith({ contract_id: 3 })
    expect(pollOA).toHaveBeenNthCalledWith(1, 9)
  })

  it('failed / finished / completed / error 都算终态（后端 status 大小写与取值不统一）', async () => {
    for (const status of ['failed', 'FINISHED', 'Completed', 'ERROR']) {
      execOA.mockResolvedValue({ id: 1, status: 'pending' } as never)
      pollOA.mockReset()
      pollOA.mockResolvedValueOnce({ id: 1, status } as never)

      const { result } = renderHook(() => useOAFiling())
      await act(async () => {
        await result.current.run({})
      })

      expect(result.current.state.phase).toBe('done')
      // status 原样展示，前端不翻译后端语义
      expect(result.current.state.status).toBe(status)
      expect(result.current.state.ticks).toBe(1)
    }
  })

  it('后端没给 session_id：不进轮询，status 原样透出、phase 直接 done', async () => {
    execOA.mockResolvedValue({ id: null, status: 'success' } as never)

    const { result } = renderHook(() => useOAFiling())
    await act(async () => {
      await result.current.run({})
    })

    expect(result.current.state.phase).toBe('done')
    expect(result.current.state.status).toBe('success')
    expect(result.current.state.session).toBeNull()
    expect(pollOA).not.toHaveBeenCalled()
  })

  it('提交抛错：done + error，一个轮询都不发', async () => {
    execOA.mockRejectedValue(new Error('OA 凭证未配置'))

    const { result } = renderHook(() => useOAFiling())
    await act(async () => {
      await result.current.run({})
    })

    expect(result.current.state.phase).toBe('done')
    expect(result.current.state.error).toBe('OA 凭证未配置')
    expect(pollOA).not.toHaveBeenCalled()
  })

  it('轮询偶发抖动（< 10 次连续失败）不判死，恢复后照常跑到终态', async () => {
    execOA.mockResolvedValue({ id: 1, status: 'pending' } as never)
    pollOA
      .mockRejectedValueOnce(new Error('网络抖动'))
      .mockRejectedValueOnce(new Error('网络抖动'))
      .mockResolvedValueOnce({ id: 1, status: 'success' } as never)

    const { result } = renderHook(() => useOAFiling())
    await act(async () => {
      await result.current.run({})
    })

    expect(result.current.state.phase).toBe('done')
    expect(result.current.state.error).toBeNull()
    expect(result.current.state.status).toBe('success')
    // 失败的两拍也计进 ticks（界面用它展示「还在跑」）
    expect(result.current.state.ticks).toBe(3)
  })

  it('轮询连续失败到宽限（10 次）才判失败，并带最后一次的原因', async () => {
    execOA.mockResolvedValue({ id: 1, status: 'pending' } as never)
    pollOA.mockRejectedValue(new Error('会话不存在'))

    const { result } = renderHook(() => useOAFiling())
    await act(async () => {
      await result.current.run({})
    })

    expect(result.current.state.phase).toBe('done')
    expect(result.current.state.error).toBe('会话不存在')
    expect(pollOA).toHaveBeenCalledTimes(10)
  })

  it('轮询永不终态：到上限（450 拍）后判 timeout，不写 error', async () => {
    execOA.mockResolvedValue({ id: 1, status: 'pending' } as never)
    pollOA.mockResolvedValue({ id: 1, status: 'running' } as never)

    const { result } = renderHook(() => useOAFiling())
    await act(async () => {
      await result.current.run({})
    })

    // MAX_POLLS = 450：打满就停，phase 是 timeout 而不是 done
    expect(result.current.state.phase).toBe('timeout')
    expect(result.current.state.error).toBeNull()
    expect(result.current.state.ticks).toBe(450)
    expect(pollOA).toHaveBeenCalledTimes(450)
  })

  it('reset 回到 idle，清空 status / error / ticks', async () => {
    execOA.mockResolvedValue({ id: 1, status: 'success' } as never)
    pollOA.mockResolvedValueOnce({ id: 1, status: 'success' } as never)

    const { result } = renderHook(() => useOAFiling())
    await act(async () => {
      await result.current.run({})
    })
    expect(result.current.state.phase).toBe('done')

    act(() => result.current.reset())
    expect(result.current.state).toEqual({ phase: 'idle', session: null, status: '', error: null, ticks: 0 })
  })

  it('卸载后到达的轮询结果不再写状态（会触发 React 警告，且已无意义）', async () => {
    execOA.mockResolvedValue({ id: 1, status: 'pending' } as never)
    // 把第一拍轮询挂起：卸载发生在这拍返回之前
    let release!: (v: unknown) => void
    pollOA.mockReturnValueOnce(new Promise((r) => (release = r)) as never)

    const { result, unmount } = renderHook(() => useOAFiling())
    // 不 await run：它会一直挂着等第一拍轮询
    let done!: Promise<void>
    act(() => {
      done = result.current.run({})
    })
    // 让出宏任务直到第一拍轮询发出（提交 → running → 等一拍 → GET 会话）
    for (let i = 0; i < 20 && pollOA.mock.calls.length === 0; i++) await setImmediatePromise()
    expect(pollOA).toHaveBeenCalledTimes(1)

    unmount()
    release({ id: 1, status: 'success' })
    await done

    // alive=false 后循环直接 return：只有一拍轮询，没有被重写成 done/success
    expect(pollOA).toHaveBeenCalledTimes(1)
  })
})

describe('useOAStamp（入参是一条 file_path 字符串）', () => {
  it('把字符串包成 { file_path, site_name } 提交，并把会话裁成最小形状轮询', async () => {
    applyStampMock.mockResolvedValue({ id: 7, status: 'pending', error_message: '' } as never)
    pollStamp.mockResolvedValueOnce({ id: 7, status: 'success', error_message: '' } as never)

    const { result } = renderHook(() => useOAStamp('某某律所OA'))
    await act(async () => {
      await result.current.run('/case/起诉状.pdf')
    })

    expect(applyStampMock).toHaveBeenCalledWith({
      file_path: '/case/起诉状.pdf',
      site_name: '某某律所OA',
    })
    // 轮询返回的会话被裁成 { id, status, error_message } 三个字段
    expect(result.current.state.session).toEqual({ id: 7, status: 'success', error_message: '' })
    expect(result.current.state.phase).toBe('done')
  })

  it('siteName 默认空串（调用点没传时不上报站点名）', async () => {
    applyStampMock.mockResolvedValue({ id: 7, status: 'success' } as never)

    const { result } = renderHook(() => useOAStamp())
    await act(async () => {
      await result.current.run('/case/a.pdf')
    })

    expect(applyStampMock).toHaveBeenCalledWith({ file_path: '/case/a.pdf', site_name: '' })
  })
})

describe('useOAArchive（入参是 file_paths 数组）', () => {
  it('多条路径原样进 file_paths，可一次归档多份', async () => {
    applyArchiveMock.mockResolvedValue({ id: 8, status: 'pending' } as never)
    pollArchive.mockResolvedValueOnce({ id: 8, status: 'success' } as never)

    const { result } = renderHook(() => useOAArchive('某某律所OA'))
    const paths = ['/case/判决书.pdf', '/case/裁定书.pdf']
    await act(async () => {
      await result.current.run(paths)
    })

    expect(applyArchiveMock).toHaveBeenCalledWith({ file_paths: paths, site_name: '某某律所OA' })
    expect(result.current.state.phase).toBe('done')
    expect(result.current.state.status).toBe('success')
  })
})

describe('useCourtFiling（一张网）', () => {
  it('提交回包取 session_id；缺 status 时按 success 布尔兜底', async () => {
    execCourt.mockResolvedValue({ session_id: 12, success: true } as never)
    pollCourt.mockResolvedValueOnce({ session_id: 12, status: 'success' } as never)

    const { result } = renderHook(() => useCourtFiling())
    await act(async () => {
      await result.current.run({ case_id: 406 } as never)
    })

    // executeCourtFiling 的 status 兜底：r.status ?? (r.success ? 'success' : 'failed')
    expect(result.current.state.status).toBe('success')
    expect(result.current.state.phase).toBe('done')
    expect(pollCourt).toHaveBeenCalledWith(12)
  })

  it('提交回包 success=false 且无 status 时归一成 failed（不假装成功）', async () => {
    execCourt.mockResolvedValue({ session_id: 12, success: false } as never)
    pollCourt.mockResolvedValueOnce({ session_id: 12, status: undefined, success: false } as never)

    const { result } = renderHook(() => useCourtFiling())
    await act(async () => {
      await result.current.run({})
    })

    expect(result.current.state.status).toBe('failed')
    expect(result.current.state.phase).toBe('done')
  })

  it('一张网的 session 字段名是 session_id，缺了就不进轮询', async () => {
    execCourt.mockResolvedValue({ session_id: null, success: true } as never)

    const { result } = renderHook(() => useCourtFiling())
    await act(async () => {
      await result.current.run({})
    })

    expect(result.current.state.phase).toBe('done')
    expect(pollCourt).not.toHaveBeenCalled()
  })
})
