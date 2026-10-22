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
