// @vitest-environment jsdom
/**
 * FolderTree 测试（jsdom）。
 *
 * 递归文件树的三个层次：
 * - FolderTree：标题行 + 新建文件夹入口 + 空白区拖放上传
 * - NodeList：loading / error / 空目录 / 空根 / 递归渲染
 * - FolderRow / FileRow：展开折叠、重命名、删除、右键菜单
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, waitFor, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  listFolderEntries: vi.fn(),
  createFolderEntry: vi.fn(),
  renameFolderEntry: vi.fn(),
  uploadFolderFiles: vi.fn(),
  copyFolderEntry: vi.fn(),
  deleteFolderEntry: vi.fn(),
  folderFileUrl: vi.fn(() => '/api/v1/cases/1/folder-file?subpath=x'),
}))
const ticketMock = vi.hoisted(() => vi.fn(async (p: string) => p + '&ticket=t'))

vi.mock('../../api', () => ({ ...apiMock }))
vi.mock('../../hooks/use-workbench-data', () => ({
  workbenchKeys: {
    folderEntries: (k: string, id: number) => ['folders', k, id],
    folderEntriesItem: (k: string, id: number, sp: string) => ['folders', k, id, sp],
  },
}))
vi.mock('@/lib/download-ticket', () => ({ withDownloadTicket: (p: string) => ticketMock(p) }))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }))

import { toast } from 'sonner'

import { FolderTree } from './FolderTree'

function entries(folders: string[] = [], files: string[] = []) {
  return {
    browsable: true,
    message: null,
    path_display: '/',
    subpath: '',
    parent_subpath: '',
    folders: folders.map((n) => ({ name: n, subpath: n })),
    files: files.map((n) => ({ name: n, subpath: n, size: 100, modified_at: '2026-10-20T10:00:00' })),
  }
}

function renderTree(props: Partial<Parameters<typeof FolderTree>[0]> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const wrap = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
  return render(<FolderTree kind="case" ownerId={1} {...props} />, { wrapper: wrap })
}

beforeEach(() => {
  vi.clearAllMocks()
  apiMock.listFolderEntries.mockResolvedValue(entries())
})

describe('FolderTree：根层', () => {
  it('loading 时显示读取中', async () => {
    apiMock.listFolderEntries.mockReturnValue(new Promise(() => {}))
    const { container } = renderTree()
    await waitFor(() => expect(container.textContent).toContain('正在读取文件夹'))
    container.remove()
  })

  it('读取失败时显示错误文案', async () => {
    apiMock.listFolderEntries.mockRejectedValue(new Error('网络异常'))
    const { container } = renderTree()
    await waitFor(() => expect(within(container).getByText('网络异常')).toBeTruthy())
    container.remove()
  })

  it('根目录为空时提示「文件夹是空的」', async () => {
    const { container } = renderTree()
    await waitFor(() => expect(within(container).getByText('文件夹是空的')).toBeTruthy())
    container.remove()
  })

  it('有 title 时渲染标题行', async () => {
    const { container } = renderTree({ title: '案件材料' })
    await waitFor(() => expect(within(container).getByText('案件材料')).toBeTruthy())
    container.remove()
  })

  it('渲染文件夹与文件', async () => {
    apiMock.listFolderEntries.mockResolvedValue(entries(['起诉状'], ['a.pdf']))
    const { container } = renderTree()
    await waitFor(() => expect(within(container).getByText('起诉状')).toBeTruthy())
    expect(within(container).getByText('a.pdf')).toBeTruthy()
    container.remove()
  })

  it('点「新建文件夹」进入创建态', async () => {
    const { container } = renderTree()
    await waitFor(() => expect(within(container).getByText('文件夹是空的')).toBeTruthy())

    fireEvent.click(within(container).getByRole('button', { name: /新建文件夹/ }))
    // 输入框 autoFocus 挂载后才出现，需等一拍
    await waitFor(() => expect(container.querySelector('input[placeholder="新文件夹名"]')).toBeTruthy())
    container.remove()
  })

  it('拖入文件到空白区触发根目录上传', async () => {
    apiMock.uploadFolderFiles.mockResolvedValue({ saved: [] })
    const { container } = renderTree()
    await waitFor(() => expect(within(container).getByText('文件夹是空的')).toBeTruthy())

    const root = container.firstElementChild as HTMLElement
    const file = new File(['x'], 'a.pdf')
    fireEvent.drop(root, { dataTransfer: { files: [file] } })

    await waitFor(() => expect(apiMock.uploadFolderFiles).toHaveBeenCalledWith('case', 1, '', [file]))
    container.remove()
  })

  it('拖入空文件列表不触发上传', async () => {
    const { container } = renderTree()
    await waitFor(() => expect(within(container).getByText('文件夹是空的')).toBeTruthy())

    const root = container.firstElementChild as HTMLElement
    fireEvent.drop(root, { dataTransfer: { files: [] } })
    await new Promise((r) => setTimeout(r, 30))
    expect(apiMock.uploadFolderFiles).not.toHaveBeenCalled()
    container.remove()
  })
})

describe('FolderTree：文件夹交互', () => {
  it('展开文件夹会请求该层并渲染子项', async () => {
    apiMock.listFolderEntries.mockImplementation(async (_k, _id, sp: string) =>
      sp === '' ? entries(['子夹']) : entries([], ['inner.pdf']),
    )
    const { container } = renderTree()
    await waitFor(() => expect(within(container).getByText('子夹')).toBeTruthy())

    fireEvent.click(within(container).getByText('子夹'))
    await waitFor(() => expect(within(container).getByText('inner.pdf')).toBeTruthy())
    container.remove()
  })

  it('空文件夹展开后显示「（空）」', async () => {
    apiMock.listFolderEntries.mockImplementation(async (_k, _id, sp: string) =>
      sp === '' ? entries(['空夹']) : entries(),
    )
    const { container } = renderTree()
    await waitFor(() => expect(within(container).getByText('空夹')).toBeTruthy())

    fireEvent.click(within(container).getByText('空夹'))
    await waitFor(() => expect(within(container).getByText('（空）')).toBeTruthy())
    container.remove()
  })

  it('重命名成功后提示并刷新', async () => {
    apiMock.listFolderEntries.mockResolvedValue(entries(['旧名']))
    apiMock.renameFolderEntry.mockResolvedValue({})
    const { container } = renderTree()
    await waitFor(() => expect(within(container).getByText('旧名')).toBeTruthy())

    fireEvent.click(within(container).getByRole('button', { name: '重命名' }))
    const input = container.querySelector('input[placeholder="新名称"]') as HTMLInputElement
    fireEvent.change(input, { target: { value: '新名' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    await waitFor(() => expect(apiMock.renameFolderEntry).toHaveBeenCalledWith('case', 1, '旧名', '新名'))
    container.remove()
  })

  it('重命名失败弹 toast', async () => {
    apiMock.listFolderEntries.mockResolvedValue(entries(['旧名']))
    apiMock.renameFolderEntry.mockRejectedValue(new Error('同名已存在'))
    const { container } = renderTree()
    await waitFor(() => expect(within(container).getByText('旧名')).toBeTruthy())

    fireEvent.click(within(container).getByRole('button', { name: '重命名' }))
    const input = container.querySelector('input[placeholder="新名称"]') as HTMLInputElement
    fireEvent.change(input, { target: { value: '新名' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    await waitFor(() => expect(toast.error).toHaveBeenCalled())
    container.remove()
  })
})

describe('FolderTree：文件交互', () => {
  it('文件行显示日期与大小', async () => {
    apiMock.listFolderEntries.mockResolvedValue(entries([], ['a.pdf']))
    const { container } = renderTree()
    await waitFor(() => expect(within(container).getByText('a.pdf')).toBeTruthy())
    expect(container.textContent).toContain('2026-10-20')
    container.remove()
  })

  it('Enter 打开文件预览（换票据后新窗口）', async () => {
    const openSpy = vi.fn()
    vi.stubGlobal('open', openSpy)
    apiMock.listFolderEntries.mockResolvedValue(entries([], ['a.pdf']))

    const { container } = renderTree()
    const row = await waitFor(() => within(container).getByText('a.pdf').closest('[role="button"]') as HTMLElement)
    fireEvent.keyDown(row, { key: 'Enter' })

    await waitFor(() => expect(openSpy).toHaveBeenCalled())
    vi.unstubAllGlobals()
    container.remove()
  })

  it('Space 同样打开预览（W-P1-4 回归）', async () => {
    const openSpy = vi.fn()
    vi.stubGlobal('open', openSpy)
    apiMock.listFolderEntries.mockResolvedValue(entries([], ['a.pdf']))

    const { container } = renderTree()
    const row = await waitFor(() => within(container).getByText('a.pdf').closest('[role="button"]') as HTMLElement)
    fireEvent.keyDown(row, { key: ' ' })

    await waitFor(() => expect(openSpy).toHaveBeenCalled())
    vi.unstubAllGlobals()
    container.remove()
  })

  it('右键文件弹出菜单，含重命名与删除', async () => {
    apiMock.listFolderEntries.mockResolvedValue(entries([], ['a.pdf']))
    const { container } = renderTree()
    const row = await waitFor(() => within(container).getByText('a.pdf').closest('[role="button"]') as HTMLElement)

    fireEvent.contextMenu(row, { clientX: 100, clientY: 100 })
    await waitFor(() => expect(document.querySelector('[role="menu"]')).toBeTruthy())

    const labels = Array.from(document.querySelectorAll('[role="menuitem"]')).map((i) => i.textContent)
    expect(labels.some((l) => l?.includes('重命名'))).toBe(true)
    expect(labels.some((l) => l?.includes('删除'))).toBe(true)
    container.remove()
  })
})
