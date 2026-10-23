// @vitest-environment jsdom
/**
 * RenameMatDialog 测试（jsdom）。
 *
 * 重命名源文件的展示名（只改 draft，不改原始文件）：
 * - 打开时回填当前名、关闭态不渲染
 * - 空名禁用保存、Enter 同样不提交
 * - 保存调用 renameMatInDraft 并 trim、随后关闭并提示
 * - 取消不提交
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const storeMock = vi.hoisted(() => ({ renameMatInDraft: vi.fn() }))
vi.mock('../../store', () => ({
  useReader: (sel: (s: typeof storeMock) => unknown) => sel(storeMock),
}))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }))

import { toast } from 'sonner'

import { RenameMatDialog } from './RenameMatDialog'

function renderDialog(target: { mi: number; initial: string } | null, onClose = vi.fn()) {
  const utils = render(<RenameMatDialog target={target} onClose={onClose} />)
  return { ...utils, onClose }
}

function input(): HTMLInputElement {
  return screen.getByPlaceholderText('源文件名') as HTMLInputElement
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('RenameMatDialog：回填与禁用', () => {
  it('关闭态（target=null）不渲染输入框', () => {
    const { unmount } = renderDialog(null)
    expect(screen.queryByPlaceholderText('源文件名')).toBeNull()
    unmount()
  })

  it('打开时回填当前名', async () => {
    const { unmount } = renderDialog({ mi: 0, initial: '起诉状.pdf' })
    await waitFor(() => expect(input().value).toBe('起诉状.pdf'))
    unmount()
  })

  it('空名时保存按钮禁用', async () => {
    const { unmount } = renderDialog({ mi: 0, initial: '起诉状.pdf' })
    await waitFor(() => expect(input().value).toBe('起诉状.pdf'))

    fireEvent.change(input(), { target: { value: '   ' } })
    expect((screen.getByRole('button', { name: '保存' }) as HTMLButtonElement).disabled).toBe(true)
    unmount()
  })
})

describe('RenameMatDialog：提交', () => {
  it('点保存：trim 后调用 renameMatInDraft，关闭并提示', async () => {
    const { unmount, onClose } = renderDialog({ mi: 2, initial: '旧名.pdf' })
    await waitFor(() => expect(input().value).toBe('旧名.pdf'))

    fireEvent.change(input(), { target: { value: '  新名.pdf  ' } })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))

    expect(storeMock.renameMatInDraft).toHaveBeenCalledWith(2, '新名.pdf')
    expect(onClose).toHaveBeenCalled()
    expect(toast.success).toHaveBeenCalledWith('已重命名')
    unmount()
  })

  it('Enter 键提交', async () => {
    const { unmount } = renderDialog({ mi: 1, initial: 'a.pdf' })
    await waitFor(() => expect(input().value).toBe('a.pdf'))

    fireEvent.change(input(), { target: { value: 'b.pdf' } })
    fireEvent.keyDown(input(), { key: 'Enter' })

    expect(storeMock.renameMatInDraft).toHaveBeenCalledWith(1, 'b.pdf')
    unmount()
  })

  it('空名按 Enter 不提交', async () => {
    const { unmount } = renderDialog({ mi: 0, initial: 'a.pdf' })
    await waitFor(() => expect(input().value).toBe('a.pdf'))

    fireEvent.change(input(), { target: { value: '  ' } })
    fireEvent.keyDown(input(), { key: 'Enter' })
    expect(storeMock.renameMatInDraft).not.toHaveBeenCalled()
    unmount()
  })

  it('点取消不提交', async () => {
    const { unmount } = renderDialog({ mi: 0, initial: "a.pdf" })
    await waitFor(() => expect(input().value).toBe('a.pdf'))

    fireEvent.change(input(), { target: { value: 'b.pdf' } })
    fireEvent.click(screen.getByRole('button', { name: '取消' }))

    expect(storeMock.renameMatInDraft).not.toHaveBeenCalled()
    unmount()
  })
})
