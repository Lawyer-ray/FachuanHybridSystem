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
