// @vitest-environment jsdom
/**
 * ClientUploadPage 交互测试（jsdom）。
 *
 * 这是客户（非律师）看到的唯一页面，文案与禁用态要经得起「不解释就点不动」：
 * - 三态：加载中 / 链接无效 / 正常；
 * - 已关闭的三种原因各给各的提示，且不渲染上传区；
 * - 选文件后按钮文案变成「提交 N 个文件」，未选时说明为什么不能点；
 * - 同名同大小重复选择去重（拖两次不该传两遍）；
 * - 提交成功后清空未选列表并回读已传列表。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { getLinkInfo, listUploadedFiles, uploadFiles } = vi.hoisted(() => ({
  getLinkInfo: vi.fn(),
  listUploadedFiles: vi.fn(),
  uploadFiles: vi.fn(),
}))

vi.mock('react-router', () => ({ useParams: () => ({ token: 'tok-1' }) }))
vi.mock('../api', () => ({ getLinkInfo, listUploadedFiles, uploadFiles }))

import { ClientUploadPage } from './ClientUploadPage'

const info = {
  title: '请上传本次诉讼材料',
  lawyer_name: '李律师',
  contract_name: '某施工合同纠纷',
  client_name: '张三公司',
  note: '请提供合同原件扫描件',
  state: 'open' as const,
  remaining_bytes: 1024 * 1024,
}

const pdf = (name: string, size = 2048) => new File(['x'.repeat(size)], name, { type: 'application/pdf' })

function selectFiles(files: File[]) {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement
  Object.defineProperty(input, 'files', { value: files, configurable: true })
  fireEvent.change(input)
}

beforeEach(() => {
  vi.clearAllMocks()
  getLinkInfo.mockResolvedValue(info)
  listUploadedFiles.mockResolvedValue([])
  uploadFiles.mockResolvedValue({ files: [{ filename: 'a.pdf' }] })
})

describe('ClientUploadPage', () => {
  it('加载中显示「正在打开…」', () => {
    getLinkInfo.mockReturnValue(new Promise(() => {}))
    listUploadedFiles.mockReturnValue(new Promise(() => {}))
    render(<ClientUploadPage />)
    expect(screen.getByText('正在打开…')).toBeTruthy()
  })

  it('链接信息取不到：给「链接不存在或已关闭」，不渲染上传区', async () => {
    getLinkInfo.mockRejectedValue(new Error('404'))
    render(<ClientUploadPage />)
    await waitFor(() => expect(screen.getByText('链接不存在或已关闭')).toBeTruthy())
    expect(screen.queryByText(/点击选择文件/)).toBeNull()
  })

  it('正常态：标题、来源说明与剩余容量都展示', async () => {
    render(<ClientUploadPage />)
    await waitFor(() => expect(screen.getByText('请上传本次诉讼材料')).toBeTruthy())
    expect(screen.getByText(/李律师律师 · 某施工合同纠纷 · 张三公司/)).toBeTruthy()
    expect(screen.getByText('请提供合同原件扫描件')).toBeTruthy()
    expect(screen.getByText(/剩余容量/)).toBeTruthy()
  })

  it.each([
    ['expired', '链接已过期，请联系律师重新获取链接'],
    ['revoked', '链接已作废，请联系律师重新获取链接'],
    ['full', '链接已收满，请联系律师重新获取链接'],
  ])('state=%s 时提示各自的原因且不渲染上传区', async (state, text) => {
    getLinkInfo.mockResolvedValue({ ...info, state })
    render(<ClientUploadPage />)
    await waitFor(() => expect(screen.getByText(text)).toBeTruthy())
    expect(screen.queryByText(/点击选择文件/)).toBeNull()
  })

  it('未选文件：按钮禁用且文案说明原因', async () => {
    render(<ClientUploadPage />)
    await waitFor(() => expect(screen.getByText('请先选择文件')).toBeTruthy())
    expect((screen.getByRole('button', { name: /请先选择文件/ }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('选文件后：列出文件名，按钮文案带数量，可单条移除', async () => {
    render(<ClientUploadPage />)
    await waitFor(() => expect(screen.getByText(/点击选择文件/)).toBeTruthy())

    selectFiles([pdf('合同.pdf'), pdf('证据.pdf')])
    await waitFor(() => expect(screen.getByText('提交 2 个文件')).toBeTruthy())
    expect(screen.getByText('合同.pdf')).toBeTruthy()

    const removeButtons = screen.getAllByRole('button', { name: '移除' })
    fireEvent.click(removeButtons[0] as HTMLElement)
    await waitFor(() => expect(screen.getByText('提交 1 个文件')).toBeTruthy())
    expect(screen.queryByText('合同.pdf')).toBeNull()
  })

  it('同名同大小的文件重复选择只保留一份', async () => {
    render(<ClientUploadPage />)
    await waitFor(() => expect(screen.getByText(/点击选择文件/)).toBeTruthy())

    selectFiles([pdf('合同.pdf', 10)])
    await waitFor(() => expect(screen.getByText('提交 1 个文件')).toBeTruthy())
    selectFiles([pdf('合同.pdf', 10)])
    await waitFor(() => expect(screen.getByText('提交 1 个文件')).toBeTruthy())
  })

  it('拖放也走同一收件逻辑', async () => {
    render(<ClientUploadPage />)
    await waitFor(() => expect(screen.getByText(/点击选择文件/)).toBeTruthy())

    const zone = screen.getByText('点击选择文件，或把文件拖到这里').closest('section') as HTMLElement
    fireEvent.drop(zone, { dataTransfer: { files: [pdf('拖进来的.pdf')] } })
    await waitFor(() => expect(screen.getByText('提交 1 个文件')).toBeTruthy())
  })

  it('提交成功：回读已传列表，清空待选与备注，提示已提交份数', async () => {
    listUploadedFiles
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([{ filename: 'a.pdf', size: 2048 }])
    render(<ClientUploadPage />)
    await waitFor(() => expect(screen.getByText(/点击选择文件/)).toBeTruthy())

    selectFiles([pdf('a.pdf')])
    fireEvent.click(screen.getByRole('textbox'))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '第一批证据' } })
    await waitFor(() => expect(screen.getByText('提交 1 个文件')).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: /提交 1 个文件/ }))

    await waitFor(() => expect(screen.getByText(/已提交 1 份材料/)).toBeTruthy())
    expect(uploadFiles).toHaveBeenCalledWith('tok-1', [expect.any(File)], '第一批证据', expect.any(Function))
    expect(screen.getByText('已提交的材料（1）')).toBeTruthy()
    expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe('')
  })

  it('提交失败：错误文案就地展示，待选文件保留（可重试）', async () => {
    uploadFiles.mockRejectedValue(new Error('单个文件超过 50MB'))
    render(<ClientUploadPage />)
    await waitFor(() => expect(screen.getByText(/点击选择文件/)).toBeTruthy())

    selectFiles([pdf('大文件.pdf')])
    await waitFor(() => expect(screen.getByText('提交 1 个文件')).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: /提交 1 个文件/ }))

    await waitFor(() => expect(screen.getByText('单个文件超过 50MB')).toBeTruthy())
    expect(screen.getByText('提交 1 个文件')).toBeTruthy()
  })

  it('已传列表为空时不渲染「已提交的材料」区块', async () => {
    render(<ClientUploadPage />)
    await waitFor(() => expect(screen.getByText(/点击选择文件/)).toBeTruthy())
    expect(screen.queryByText(/已提交的材料/)).toBeNull()
  })
})
