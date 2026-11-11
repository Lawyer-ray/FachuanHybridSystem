// @vitest-environment jsdom
/**
 * OcrPanel 测试（jsdom）。
 *
 * OCR 取字是「机器猜 + 人工改」：识别中要锁住输入并说明进度，识别完要允许
 * 直接改文字、重框、或取消。文案两条都要给到位，否则用户不知道该干什么。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { OcrPanel } from './OcrPanel'
import type { OcrPending } from '../../types'

function pending(over: Partial<OcrPending> = {}): OcrPending {
  return { mi: 0, p: 3, rect: { x: 0, y: 0, w: 100, h: 40 }, text: '原告张某与被告某公司', loading: false, ...over }
}

function props(over: Partial<Parameters<typeof OcrPanel>[0]> = {}) {
  return {
    pending: pending(),
    fromLabel: '第 3 页',
    toLabel: '第 4 页',
    onText: vi.fn(),
    onRedo: vi.fn(),
    onCancel: vi.fn(),
    onOk: vi.fn(),
    ...over,
  }
}

describe('OcrPanel', () => {
  it('展示来源页与目标页，按钮文案指向目标页', () => {
    render(<OcrPanel {...props()} />)
    expect(screen.getByText('第 3 页')).toBeTruthy()
    expect(screen.getByText('第 4 页')).toBeTruthy()
    expect(screen.getByRole('button', { name: '填入「第 4 页」' })).toBeTruthy()
  })

  it('已有识别结果：提示可直接改、可继续调范围', () => {
    render(<OcrPanel {...props()} />)
    expect(screen.getByText('识别结果可直接改，继续拖手柄还能调范围')).toBeTruthy()
  })

  it('空结果：提示重框或手打（而不是让人对着空白发呆）', () => {
    render(<OcrPanel {...props({ pending: pending({ text: '' }) })} />)
    expect(screen.getByText('换个位置重框，或直接手打')).toBeTruthy()
  })

  it('识别中：显示进度文案，输入禁用且占位换文案', () => {
    render(<OcrPanel {...props({ pending: pending({ loading: true, text: '' }) })} />)
    expect(screen.getByText('识别中…', { selector: 'span' })).toBeTruthy()
    const input = screen.getByPlaceholderText('识别中…') as HTMLInputElement
    expect(input.disabled).toBe(true)
  })

  it('编辑文字回传 onText', () => {
    const p = props()
    render(<OcrPanel {...p} />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '改后的字' } })
    expect(p.onText).toHaveBeenCalledWith('改后的字')
  })

  it('重框 / 取消 / 填入各自回传', () => {
    const p = props()
    render(<OcrPanel {...p} />)

    fireEvent.click(screen.getByRole('button', { name: '重框' }))
    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    fireEvent.click(screen.getByRole('button', { name: '填入「第 4 页」' }))

    expect(p.onRedo).toHaveBeenCalledTimes(1)
    expect(p.onCancel).toHaveBeenCalledTimes(1)
    expect(p.onOk).toHaveBeenCalledTimes(1)
  })
})
