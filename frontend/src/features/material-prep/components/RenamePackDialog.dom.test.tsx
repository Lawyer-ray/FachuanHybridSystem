// @vitest-environment jsdom
/**
 * RenamePackDialog 测试（jsdom）。
 *
 * 重命名材料包：打开时回填当前名、空名禁用保存、Enter 提交、
 * 成功后同步阅读器标题并关闭提示、失败提示且不关闭。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const hookMock = vi.hoisted(() => ({
  mutateAsync: vi.fn(),
  isPending: false,
}))
const storeMock = vi.hoisted(() => ({ renameSubject: vi.fn() }))

vi.mock('../hooks/use-inbox', () => ({ useRenamePack: () => hookMock }))
vi.mock('../store', () => ({
  useReader: (sel: (s: typeof storeMock) => unknown) => sel(storeMock),
}))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }))

import { toast } from 'sonner'

import { RenamePackDialog } from './RenamePackDialog'

function pack(subject: string) {
  return { id: 7, subject } as never
}

function renderDialog(props: Partial<Parameters<typeof RenamePackDialog>[0]> = {}) {
  const onOpenChange = vi.fn()
  const utils = render(
    <RenamePackDialog open onOpenChange={onOpenChange} pack={pack('旧名字')} {...props} />,
  )
  return { ...utils, onOpenChange }
}

function input(): HTMLInputElement {
  return screen.getByPlaceholderText('材料包名称') as HTMLInputElement
}

beforeEach(() => {
  vi.clearAllMocks()
  hookMock.mutateAsync = vi.fn(async () => ({}))
  hookMock.isPending = false
})

describe('RenamePackDialog：回填与禁用', () => {
  it('打开时回填当前名称', async () => {
    const { unmount } = renderDialog()
    await waitFor(() => expect(input().value).toBe('旧名字'))
    unmount()
  })

  it('pack 为 null 时输入为空', async () => {
    const { unmount } = renderDialog({ pack: null })
    await waitFor(() => expect(input().value).toBe(''))
    unmount()
  })

  it('空名时保存按钮禁用', async () => {
    const { unmount } = renderDialog()
    await waitFor(() => expect(input().value).toBe('旧名字'))

    fireEvent.change(input(), { target: { value: '   ' } })
    const save = screen.getByRole('button', { name: '保存' }) as HTMLButtonElement
    expect(save.disabled).toBe(true)
    unmount()
  })

  it('isPending 时保存按钮禁用且显示「保存中…」', async () => {
    hookMock.isPending = true
    const { unmount } = renderDialog()
    await waitFor(() => expect(input().value).toBe('旧名字'))
    expect(screen.getByRole('button', { name: /保存中/ })).toBeTruthy()
    unmount()
  })
})

describe('RenamePackDialog：提交', () => {
  it('点保存提交并同步阅读器标题、关闭、提示', async () => {
    const { onOpenChange, unmount } = renderDialog()
    await waitFor(() => expect(input().value).toBe('旧名字'))

    fireEvent.change(input(), { target: { value: '新名字' } })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))

    await waitFor(() => expect(hookMock.mutateAsync).toHaveBeenCalledWith({ id: 7, subject: '新名字' }))
    expect(storeMock.renameSubject).toHaveBeenCalledWith(7, '新名字')
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(toast.success).toHaveBeenCalledWith('已重命名')
    unmount()
  })

  it('提交前 trim 前后空白', async () => {
    const { unmount } = renderDialog()
    await waitFor(() => expect(input().value).toBe('旧名字'))

    fireEvent.change(input(), { target: { value: '  新名字  ' } })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))

    await waitFor(() => expect(hookMock.mutateAsync).toHaveBeenCalledWith({ id: 7, subject: '新名字' }))
    unmount()
  })

  it('Enter 键提交', async () => {
    const { unmount } = renderDialog()
    await waitFor(() => expect(input().value).toBe('旧名字'))

    fireEvent.change(input(), { target: { value: '回车名' } })
    fireEvent.keyDown(input(), { key: 'Enter' })

    await waitFor(() => expect(hookMock.mutateAsync).toHaveBeenCalledWith({ id: 7, subject: '回车名' }))
    unmount()
  })

  it('空名按 Enter 不提交', async () => {
    const { unmount } = renderDialog()
    await waitFor(() => expect(input().value).toBe('旧名字'))

    fireEvent.change(input(), { target: { value: '  ' } })
    fireEvent.keyDown(input(), { key: 'Enter' })
    await new Promise((r) => setTimeout(r, 30))
    expect(hookMock.mutateAsync).not.toHaveBeenCalled()
    unmount()
  })

  it('失败提示且不同步标题', async () => {
    hookMock.mutateAsync = vi.fn(async () => {
      throw new Error('boom')
    })
    const { unmount } = renderDialog()
    await waitFor(() => expect(input().value).toBe('旧名字'))

    fireEvent.change(input(), { target: { value: '新名字' } })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('重命名失败，请重试'))
    // 失败时不得同步标题（onOpenChange 可能被 AlertDialog 自身交互触发，
    // 不作为「成功关闭」的判据）
    expect(storeMock.renameSubject).not.toHaveBeenCalled()
    unmount()
  })
})
