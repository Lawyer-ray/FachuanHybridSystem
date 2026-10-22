// @vitest-environment jsdom
/**
 * QuickAdd 粘贴接线的 dom 测试（jsdom）。
 *
 * 纯函数在 clipboard-file.test.ts（node）覆盖；本文件只验证组件接线：
 * paste 带图片 → 走文件校验 → 出现文件胶囊与「识别并确认」；
 * 纯文字 paste 不拦截默认行为、校验拒绝时不进文件态。
 * document-recognition 域整域 mock（真实惰性块会连带 pdfjs 预览，过重）。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('sonner', () => ({
  toast: { info: vi.fn(), success: vi.fn(), warning: vi.fn(), error: vi.fn() },
}))

import { toast } from 'sonner'

import { QuickAdd } from './SideCards'

const fileRejectReason = vi.hoisted(() => vi.fn<(f: File) => string | null>(() => null))
vi.mock('@/features/document-recognition', () => ({
  preloadRecognizeDialog: vi.fn(),
  fileRejectReason: (f: File) => fileRejectReason(f),
  rowsFromParsed: vi.fn(() => []),
  RecognizeDialogLazy: () => <div data-testid="recognize-dialog-stub" />,
}))

function pasteImage(name = 'image.png', type = 'image/png') {
  const input = screen.getByPlaceholderText(/快速记一笔/)
  fireEvent.paste(input, {
    clipboardData: { files: [new File(['x'], name, { type })] },
  })
}

describe('QuickAdd onPaste', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fileRejectReason.mockReturnValue(null)
  })

  it('粘贴截图：出文件胶囊与「识别并确认」，弹窗域被拉起', () => {
    render(<QuickAdd onAdded={vi.fn()} />)
    pasteImage()
    expect(screen.getByText(/粘贴图片-\d{8}-\d{6}\.png/)).toBeTruthy()
    expect(screen.getByRole('button', { name: '识别并确认' })).toBeTruthy()
    expect(screen.getByTestId('recognize-dialog-stub')).toBeTruthy()
  })

  it('粘贴的名字有信息量时原样展示（不改名）', () => {
    render(<QuickAdd onAdded={vi.fn()} />)
    pasteImage('传票.jpg', 'image/jpeg')
    expect(screen.getByText('传票.jpg')).toBeTruthy()
  })

  it('校验拒绝：就地警告，不进文件态', () => {
    fileRejectReason.mockReturnValue('文件超过 20MB')
    render(<QuickAdd onAdded={vi.fn()} />)
    pasteImage()
    expect(toast.warning).toHaveBeenCalledWith('文件超过 20MB')
    expect(screen.queryByRole('button', { name: '识别并确认' })).toBeNull()
  })

  it('纯文字剪贴板：不触发文件校验，也不进文件态', () => {
    render(<QuickAdd onAdded={vi.fn()} />)
    const input = screen.getByPlaceholderText(/快速记一笔/)
    fireEvent.paste(input, { clipboardData: { files: [] } })
    expect(fileRejectReason).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: '识别并确认' })).toBeNull()
  })
})

// ============ 拖放 / 文件胶囊 / 按钮态（覆盖率补测） ============

describe('QuickAdd 拖放与文件胶囊', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fileRejectReason.mockReturnValue(null)
  })

  function dropFile(container: HTMLElement, name = 'drag.pdf') {
    const bar = container.firstElementChild as HTMLElement
    fireEvent.drop(bar, { dataTransfer: { files: [new File(['x'], name, { type: 'application/pdf' })] } })
    return bar
  }

  it('拖入文件：走校验并进入文件态', () => {
    const { container } = render(<QuickAdd onAdded={vi.fn()} />)
    dropFile(container)
    expect(fileRejectReason).toHaveBeenCalled()
    expect(screen.getByText('drag.pdf')).toBeTruthy()
    expect(screen.getByRole('button', { name: '识别并确认' })).toBeTruthy()
    container.remove()
  })

  it('拖入被拒绝的文件：就地警告且不进文件态', () => {
    fileRejectReason.mockReturnValue('不支持该格式')
    const { container } = render(<QuickAdd onAdded={vi.fn()} />)
    dropFile(container, 'bad.exe')

    expect(toast.warning).toHaveBeenCalledWith('不支持该格式')
    expect(screen.queryByText('bad.exe')).toBeNull()
    container.remove()
  })

  it('文件态下点「移除文件」清掉胶囊回到输入框', () => {
    const { container } = render(<QuickAdd onAdded={vi.fn()} />)
    dropFile(container)
    expect(screen.getByText('drag.pdf')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '移除文件' }))
    expect(screen.queryByText('drag.pdf')).toBeNull()
    expect(screen.getByPlaceholderText(/快速记一笔/)).toBeTruthy()
    container.remove()
  })

  it('文件态下主按钮文案变为「识别并确认」', () => {
    const { container } = render(<QuickAdd onAdded={vi.fn()} />)
    dropFile(container)
    expect(screen.getByRole('button', { name: '识别并确认' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: '记一笔' })).toBeNull()
    container.remove()
  })

  it('点「上传文书识别」触发隐藏 file input', () => {
    const { container } = render(<QuickAdd onAdded={vi.fn()} />)
    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    const clickSpy = vi.spyOn(input, 'click')

    fireEvent.click(screen.getByRole('button', { name: '上传文书识别' }))
    expect(clickSpy).toHaveBeenCalled()
    container.remove()
  })

  it('通过 file input 选文件同样进入文件态', () => {
    const { container } = render(<QuickAdd onAdded={vi.fn()} />)
    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [new File(['x'], 'picked.pdf')] } })

    expect(screen.getByText('picked.pdf')).toBeTruthy()
    container.remove()
  })

  it('dragover 时高亮输入条，dragleave 取消高亮', () => {
    const { container } = render(<QuickAdd onAdded={vi.fn()} />)
    const bar = container.firstElementChild as HTMLElement

    fireEvent.dragOver(bar)
    expect(bar.className).toContain('border-ring/60')

    fireEvent.dragLeave(bar)
    expect(bar.className).not.toContain('border-ring/60')
    container.remove()
  })
})

// ============ pickFile 空值 / preload 调用（覆盖率补测） ============

describe('QuickAdd pickFile 边界', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('file input 未选文件（files 为空）时不进入文件态', () => {
    const { container } = render(<QuickAdd onAdded={vi.fn()} />)
    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [] } })

    expect(fileRejectReason).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: '识别并确认' })).toBeNull()
    container.remove()
  })

  it('拖入空文件列表时不进入文件态', () => {
    const { container } = render(<QuickAdd onAdded={vi.fn()} />)
    const bar = container.firstElementChild as HTMLElement
    fireEvent.drop(bar, { dataTransfer: { files: [] } })

    expect(fileRejectReason).not.toHaveBeenCalled()
    container.remove()
  })
})
