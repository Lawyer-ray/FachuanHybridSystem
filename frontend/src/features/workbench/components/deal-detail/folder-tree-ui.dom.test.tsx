// @vitest-environment jsdom
/**
 * folder-tree-ui 的 EntryInput 测试。
 *
 * 关键不变量：Enter 且非空才提交、空串按取消处理、Esc 取消、失焦取消。
 * 这些分支直接决定「重命名/新建」会不会误提交空名。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { EntryInput } from './folder-tree-ui'

function renderInput(props: Partial<Parameters<typeof EntryInput>[0]> = {}) {
  const onConfirm = vi.fn()
  const onCancel = vi.fn()
  const utils = render(
    <EntryInput placeholder="新名称" onConfirm={onConfirm} onCancel={onCancel} {...props} />,
  )
  const input = screen.getByPlaceholderText('新名称')
  return { ...utils, input, onConfirm, onCancel }
}

describe('EntryInput', () => {
  it('初始值渲染进输入框', () => {
    const { input, unmount } = renderInput({ initial: '旧名字' })
    expect((input as HTMLInputElement).value).toBe('旧名字')
    unmount()
  })

  it('Enter 且非空：提交 trim 后的名字', () => {
    const { input, onConfirm, onCancel, unmount } = renderInput({ initial: '  新名字  ' })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onConfirm).toHaveBeenCalledWith('新名字')
    expect(onCancel).not.toHaveBeenCalled()
    unmount()
  })

  it('Enter 且全空白：按取消处理，不提交空名', () => {
    const { input, onConfirm, onCancel, unmount } = renderInput({ initial: '   ' })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onConfirm).not.toHaveBeenCalled()
    expect(onCancel).toHaveBeenCalled()
    unmount()
  })

  it('Esc：取消且不提交', () => {
    const { input, onConfirm, onCancel, unmount } = renderInput({ initial: '改了' })
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(onCancel).toHaveBeenCalled()
    expect(onConfirm).not.toHaveBeenCalled()
    unmount()
  })

  it('失焦：取消不提交（无歧义动作不做弹窗）', () => {
    const { input, onConfirm, onCancel, unmount } = renderInput({ initial: '改了' })
    fireEvent.blur(input)
    expect(onCancel).toHaveBeenCalled()
    expect(onConfirm).not.toHaveBeenCalled()
    unmount()
  })

  it('输入内容更新后提交新值', () => {
    const { input, onConfirm, unmount } = renderInput()
    fireEvent.change(input, { target: { value: '子文件夹' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onConfirm).toHaveBeenCalledWith('子文件夹')
    unmount()
  })
})
