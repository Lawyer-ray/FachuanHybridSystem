// @vitest-environment jsdom
/**
 * MaterialDropZone 测试（jsdom）。
 *
 * 覆盖拖放/点选/键盘三条录入路径、删除单件、禁用态、不支持文件的提示，
 * 以及高亮层的 enter/leave 深度计数（子元素间抖动不应熄灭高亮）。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('sonner', () => ({ toast: { warning: vi.fn(), info: vi.fn() } }))

import { toast } from 'sonner'

import { MaterialDropZone } from './MaterialDropZone'

function pdf(name: string, size = 10, lastModified = 1): File {
  return new File([new Uint8Array(size)], name, { type: 'application/pdf', lastModified })
}

function zone() {
  return screen.getByRole('button', { name: '拖入或点击选择案件材料' })
}

describe('MaterialDropZone', () => {
  it('空列表时显示提示文案，不渲染文件项', () => {
    render(<MaterialDropZone files={[]} onFilesChange={vi.fn()} />)

    expect(screen.getByText('拖入案件材料，或点击选择')).toBeTruthy()
    expect(screen.queryByRole('list')).toBeNull()
  })

  it('拖入文件：回调收到新列表', () => {
    const onFilesChange = vi.fn()
    render(<MaterialDropZone files={[]} onFilesChange={onFilesChange} />)

    const file = pdf('判决书.pdf')
    fireEvent.drop(zone(), { dataTransfer: { files: [file] } })

    expect(onFilesChange).toHaveBeenCalledWith([file])
  })

  it('拖入不支持的文件：提示且不回调', () => {
    const onFilesChange = vi.fn()
    render(<MaterialDropZone files={[]} onFilesChange={onFilesChange} />)

    fireEvent.drop(zone(), { dataTransfer: { files: [new File(['x'], 'a.mov')] } })

    expect(toast.warning).toHaveBeenCalled()
    expect(onFilesChange).not.toHaveBeenCalled()
  })

  it('重复拖入同一文件不重复入列', () => {
    const existing = pdf('判决书.pdf', 10, 1)
    const onFilesChange = vi.fn()
    render(<MaterialDropZone files={[existing]} onFilesChange={onFilesChange} />)

    fireEvent.drop(zone(), { dataTransfer: { files: [pdf('判决书.pdf', 10, 1)] } })

    expect(onFilesChange).not.toHaveBeenCalled()
  })

  it('点选文件（input change）走同一套合并逻辑', () => {
    const onFilesChange = vi.fn()
    render(<MaterialDropZone files={[]} onFilesChange={onFilesChange} />)

    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = pdf('证据.png'.replace('.png', '.pdf'))
    fireEvent.change(input, { target: { files: [file] } })

    expect(onFilesChange).toHaveBeenCalledWith([file])
  })

  it('文件列表展示名称/大小，并可单件移除', () => {
    const a = pdf('判决书.pdf', 2048, 1)
    const b = pdf('证据.pdf', 1024, 2)
    const onFilesChange = vi.fn()
    render(<MaterialDropZone files={[a, b]} onFilesChange={onFilesChange} />)

    expect(screen.getByText('判决书.pdf')).toBeTruthy()
    expect(screen.getByText('2 KB')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '移除 判决书.pdf' }))
    expect(onFilesChange).toHaveBeenCalledWith([b])
  })

  it('disabled：拖放与点击都不触发回调，input 禁用', () => {
    const onFilesChange = vi.fn()
    render(<MaterialDropZone files={[]} onFilesChange={onFilesChange} disabled />)

    fireEvent.drop(zone(), { dataTransfer: { files: [pdf('a.pdf')] } })
    fireEvent.click(zone())
    const input = document.querySelector('input[type="file"]') as HTMLInputElement

    expect(onFilesChange).not.toHaveBeenCalled()
    expect(input.disabled).toBe(true)
    expect(zone().getAttribute('aria-disabled')).toBe('true')
  })

  it('键盘 Enter / 空格等价于点击（可访问性）', () => {
    render(<MaterialDropZone files={[]} onFilesChange={vi.fn()} />)
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    const clickSpy = vi.spyOn(input, 'click')

    fireEvent.keyDown(zone(), { key: 'Enter' })
    fireEvent.keyDown(zone(), { key: ' ' })

    expect(clickSpy).toHaveBeenCalledTimes(2)
  })

  it('拖过子元素（enter/leave 交替）时高亮不平灭，全部 leave 后才平灭', () => {
    render(<MaterialDropZone files={[]} onFilesChange={vi.fn()} />)
    const el = zone()

    // 进入热区 + 进入子元素 = 两次 enter
    fireEvent.dragEnter(el)
    fireEvent.dragEnter(el)
    expect(screen.getByText('松开即可添加')).toBeTruthy()

    // 离开一个子元素：深度不为 0，仍高亮
    fireEvent.dragLeave(el)
    expect(screen.getByText('松开即可添加')).toBeTruthy()

    // 真正离开热区
    fireEvent.dragLeave(el)
    expect(screen.queryByText('松开即可添加')).toBeNull()
  })

  it('drop 后熄灭高亮', () => {
    render(<MaterialDropZone files={[]} onFilesChange={vi.fn()} />)
    const el = zone()

    fireEvent.dragEnter(el)
    fireEvent.drop(el, { dataTransfer: { files: [pdf('a.pdf')] } })

    expect(screen.queryByText('松开即可添加')).toBeNull()
  })

  it('disabled 时忽略 dragEnter（不显示高亮）', () => {
    render(<MaterialDropZone files={[]} onFilesChange={vi.fn()} disabled />)

    fireEvent.dragEnter(zone())
    expect(screen.queryByText('松开即可添加')).toBeNull()
  })
})
