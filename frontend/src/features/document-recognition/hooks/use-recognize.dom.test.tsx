// @vitest-environment jsdom
/**
 * useRecognize 轮询编排单测（jsdom + fake timers）。
 *
 * mock 只打 api 层（../api = document-recognition/api.ts）：
 * recognizeFile / getTask。覆盖提交、轮询推进到 success/failed 终态、
 * 404 宽限（连续 15 轮才判死、宽限内可恢复）、非 404 单轮失败不判死、上传失败与 reset。
 *
 * 注意：submit 内部 `await poll(id)` 会陪轮询到终态才 resolve，
 * 测试不能 `await submit(...)`，否则陪 fake timer 一起挂——统一用 startSubmit
 * 「发起后冲微任务」再按需推进计时器。
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api', () => ({
  recognizeFile: vi.fn(),
  getTask: vi.fn(),
}))

import { getTask, recognizeFile } from '../api'
import { RECOGNIZE_POLL_MS } from '../constants'
import type { TaskOut } from '../types'

import { useRecognize } from './use-recognize'

// 被 vi.mock 的模块函数经 vi.mocked 拿到带 mock 属性的类型视图
const recognizeMock = vi.mocked(recognizeFile)
const getTaskMock = vi.mocked(getTask)

const TICK = RECOGNIZE_POLL_MS

function makeTask(partial: Partial<TaskOut>): TaskOut {
  return {
    task_id: 5,
    status: 'processing',
    file_path: null,
    file_url: null,
    recognition: null,
    binding: null,
    date_candidates: [],
    contacts: [],
    address: null,
    recommendations: [],
    binding_mode: 'standalone',
    date_confirmation_status: null,
    error_message: null,
    created_at: '2026-10-01T10:00:00',
    finished_at: null,
    ...partial,
  }
}

/** ky 404 的错误形状（use-recognize 从 e.response.status 判宽限） */
function httpError(status: number) {
  return Object.assign(new Error(`HTTP ${status}`), { response: { status } })
}

type HookResult = ReturnType<typeof useRecognize>

function setup() {
  return renderHook(() => useRecognize())
}

/** 发起 submit 但不等待（其内部 await poll 会陪到终态），只冲微任务让上传落地 */
async function startSubmit(result: { current: HookResult }, file = new File(['x'], 'summons.pdf')) {
  await act(async () => {
    void result.current.submit(file)
    await vi.advanceTimersByTimeAsync(0)
  })
}

async function tick(ms = TICK) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

async function flush() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0)
  })
}

const HINT_UPLOADING = '正在上传文书…'
const HINT_POLLING = '识别中（文本提取 + LLM 分析），通常 5-30 秒…'

