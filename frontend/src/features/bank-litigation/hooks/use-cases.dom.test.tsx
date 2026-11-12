// @vitest-environment jsdom
/**
 * 案件读取 hooks 单测（jsdom）。
 *
 * mock 只打 api 层（../api），覆盖：
 * - useLoad 的三态骨架：初值 loading → 数据到位 → reload 再拉一次
 * - 失败落到 error 且 data 置空（不给旧值）
 * - caseId 为 null 时不发请求，直接落到「未指定案件」错误
 * - deps 变化（换 caseId）会重新拉
 * - useConflictCheck 是**手动触发**（POST 有副作用会写审计），进页面不许自动跑
 *
 * 为什么值得测「不发请求」：这几个 hook 决定页面上「起诉条件/材料齐备」的数字，
 * 没有 caseId 却发了 listCases 之类的请求，会让界面显示别的案子的结论。
 */
import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return {
    ...actual,
    listCases: vi.fn(),
    getCase: vi.fn(),
    getMaterialStatus: vi.fn(),
    getReadiness: vi.fn(),
    getCaseFilingInfo: vi.fn(),
    listOAConfigs: vi.fn(),
    runConflictCheck: vi.fn(),
  }
})

import {
  getCase,
  getCaseFilingInfo,
  getMaterialStatus,
  getReadiness,
  listCases,
  listOAConfigs,
  runConflictCheck,
} from '../api'
import {
  useCase,
  useCaseFilingInfo,
  useCases,
  useConflictCheck,
  useMaterialStatus,
  useOAConfigs,
  useReadiness,
} from './use-cases'

const listCasesMock = vi.mocked(listCases)
const getCaseMock = vi.mocked(getCase)
const getMaterialStatusMock = vi.mocked(getMaterialStatus)
const getReadinessMock = vi.mocked(getReadiness)
const getCaseFilingInfoMock = vi.mocked(getCaseFilingInfo)
const listOAConfigsMock = vi.mocked(listOAConfigs)
const runConflictCheckMock = vi.mocked(runConflictCheck)

beforeEach(() => {
  vi.clearAllMocks()
})

describe('useLoad 骨架（以 useCases 为入口）', () => {
  it('先 loading 后给数据，且 natural 一次只拉一次', async () => {
    listCasesMock.mockResolvedValue([{ id: 1 }, { id: 2 }] as never)
    const { result } = renderHook(() => useCases())

    expect(result.current.loading).toBe(true)
    expect(result.current.data).toBeNull()

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data).toHaveLength(2)
    expect(result.current.error).toBeNull()
    expect(listCasesMock).toHaveBeenCalledTimes(1)
  })

  it('失败时 error 有文案、data 为空 —— 不留旧值给界面算结论', async () => {
    listCasesMock.mockRejectedValue(new Error('网络断了'))
    const { result } = renderHook(() => useCases())

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data).toBeNull()
    expect(result.current.error).toBe('网络断了')
  })

  it('reload 会重新拉一次，成功后清掉上一次的 error', async () => {
    listCasesMock.mockRejectedValueOnce(new Error('首拉失败')).mockResolvedValueOnce([{ id: 7 }] as never)
    const { result } = renderHook(() => useCases())

    await waitFor(() => expect(result.current.error).toBe('首拉失败'))

    act(() => result.current.reload())
    await waitFor(() => expect(result.current.data).toEqual([{ id: 7 }]))
    expect(result.current.error).toBeNull()
    expect(listCasesMock).toHaveBeenCalledTimes(2)
  })
})

