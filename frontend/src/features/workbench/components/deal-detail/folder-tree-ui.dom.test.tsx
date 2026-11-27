// @vitest-environment jsdom
/**
 * folder-tree-ui 的 EntryInput 测试。
 *
 * 关键不变量：Enter 且非空才提交、空串按取消处理、Esc 取消、
 * **失焦有改动即提交**（触屏没有 Enter 可依赖，点一下别处不该白敲一遍）、
 * ✓ / ✕ 两个显式出口，且一次输入只收尾一次。
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

  it('失焦且有改动：提交（触屏没有 Enter 可用，点别处不该白敲）', () => {
    const { input, onConfirm, onCancel, unmount } = renderInput({ initial: '旧名字' })
    fireEvent.change(input, { target: { value: '新名字' } })
    fireEvent.blur(input)
    expect(onConfirm).toHaveBeenCalledWith('新名字')
    expect(onCancel).not.toHaveBeenCalled()
    unmount()
  })

  it('失焦但没改：取消，不发一个同名的无意义重命名', () => {
    const { input, onConfirm, onCancel, unmount } = renderInput({ initial: '旧名字' })
    fireEvent.blur(input)
    expect(onConfirm).not.toHaveBeenCalled()
    expect(onCancel).toHaveBeenCalled()
    unmount()
  })

  it('✓ 提交 / ✕ 取消，且不会因为先失焦而把「取消」变成「提交」', () => {
    const ok = renderInput()
    fireEvent.change(ok.input, { target: { value: '新名' } })
    fireEvent.pointerDown(screen.getByRole('button', { name: '确认' }))
    expect(ok.onConfirm).toHaveBeenCalledWith('新名')
    ok.unmount()

    const no = renderInput({ initial: '旧名字' })
    fireEvent.change(no.input, { target: { value: '新名' } })
    fireEvent.pointerDown(screen.getByRole('button', { name: '取消' }))
    expect(no.onConfirm).not.toHaveBeenCalled()
    expect(no.onCancel).toHaveBeenCalled()
    no.unmount()
  })

  it('同一输入只收尾一次（Enter 后再失焦不重复提交）', () => {
    const { input, onConfirm, unmount } = renderInput({ initial: '旧名字' })
    fireEvent.change(input, { target: { value: '新名' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    fireEvent.blur(input)
    expect(onConfirm).toHaveBeenCalledTimes(1)
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
