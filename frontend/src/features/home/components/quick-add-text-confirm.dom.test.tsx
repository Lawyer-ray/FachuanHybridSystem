// @vitest-environment jsdom
/**
 * QuickAdd 文字路径部分成功的回归测试（jsdom）。
 *
 * 背景（2026-10 审查 H-P1-2 / D-P2-3）：confirmTextReminders 逐条
 * POST /reminders/create。此前串行 await 中途失败时，前面已建成功的提醒
 * 不会从 textRows 里移除，用户再点「记一笔」会把它们重复创建一遍。
 *
 * 做法：mock document-recognition 域，从 RecognizeDialogLazy 的 props 里
 * 取到 onConfirmText（即 confirmTextReminders），直接调用并断言行为。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('sonner', () => ({
  toast: { info: vi.fn(), success: vi.fn(), warning: vi.fn(), error: vi.fn() },
}))

const parseMock = vi.hoisted(() => vi.fn())
const createMock = vi.hoisted(() => vi.fn())
const captured = vi.hoisted(() => ({ onConfirmText: null as null | ((rows: unknown[]) => Promise<number>) }))

vi.mock('../api', () => ({
  createReminder: (...a: unknown[]) => createMock(...a),
  listInbox: vi.fn(async () => []),
  parseReminder: (...a: unknown[]) => parseMock(...a),
  HOME_INBOX_KEY: ['home', 'inbox'],
}))

vi.mock('@/features/document-recognition', () => ({
  preloadRecognizeDialog: vi.fn(),
  fileRejectReason: () => null,
  rowsFromParsed: (parsed: unknown[]) => parsed,
  RecognizeDialogLazy: (props: { onConfirmText: (rows: unknown[]) => Promise<number> }) => {
    captured.onConfirmText = props.onConfirmText
    return <div data-testid="recognize-dialog-stub" />
  },
}))

import { toast } from 'sonner'

import { QuickAdd } from './SideCards'

function candidate(key: string) {
  return {
    key,
    candidateId: null,
    checked: true,
    dueLocal: '2026-10-20T09:00',
    reminderType: 'hearing',
    confidence: null,
    status: 'pending',
    contextText: '',
    label: key,
    content: key,
  }
}

async function openTextDialog(rows: unknown[]) {
  parseMock.mockResolvedValue(rows)
  render(<QuickAdd onAdded={vi.fn()} />)
  const input = screen.getByPlaceholderText(/快速记一笔/)
  fireEvent.change(input, { target: { value: '2026-10-20 09:00 开庭' } })
  fireEvent.click(screen.getByRole('button', { name: '记一笔' }))
  await waitFor(() => expect(captured.onConfirmText).not.toBeNull())
  return captured.onConfirmText!
}

beforeEach(() => {
  vi.clearAllMocks()
  captured.onConfirmText = null
})

describe('QuickAdd 文字路径', () => {
  it('全部成功：返回创建条数并清空输入', async () => {
    createMock.mockResolvedValue({})
    const onConfirm = await openTextDialog([candidate('a'), candidate('b')])

    const created = await onConfirm([candidate('a'), candidate('b')])
    expect(created).toBe(2)
    expect(createMock).toHaveBeenCalledTimes(2)
  })

  it('部分失败：已成功的行不再留在待提交列表，重试不会重复创建', async () => {
    // 第 1 条成功、第 2 条失败
    createMock.mockResolvedValueOnce({}).mockRejectedValueOnce(new Error('第 2 条失败'))
    const onConfirm = await openTextDialog([candidate('a'), candidate('b')])

    const created = await onConfirm([candidate('a'), candidate('b')])
    expect(created).toBe(1)
    expect(toast.warning).toHaveBeenCalled()

    // 关键断言：用户重试时若拿到的是「只剩失败行」，已成功的 a 不会被再创建一次
    createMock.mockClear()
    createMock.mockResolvedValue({})
    const retryRows = [candidate('b')]
    const retried = await onConfirm(retryRows)
    expect(retried).toBe(1)
    expect(createMock).toHaveBeenCalledTimes(1)
    expect(createMock).toHaveBeenCalledWith(expect.objectContaining({ content: 'b' }))
  })
})

// ============ submitText 解析分支（覆盖率补测） ============

describe('QuickAdd submitText', () => {
  function typeAndSubmit(value: string) {
    const input = screen.getByPlaceholderText(/快速记一笔/)
    fireEvent.change(input, { target: { value } })
    fireEvent.click(screen.getByRole('button', { name: '记一笔' }))
    return input
  }

  it('空文本：提示用法且不调用 parseReminder', async () => {
    const { unmount } = render(<QuickAdd onAdded={vi.fn()} />)
    typeAndSubmit('   ')

    await waitFor(() => expect(toast.info).toHaveBeenCalledWith(expect.stringContaining('先写一句')))
    expect(parseMock).not.toHaveBeenCalled()
    unmount()
  })

  it('解析出候选：打开确认弹窗', async () => {
    parseMock.mockResolvedValue([candidate('a')])
    const { unmount } = render(<QuickAdd onAdded={vi.fn()} />)
    typeAndSubmit('2026-10-20 09:00 开庭')

    await waitFor(() => expect(parseMock).toHaveBeenCalled())
    await waitFor(() => expect(screen.getByTestId('recognize-dialog-stub')).toBeTruthy())
    unmount()
  })

  it('解析不出日期：警告且不开弹窗', async () => {
    parseMock.mockResolvedValue([])
    const { unmount } = render(<QuickAdd onAdded={vi.fn()} />)
    typeAndSubmit('没有日期的句子')

    await waitFor(() => expect(toast.warning).toHaveBeenCalledWith(expect.stringContaining('没能识别出日期')))
    expect(screen.queryByTestId('recognize-dialog-stub')).toBeNull()
    unmount()
  })

  it('解析抛错：错误提示', async () => {
    parseMock.mockRejectedValue(new Error('后端挂了'))
    const { unmount } = render(<QuickAdd onAdded={vi.fn()} />)
    typeAndSubmit('2026-10-20 开庭')

    await waitFor(() => expect(toast.error).toHaveBeenCalled())
    unmount()
  })

  it('解析中按钮禁用（防重入）', async () => {
    let release: (v: unknown[]) => void = () => {}
    parseMock.mockReturnValue(
      new Promise<unknown[]>((r) => {
        release = r
      }),
    )
    const { unmount } = render(<QuickAdd onAdded={vi.fn()} />)
    typeAndSubmit('2026-10-20 开庭')

    await waitFor(() => {
      const btn = screen.getByRole('button', { name: /记一笔/ }) as HTMLButtonElement
      expect(btn.disabled).toBe(true)
    })
    release([])
    unmount()
  })
})

// ============ 部分失败分支与关闭（覆盖率补测） ============

describe('QuickAdd confirmTextReminders 部分失败', () => {
  async function openDialog() {
    parseMock.mockResolvedValue([candidate('a'), candidate('b')])
    const utils = render(<QuickAdd onAdded={vi.fn()} />)
    const input = screen.getByPlaceholderText(/快速记一笔/)
    fireEvent.change(input, { target: { value: '2026-10-20 09:00 开庭' } })
    fireEvent.click(screen.getByRole('button', { name: '记一笔' }))
    await waitFor(() => expect(captured.onConfirmText).not.toBeNull())
    return { ...utils, onConfirm: captured.onConfirmText! }
  }

  it('部分失败：warning 提示成功数与失败数', async () => {
    createMock.mockResolvedValueOnce({}).mockRejectedValueOnce(new Error('第二条失败'))
    const { unmount, onConfirm } = await openDialog()

    const created = await onConfirm([candidate('a'), candidate('b')])
    expect(created).toBe(1)
    expect(toast.warning).toHaveBeenCalledWith(expect.stringContaining('1 条未写入'))
    unmount()
  })

  it('全部成功：清空输入框', async () => {
    createMock.mockResolvedValue({})
    const { unmount, onConfirm } = await openDialog()

    await onConfirm([candidate('a'), candidate('b')])
    // 清空是异步 state 更新，等一拍再断言
    await waitFor(() => {
      const input = screen.getByPlaceholderText(/快速记一笔/) as HTMLInputElement
      expect(input.value).toBe('')
    })
    unmount()
  })

  it('全部失败：不清空输入且提示全部未写入', async () => {
    createMock.mockRejectedValue(new Error('全失败'))
    const { unmount, onConfirm } = await openDialog()

    const created = await onConfirm([candidate('a')])
    expect(created).toBe(0)
    expect(toast.warning).toHaveBeenCalledWith(expect.stringContaining('0 条已加入'))
    unmount()
  })
})

describe('QuickAdd 关闭与回车', () => {
  beforeEach(() => {
    createMock.mockResolvedValue({})
    parseMock.mockResolvedValue([candidate('a')])
  })

  it('文件态点「识别并确认」走 closeDialog（清空文件与输入）', async () => {
    const { container, unmount } = render(<QuickAdd onAdded={vi.fn()} />)
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(fileInput, { target: { files: [new File(['x'], 'f.pdf')] } })
    await waitFor(() => expect(screen.getByText('f.pdf')).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: '识别并确认' }))
    await waitFor(() => expect(screen.queryByText('f.pdf')).toBeNull())
    unmount()
  })

  it('输入框回车触发提交', async () => {
    const { unmount } = render(<QuickAdd onAdded={vi.fn()} />)
    const input = screen.getByPlaceholderText(/快速记一笔/)
    fireEvent.change(input, { target: { value: '2026-10-20 开会' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    await waitFor(() => expect(parseMock).toHaveBeenCalled())
    unmount()
  })
})
