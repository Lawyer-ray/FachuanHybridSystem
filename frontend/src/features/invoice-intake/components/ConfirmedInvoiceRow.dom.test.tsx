// @vitest-environment jsdom
/**
 * ConfirmedInvoiceRow 复制兜底测试（jsdom）。
 *
 * 确认完最想做的下一件事是**复制那个重命名后的发票**。文件本体写不进剪贴板
 * 的浏览器/环境很常见，所以必须退一步复制文件名——而且退这一步必须让用户
 * 知道（toast 里说清原因），否则他会以为复制的是文件。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { copyInvoiceToClipboard, toast } = vi.hoisted(() => ({
  copyInvoiceToClipboard: vi.fn(),
  toast: { success: vi.fn(), info: vi.fn(), error: vi.fn() },
}))

vi.mock('../api', () => ({ copyInvoiceToClipboard }))
vi.mock('sonner', () => ({ toast }))

import { ConfirmedInvoiceRow } from './ConfirmedInvoiceRow'

const row = {
  intakeId: 1,
  invoiceId: 55,
  buyerName: '张三公司',
  totalAmount: '2400.00',
  displayFilename: '发票（张某与某公司合同纠纷）_20261104开具.pdf',
}

const writeText = vi.fn()

beforeEach(() => {
  vi.clearAllMocks()
  writeText.mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
})

describe('ConfirmedInvoiceRow', () => {
  it('展示金额、购买方、已绑定标记与重命名后的文件名', () => {
    render(<ConfirmedInvoiceRow row={row} />)
    expect(screen.getByText('¥2,400.00')).toBeTruthy()
    expect(screen.getByText('张三公司')).toBeTruthy()
    expect(screen.getByText('已绑定')).toBeTruthy()
    expect(screen.getByText(row.displayFilename)).toBeTruthy()
  })

  it('金额缺失给占位而不留空', () => {
    render(<ConfirmedInvoiceRow row={{ ...row, totalAmount: null }} />)
    expect(screen.getByText('金额未识别')).toBeTruthy()
  })

  it('文件名为空时退回「发票已生成」', () => {
    render(<ConfirmedInvoiceRow row={{ ...row, displayFilename: '' }} />)
    expect(screen.getByText('发票已生成')).toBeTruthy()
  })

  it('文件本体复制成功：直接成功提示，不再碰剪贴板文本', async () => {
    copyInvoiceToClipboard.mockResolvedValue({ success: true, copied: 1, reason: '' })
    render(<ConfirmedInvoiceRow row={row} />)

    fireEvent.click(screen.getByRole('button', { name: /复制发票/ }))

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('发票已复制，微信对话框直接 ⌘V 粘贴发送'))
    expect(writeText).not.toHaveBeenCalled()
  })

  it('环境不支持复制文件本体：退一步复制文件名并说明原因', async () => {
    copyInvoiceToClipboard.mockResolvedValue({ success: false, copied: 0, reason: 'unsupported' })
    render(<ConfirmedInvoiceRow row={row} />)

    fireEvent.click(screen.getByRole('button', { name: /复制发票/ }))

    await waitFor(() => expect(writeText).toHaveBeenCalledWith(row.displayFilename))
    expect(toast.info).toHaveBeenCalledWith('当前环境不支持复制文件本体，已复制文件名')
  })

  it('后端给了其它原因：原样拼进提示', async () => {
    copyInvoiceToClipboard.mockResolvedValue({ success: false, copied: 0, reason: '文件已删除' })
    render(<ConfirmedInvoiceRow row={row} />)

    fireEvent.click(screen.getByRole('button', { name: /复制发票/ }))
    await waitFor(() => expect(toast.info).toHaveBeenCalledWith('文件已删除，已复制文件名'))
  })

  it('后端没给原因：用通用文案，不出现空串提示', async () => {
    copyInvoiceToClipboard.mockResolvedValue({ success: false, copied: 0, reason: '' })
    render(<ConfirmedInvoiceRow row={row} />)

    fireEvent.click(screen.getByRole('button', { name: /复制发票/ }))
    await waitFor(() => expect(toast.info).toHaveBeenCalledWith('复制文件本体失败，已复制文件名'))
  })

  it('复制文件名也失败：提示去项目页下载', async () => {
    copyInvoiceToClipboard.mockResolvedValue({ success: false, copied: 0, reason: 'unsupported' })
    writeText.mockRejectedValue(new Error('剪贴板被拒绝'))
    render(<ConfirmedInvoiceRow row={row} />)

    fireEvent.click(screen.getByRole('button', { name: /复制发票/ }))
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('复制失败，请到项目页下载'))
  })

  it('接口抛错：错误文案 + 已复制文件名的复合提示', async () => {
    copyInvoiceToClipboard.mockRejectedValue(new Error('网络错误'))
    render(<ConfirmedInvoiceRow row={row} />)

    fireEvent.click(screen.getByRole('button', { name: /复制发票/ }))
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('网络错误，已复制文件名'))
  })

  it('接口抛错且剪贴板也失败：只报原始错误 + 下载指引', async () => {
    copyInvoiceToClipboard.mockRejectedValue(new Error('网络错误'))
    writeText.mockRejectedValue(new Error('剪贴板被拒绝'))
    render(<ConfirmedInvoiceRow row={row} />)

    fireEvent.click(screen.getByRole('button', { name: /复制发票/ }))
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('网络错误'))
  })

  it('复制中按钮禁用（防重复点击），完成后恢复', async () => {
    let resolveCopy: (v: unknown) => void = () => {}
    copyInvoiceToClipboard.mockReturnValue(new Promise((r) => (resolveCopy = r)))
    render(<ConfirmedInvoiceRow row={row} />)

    const btn = screen.getByRole('button', { name: /复制发票/ }) as HTMLButtonElement
    fireEvent.click(btn)
    await waitFor(() => expect(btn.disabled).toBe(true))

    resolveCopy({ success: true, copied: 1, reason: '' })
    await waitFor(() => expect(btn.disabled).toBe(false))
  })
})
