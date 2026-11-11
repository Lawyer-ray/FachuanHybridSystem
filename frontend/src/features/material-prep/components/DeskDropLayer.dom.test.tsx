// @vitest-environment jsdom
/**
 * DeskDropLayer 测试（jsdom）。
 *
 * 它承载两件事：拖拽时的「松手即新建」遮罩，以及 DeskPage 各处「选文件」
 * 按钮共用的隐藏 file input。选完必须清空 input.value —— 否则同一个文件
 * 第二次选不会触发 change（这是最容易被忽略、也最容易被用户感知为「坏了」的点）。
 */
import { createRef } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { DeskDropLayer } from './DeskDropLayer'

const inputOf = (container: HTMLElement) => container.querySelector('input[type="file"]') as HTMLInputElement

describe('DeskDropLayer', () => {
  it('未拖拽时不渲染遮罩', () => {
    const { container } = render(<DeskDropLayer dragging={false} fileInputRef={createRef<HTMLInputElement>()} onFiles={vi.fn()} />)
    expect(screen.queryByText('松手即新建材料包')).toBeNull()
    expect(inputOf(container)).toBeTruthy()
  })

  it('拖拽时展示遮罩与支持的格式说明', () => {
    render(<DeskDropLayer dragging fileInputRef={createRef<HTMLInputElement>()} onFiles={vi.fn()} />)
    expect(screen.getByText('松手即新建材料包')).toBeTruthy()
    expect(screen.getByText(/压缩包自动解包展开/)).toBeTruthy()
  })

  it('file input 支持多选，且 ref 挂到 DeskPage 持有的对象上', () => {
    const ref = createRef<HTMLInputElement>()
    const { container } = render(<DeskDropLayer dragging={false} fileInputRef={ref} onFiles={vi.fn()} />)
    const input = inputOf(container)
    expect(input.multiple).toBe(true)
    expect(ref.current).toBe(input)
  })

  it('选中文件：回调收到 FileList，且 input.value 被清空以便再次选同一文件', () => {
    const onFiles = vi.fn()
    const { container } = render(<DeskDropLayer dragging={false} fileInputRef={createRef<HTMLInputElement>()} onFiles={onFiles} />)
    const input = inputOf(container)

    const files = [new File(['x'], 'a.pdf', { type: 'application/pdf' })]
    Object.defineProperty(input, 'files', { value: files, configurable: true })

    fireEvent.change(input)

    expect(onFiles).toHaveBeenCalledWith(files)
    // jsdom 不允许给 file input 赋非空值，能观察到的就是「已被写成空串」
    expect(input.value).toBe('')
  })
})
