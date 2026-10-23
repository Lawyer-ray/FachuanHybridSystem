// @vitest-environment jsdom
/**
 * FolderTreeDrawer 测试（jsdom）：根层目录渲染、文件行拖拽携带引用
 * JSON（FOLDER_REF_MIME）、展开文件夹逐层懒加载、不可达目录的降级文案。
 * ../api 整体 mock，react-query 用真实 QueryClient。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { FolderEntries } from '../api'

const { fetchContractFolderEntries } = vi.hoisted(() => ({ fetchContractFolderEntries: vi.fn() }))

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return { ...actual, fetchContractFolderEntries }
})

import { FolderTreeDrawer } from './FolderTreeDrawer'
import { FOLDER_REF_MIME } from '../types'

const ROOT: FolderEntries = {
  browsable: true,
  message: null,
  path_display: '合同文件夹',
  subpath: '',
  parent_subpath: '',
  folders: [{ name: '1-一审', subpath: '1-一审' }],
  files: [{ name: '委托合同.docx', subpath: '委托合同.docx', size: 4096, modified_at: '2026-10-01T00:00:00' }],
}

const CHILD: FolderEntries = {
  ...ROOT,
  path_display: '合同文件夹/1-一审',
  subpath: '1-一审',
  parent_subpath: '',
  folders: [],
  files: [{ name: '起诉状.pdf', subpath: '1-一审/起诉状.pdf', size: 8192, modified_at: '2026-10-02T00:00:00' }],
}

function renderDrawer() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <FolderTreeDrawer contractId={8} onClose={vi.fn()} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  fetchContractFolderEntries.mockReset()
})

describe('FolderTreeDrawer 目录渲染', () => {
  it('根层渲染文件夹与文件，文件行可拖拽', async () => {
    fetchContractFolderEntries.mockResolvedValue(ROOT)
    renderDrawer()
    expect(await screen.findByText('1-一审')).toBeTruthy()
    expect(screen.getByText('委托合同.docx')).toBeTruthy()
    expect(screen.getByTitle('委托合同.docx · 拖到输入区引用').hasAttribute('draggable')).toBe(true)
  })

  it('点击文件夹逐层懒加载子目录', async () => {
    fetchContractFolderEntries.mockResolvedValueOnce(ROOT).mockResolvedValueOnce(CHILD)
    renderDrawer()
    fireEvent.click(await screen.findByRole('button', { name: /1-一审/ }))
    expect(await screen.findByText('起诉状.pdf')).toBeTruthy()
    expect(fetchContractFolderEntries).toHaveBeenLastCalledWith(8, '1-一审')
  })

  it('未绑定文件夹时展示后端 message 而非空树', async () => {
    fetchContractFolderEntries.mockResolvedValue({
      ...ROOT,
      browsable: false,
      message: '该合同未绑定文件夹',
      folders: [],
      files: [],
    })
    renderDrawer()
    expect(await screen.findByText('该合同未绑定文件夹')).toBeTruthy()
  })
})

describe('FolderTreeDrawer 拖拽引用', () => {
  it('dragStart 携带 {contractId, subpath, name} 的 FOLDER_REF_MIME 载荷', async () => {
    fetchContractFolderEntries.mockResolvedValue(ROOT)
    renderDrawer()
    const row = await screen.findByText('委托合同.docx')
    const setData = vi.fn()
    const dataTransfer = { setData, effectAllowed: '' }
    fireEvent.dragStart(row.closest('[draggable]') as HTMLElement, { dataTransfer })
    expect(setData).toHaveBeenCalledTimes(1)
    const first = setData.mock.calls[0]
    expect(first).toBeDefined()
    const [mime, raw] = first!
    expect(mime).toBe(FOLDER_REF_MIME)
    expect(JSON.parse(raw)).toEqual({ contractId: 8, subpath: '委托合同.docx', name: '委托合同.docx' })
    expect(dataTransfer.effectAllowed).toBe('copyLink')
  })

  it('子层文件的 subpath 携带完整相对路径', async () => {
    fetchContractFolderEntries.mockResolvedValueOnce(ROOT).mockResolvedValueOnce(CHILD)
    renderDrawer()
    fireEvent.click(await screen.findByRole('button', { name: /1-一审/ }))
    const row = await screen.findByText('起诉状.pdf')
    const setData = vi.fn()
    fireEvent.dragStart(row.closest('[draggable]') as HTMLElement, { dataTransfer: { setData, effectAllowed: '' } })
    const payload = setData.mock.calls[0]?.[1]
    expect(payload).toBeDefined()
    expect(JSON.parse(payload!)).toEqual({
      contractId: 8,
      subpath: '1-一审/起诉状.pdf',
      name: '起诉状.pdf',
    })
  })
})
