// @vitest-environment jsdom
/**
 * RecognizeDialog × StrictMode 回归（真实 useRecognize + 真实 usePollSession，只 mock api 层）。
 *
 * 2026-10-20 事故：记一笔粘贴文书后弹窗永停「正在上传文书…」，而后端任务已完成。
 * 根因是开发态 StrictMode 把挂载 effect 跑成 setup→cleanup→setup，usePollSession 的
 * cleanup 不可逆地让会话失效；弹窗用 submittedFile ref 防重，第二次 setup 不会再提交，
 * 唯一一次上传返回时 lease 已 stale 被静默吞掉。
 *
 * 既有的 RecognizeDialog.dom.test 把 useRecognize 整个 mock 掉、use-recognize.dom.test
 * 从测试体直接调 submit 且不带 StrictMode，两者都碰不到这条路径，故单独成文件。
 */
import { StrictMode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api', () => ({
  recognizeFile: vi.fn(),
  getTask: vi.fn(),
  bindTask: vi.fn(),
  confirmDates: vi.fn(),
  revokeDate: vi.fn(),
  searchCasesForBinding: vi.fn(),
}))

import { getTask, recognizeFile, searchCasesForBinding } from '../api'
import type { TaskOut } from '../types'

import { RecognizeDialog } from './RecognizeDialog'

const recognizeMock = vi.mocked(recognizeFile)
const getTaskMock = vi.mocked(getTask)
const searchCasesMock = vi.mocked(searchCasesForBinding)

function makeTask(partial: Partial<TaskOut> = {}): TaskOut {
  return {
    task_id: 5,
    status: 'success',
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
    started_at: null,
    elapsed_seconds: null,
    stalled: false,
    ...partial,
  }
}

function renderStrict(file: File) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <RecognizeDialog open onClose={vi.fn()} onSaved={vi.fn()} file={file} />
      </QueryClientProvider>
    </StrictMode>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  searchCasesMock.mockResolvedValue([])
})

describe('RecognizeDialog × StrictMode（文件模式）', () => {
  const file = new File(['x'], 'summons.pdf', { type: 'application/pdf' })

  it('挂载双调用后，唯一一次上传返回仍推进到识别终态，且不重复上传', async () => {
    recognizeMock.mockResolvedValue({ task_id: 5 })
    getTaskMock.mockResolvedValue(makeTask({ status: 'success' }))

    renderStrict(file)
    expect(screen.getByText('正在上传文书…')).toBeTruthy()

    await waitFor(() => expect(screen.getByText('关联案件')).toBeTruthy())
    expect(screen.queryByText('正在上传文书…')).toBeNull()
    // ref 防重仍然生效：StrictMode 的第二次 setup 不能变成第二次上传（后端会多出一个识别任务）
    expect(recognizeMock).toHaveBeenCalledTimes(1)
    expect(getTaskMock).toHaveBeenCalledWith(5)
  })

  it('挂载双调用后，上传失败仍能落到 error 态而不是永停上传中', async () => {
    recognizeMock.mockRejectedValue(new Error('415'))

    renderStrict(file)
    await waitFor(() => expect(screen.getByText('上传失败，请检查文件格式或稍后重试')).toBeTruthy())
    expect(recognizeMock).toHaveBeenCalledTimes(1)
    expect(getTaskMock).not.toHaveBeenCalled()
  })
})