describe('caseId 为空时的一族 hook', () => {
  it('caseId=null 时一律不发请求，直接报「未指定案件」', async () => {
    const cases = renderHook(() => useCase(null))
    const material = renderHook(() => useMaterialStatus(null))
    const readiness = renderHook(() => useReadiness(null))
    const filingInfo = renderHook(() => useCaseFilingInfo(null))

    for (const h of [cases, material, readiness, filingInfo]) {
      await waitFor(() => expect(h.result.current.loading).toBe(false))
      expect(h.result.current.error).toBe('未指定案件')
      expect(h.result.current.data).toBeNull()
    }
    expect(getCaseMock).not.toHaveBeenCalled()
    expect(getMaterialStatusMock).not.toHaveBeenCalled()
    expect(getReadinessMock).not.toHaveBeenCalled()
    expect(getCaseFilingInfoMock).not.toHaveBeenCalled()
  })

  it('有 caseId 时按 id 请求，把回包原样交给调用方', async () => {
    getCaseMock.mockResolvedValue({ id: 406, case_name: '某某一案' } as never)
    const { result } = renderHook(() => useCase(406))

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(getCaseMock).toHaveBeenCalledWith(406)
    expect(result.current.data).toEqual({ id: 406, case_name: '某某一案' })
  })

  it('换 caseId（deps 变化）会按新 id 重新拉', async () => {
    getReadinessMock.mockResolvedValue({ ready: true } as never)
    const { result, rerender } = renderHook(({ id }: { id: number }) => useReadiness(id), {
      initialProps: { id: 1 },
    })

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(getReadinessMock).toHaveBeenLastCalledWith(1)

    rerender({ id: 2 })
    await waitFor(() => expect(getReadinessMock).toHaveBeenCalledTimes(2))
    expect(getReadinessMock).toHaveBeenLastCalledWith(2)
  })
})

describe('useOAConfigs', () => {
  it('拉当前律师配置了凭证的 OA 站点，不需要任何入参', async () => {
    listOAConfigsMock.mockResolvedValue([{ id: 'abc', name: '某某律所OA' }] as never)
    const { result } = renderHook(() => useOAConfigs())

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data).toEqual([{ id: 'abc', name: '某某律所OA' }])
  })
})

describe('useConflictCheck（手动触发）', () => {
  it('进页面不自动跑 —— 冲突预检会写审计，不该在打开页面时留记录', async () => {
    renderHook(() => useConflictCheck(406))
    // 给 effect 一轮机会：如果误写成 useLoad，这里会看到调用
    await Promise.resolve()
    expect(runConflictCheckMock).not.toHaveBeenCalled()
  })

  it('没 caseId 时 run 是空操作，不会打请求', async () => {
    const { result } = renderHook(() => useConflictCheck(null))
    await act(async () => {
      await result.current.run()
    })
    expect(runConflictCheckMock).not.toHaveBeenCalled()
    expect(result.current.loading).toBe(false)
  })

  it('有 caseId 时 run 走 POST 并把结果落到 data，结束后 loading 归 false', async () => {
    runConflictCheckMock.mockResolvedValue({ level: 'neutral', items: [] } as never)
    const { result } = renderHook(() => useConflictCheck(406))

    expect(result.current.loading).toBe(false)
    let pending!: Promise<void>
    act(() => {
      pending = result.current.run()
    })
    // run 期间 loading 为 true（界面要能显示「预检中」）
    expect(result.current.loading).toBe(true)

    await act(async () => {
      await pending
    })
    expect(result.current.loading).toBe(false)
    expect(result.current.data).toEqual({ level: 'neutral', items: [] })
    expect(runConflictCheckMock).toHaveBeenCalledWith(406)
  })

  it('run 失败时落 error 且 data 为空', async () => {
    runConflictCheckMock.mockRejectedValue(new Error('预检服务超时'))
    const { result } = renderHook(() => useConflictCheck(406))

    await act(async () => {
      await result.current.run()
    })
    expect(result.current.error).toBe('预检服务超时')
    expect(result.current.data).toBeNull()
  })

  it('reset 把状态清回初始（重跑前先清，避免旧结论挂在屏幕上）', async () => {
    runConflictCheckMock.mockResolvedValue({ level: 'red' } as never)
    const { result } = renderHook(() => useConflictCheck(406))

    await act(async () => {
      await result.current.run()
    })
    expect(result.current.data).toEqual({ level: 'red' })

    act(() => result.current.reset())
    expect(result.current.data).toBeNull()
    expect(result.current.error).toBeNull()
    expect(result.current.loading).toBe(false)
  })
})