beforeEach(() => {
  vi.clearAllMocks()
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useRecognize 提交与终态', () => {
  it('初始为 idle：无任务、无错误、hint 为空', () => {
    const { result } = setup()
    expect(result.current.phase).toBe('idle')
    expect(result.current.hint).toBe('')
    expect(result.current.task).toBeNull()
    expect(result.current.error).toBeNull()
  })

  it('submit：submitting（上传 hint）→ 拿到 task_id 后进入 polling（识别 hint）', async () => {
    let resolveUpload!: (v: { task_id: number }) => void
    recognizeMock.mockReturnValue(
      new Promise<{ task_id: number }>((resolve) => {
        resolveUpload = resolve
      }),
    )
    getTaskMock.mockResolvedValue(makeTask({ status: 'processing' }))
    const { result } = setup()

    // 上传未返回：停留在 submitting，未打详情接口
    await act(async () => {
      void result.current.submit(new File(['x'], 'summons.pdf'))
    })
    expect(result.current.phase).toBe('submitting')
    expect(result.current.hint).toBe(HINT_UPLOADING)
    expect(getTask).not.toHaveBeenCalled()

    await act(async () => {
      resolveUpload({ task_id: 5 })
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(result.current.phase).toBe('polling')
    expect(result.current.hint).toBe(HINT_POLLING)
    expect(getTask).toHaveBeenCalledWith(5)
  })

  it('轮询推进：pending → success 终态，task 落地且 hint 清空', async () => {
    recognizeMock.mockResolvedValue({ task_id: 5 })
    const success = makeTask({ status: 'success' })
    getTaskMock.mockResolvedValueOnce(makeTask({ status: 'pending' })).mockResolvedValueOnce(success)
    const { result } = setup()

    await startSubmit(result)
    expect(result.current.phase).toBe('polling')

    await tick()
    expect(result.current.phase).toBe('ready')
    expect(result.current.task).toEqual(success)
    expect(result.current.hint).toBe('')
    expect(result.current.error).toBeNull()
  })

  it('轮询到 failed：优先展示后端 error_message', async () => {
    recognizeMock.mockResolvedValue({ task_id: 5 })
    getTaskMock.mockResolvedValue(makeTask({ status: 'failed', error_message: 'LLM 解析超时' }))
    const { result } = setup()

    await startSubmit(result)
    await flush()
    expect(result.current.phase).toBe('error')
    expect(result.current.error).toBe('LLM 解析超时')
  })

  it('轮询到 failed 且无 error_message：兜底文案「识别失败」', async () => {
    recognizeMock.mockResolvedValue({ task_id: 5 })
    getTaskMock.mockResolvedValue(makeTask({ status: 'failed', error_message: null }))
    const { result } = setup()

    await startSubmit(result)
    await flush()
    expect(result.current.phase).toBe('error')
    expect(result.current.error).toBe('识别失败')
  })

  it('上传失败：不进入轮询，error 为上传失败文案', async () => {
    recognizeMock.mockRejectedValue(new Error('415'))
    const { result } = setup()

    await act(async () => {
      void result.current.submit(new File(['x'], 'bad.exe'))
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(result.current.phase).toBe('error')
    expect(result.current.error).toBe('上传失败，请检查文件格式或稍后重试')
    expect(getTask).not.toHaveBeenCalled()
  })

  it('reset：轮询中直接回 idle，且旧轮询不再打接口', async () => {
    recognizeMock.mockResolvedValue({ task_id: 5 })
    getTaskMock.mockResolvedValue(makeTask({ status: 'processing' }))
    const { result } = setup()

    await startSubmit(result)
    expect(result.current.phase).toBe('polling')

    act(() => {
      result.current.reset()
    })
    expect(result.current.phase).toBe('idle')
    expect(result.current.task).toBeNull()
    const calls = getTaskMock.mock.calls.length
    await tick(TICK * 3)
    expect(getTaskMock.mock.calls.length).toBe(calls)
  })
})

describe('useRecognize 404 宽限与容错', () => {
  it('404 连续达宽限上限（15 轮）才判死，文案指向 worker 未运行', async () => {
    recognizeMock.mockResolvedValue({ task_id: 5 })
    getTaskMock.mockRejectedValue(httpError(404))
    const { result } = setup()

    await startSubmit(result)
    // 第 1 轮 404 在 startSubmit 时已发生；每轮之间 sleep 2s，第 15 轮 404 后直接终态
    await tick(TICK * 14)
    expect(result.current.phase).toBe('error')
    expect(result.current.error).toBe('识别任务排队后没有执行起来——多为后台 worker 未运行，请稍后重试')
    expect(getTaskMock.mock.calls.length).toBe(15)
  })

  it('404 在宽限内恢复（后端落库完成）→ 继续轮询到 success，不判死', async () => {
    recognizeMock.mockResolvedValue({ task_id: 5 })
    getTaskMock
      .mockRejectedValueOnce(httpError(404))
      .mockRejectedValueOnce(httpError(404))
      .mockResolvedValueOnce(makeTask({ status: 'processing' }))
      .mockResolvedValueOnce(makeTask({ status: 'success' }))
    const { result } = setup()

    await startSubmit(result)
    await tick(TICK * 3)
    expect(result.current.phase).toBe('ready')
    expect(result.current.error).toBeNull()
  })

  it('非 404 的单轮失败不判死：继续轮询直到 success', async () => {
    recognizeMock.mockResolvedValue({ task_id: 5 })
    getTaskMock
      .mockRejectedValueOnce(httpError(500))
      .mockResolvedValueOnce(makeTask({ status: 'success' }))
    const { result } = setup()

    await startSubmit(result)
    await tick(TICK * 2)
    expect(result.current.phase).toBe('ready')
  })
})

describe('useRecognize 重提交竞态回归', () => {
  it('重提交：旧任务在飞的轮询响应迟到，也不得把旧终态写进 state 覆盖新提交', async () => {
    // 第一次提交拿任务 5，第二次拿任务 6
    recognizeMock.mockResolvedValueOnce({ task_id: 5 }).mockResolvedValueOnce({ task_id: 6 })
    const oldTask = makeTask({ task_id: 5, status: 'success' })
    let resolveOld!: (v: TaskOut) => void
    getTaskMock.mockImplementation((id: number) => {
      if (id === 5) {
        // 旧任务的首轮查询悬住：模拟「正在 await 网络」的旧轮询循环
        return new Promise<TaskOut>((resolve) => {
          resolveOld = resolve
        })
      }
      return Promise.resolve(makeTask({ task_id: 6, status: 'failed', error_message: '新任务失败了' }))
    })

    const { result } = setup()
    await startSubmit(result)
    expect(result.current.phase).toBe('polling')
    expect(getTask).toHaveBeenCalledWith(5)

    // 旧查询还在飞时再提交：旧会话即刻失效
    await startSubmit(result, new File(['y'], 'summons2.pdf'))
    expect(result.current.phase).toBe('error')
    expect(result.current.error).toBe('新任务失败了')

    // 旧任务的 success 终态此刻才返回——旧循环醒来必须自检退出，不写任何 state
    await act(async () => {
      resolveOld(oldTask)
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(result.current.phase).toBe('error')
    expect(result.current.error).toBe('新任务失败了')
    expect(result.current.task).toBeNull()

    // 旧循环彻底死透：继续走表也不会再查任务 5
    const callsWith5 = getTaskMock.mock.calls.filter(([id]) => id === 5).length
    await tick(TICK * 3)
    expect(getTaskMock.mock.calls.filter(([id]) => id === 5).length).toBe(callsWith5)
  })

  it('重提交后旧循环停止轮询旧任务 id：计时器推进只服务新任务', async () => {
    recognizeMock.mockResolvedValueOnce({ task_id: 5 }).mockResolvedValueOnce({ task_id: 6 })
    // 两个任务都永远 processing（旧循环若未被会话失效，会一直打任务 5 的查询）
    getTaskMock.mockImplementation((id: number) =>
      Promise.resolve(makeTask({ task_id: id, status: 'processing' })),
    )

    const { result } = setup()
    await startSubmit(result)
    await tick(TICK * 2)
    expect(getTask).toHaveBeenCalledWith(5)

    await startSubmit(result, new File(['y'], 'summons2.pdf'))
    const callsWith5 = getTaskMock.mock.calls.filter(([id]) => id === 5).length
    await tick(TICK * 5)
    expect(getTask).toHaveBeenCalledWith(6)
    expect(getTaskMock.mock.calls.filter(([id]) => id === 5).length).toBe(callsWith5)
    expect(result.current.phase).toBe('polling')
  })
})
