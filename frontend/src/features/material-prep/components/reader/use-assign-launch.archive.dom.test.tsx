// @vitest-environment jsdom
/**
 * 「归案后归档到案件文件夹」的接线测试（jsdom）。
 *
 * 守三件事：
 * 1. 勾选时才归档，且按 `splitRef` 分组、逐 job 调端点；没有 splitRef 的段跳过
 *    （人工切/并段、旧草稿在后端没有任务产物）；
 * 2. 段 → 入参映射：`doc_type` / `material_type` 取段名去扩展名，页区间取段的页；
 * 3. **归档失败绝不能影响归案成功** —— 归案 toast 与跳转照旧，归档失败只多一条
 *    warning。这条是本次改动的核心风险：归档是后加的附加动作，它挂了不能让律师
 *    以为归案也挂了（归案本身已经写库成功，重试会建出第二个案子）。
 */
import { act, renderHook } from '@testing-library/react'
import type { NavigateFunction } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  assignPack: vi.fn(),
  fetchAttachmentBytes: vi.fn(),
  archiveSplitToCaseFolder: vi.fn(),
}))
vi.mock('../../api', () => api)

const toastMock = vi.hoisted(() => ({
  loading: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
}))
vi.mock('sonner', () => ({ toast: toastMock }))

import type { DraftState } from '../../types'
import { setArchiveToCaseFolderEnabled, useAssignLaunch } from './use-assign-launch'

/** 段的页引用必须是单源内**逐页连续**的（归案前会校验，见 isSingleSourceContiguous） */
function pages(mi: number, from: number, to: number) {
  return Array.from({ length: to - from + 1 }, (_, i) => ({ mi, p: from + i }))
}

/** 两个拆分任务（job-A 两段、job-B 一段）+ 一个没有 splitRef 的人工段 */
function draftWithSegs(): DraftState {
  return {
    mats: [],
    infos: [],
    segs: [
      {
        id: 'seg-1',
        t: '起诉状',
        fn: '张某-起诉状',
        refs: pages(0, 1, 3),
        manual: false,
        splitRef: { jobId: 'job-A', pk: 11 },
      },
      {
        // 段类型为空 → 退回文件名，并去掉扩展名
        id: 'seg-2',
        t: '',
        fn: '证据目录.pdf',
        refs: pages(0, 4, 9),
        manual: false,
        splitRef: { jobId: 'job-A', pk: 12 },
      },
      {
        id: 'seg-3',
        t: '庭审笔录',
        fn: '张某-庭审笔录',
        refs: pages(0, 10, 12),
        manual: false,
        splitRef: { jobId: 'job-B', pk: 21 },
      },
      {
        // 人工切出来的段：后端没有任务产物，不传
        id: 'seg-4',
        t: '手工段',
        fn: '张某-手工段',
        refs: pages(0, 13, 13),
        manual: true,
      },
    ],
  }
}

const ASSIGN_RESULT = {
  caseId: 42,
  caseName: '张某诉某公司买卖合同纠纷一案',
  contractId: null,
  boundCount: 2,
  unsplitCount: 0,
}

const ARCHIVE_RESULT = { root: '', written: [], duplicates: [], skipped: [], notice_path: '' }

function renderLaunch() {
  const navigate = vi.fn()
  const { result } = renderHook(() =>
    useAssignLaunch({
      draft: draftWithSegs(),
      messageId: 7,
      navigate: navigate as unknown as NavigateFunction,
      setAssignOpen: vi.fn(),
      setAssign: vi.fn(),
      close: vi.fn(),
      setLaunchFile: vi.fn(),
    }),
  )
  return { result, navigate }
}

async function confirmAssign(result: { current: ReturnType<typeof useAssignLaunch> }) {
  await act(async () => {
    await result.current.onAssignConfirm({ target: 'existing', caseId: 42 })
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  setArchiveToCaseFolderEnabled(true)
  api.assignPack.mockResolvedValue(ASSIGN_RESULT)
  api.archiveSplitToCaseFolder.mockResolvedValue(ARCHIVE_RESULT)
})

describe('onAssignConfirm：归案成功后归档到案件文件夹', () => {
  it('按 splitRef 分组逐 job 归档，没有 splitRef 的段跳过', async () => {
    const { result, navigate } = renderLaunch()

    await confirmAssign(result)

    expect(api.archiveSplitToCaseFolder).toHaveBeenCalledTimes(2)
    expect(api.archiveSplitToCaseFolder).toHaveBeenNthCalledWith(1, 'job-A', 42, [
      { page_start: 1, page_end: 3, doc_type: '起诉状', material_type: '起诉状' },
      { page_start: 4, page_end: 9, doc_type: '证据目录', material_type: '证据目录' },
    ])
    expect(api.archiveSplitToCaseFolder).toHaveBeenNthCalledWith(2, 'job-B', 42, [
      { page_start: 10, page_end: 12, doc_type: '庭审笔录', material_type: '庭审笔录' },
    ])
    expect(navigate).toHaveBeenCalledWith('/bank-litigation/42')
  })

  it('未勾选「同时归档到案件文件夹」时不归档，归案照常跳转', async () => {
    setArchiveToCaseFolderEnabled(false)
    const { result, navigate } = renderLaunch()

    await confirmAssign(result)

    expect(api.archiveSplitToCaseFolder).not.toHaveBeenCalled()
    expect(navigate).toHaveBeenCalledWith('/bank-litigation/42')
  })

  it('归档失败仍归案成功：只 toast.warning，归案 toast 与跳转照旧，且不误报归案失败', async () => {
    api.archiveSplitToCaseFolder.mockRejectedValue(new Error('500 Internal Server Error'))

    const { result, navigate } = renderLaunch()

    await confirmAssign(result)

    expect(toastMock.success).toHaveBeenCalledWith(
      expect.stringContaining('已归案'),
      expect.anything(),
    )
    // 两个 job 各试一次：一个挂了不跳过其余
    expect(api.archiveSplitToCaseFolder).toHaveBeenCalledTimes(2)
    expect(toastMock.warning).toHaveBeenCalledTimes(2)
    expect(toastMock.warning.mock.calls[0]![0]).toContain('归档到案件文件夹失败')
    expect(toastMock.error).not.toHaveBeenCalled()
    expect(navigate).toHaveBeenCalledWith('/bank-litigation/42')
  })
})
