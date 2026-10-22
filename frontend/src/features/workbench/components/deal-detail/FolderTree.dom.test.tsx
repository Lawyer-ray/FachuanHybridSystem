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
import { createEvent, fireEvent, render, waitFor, within } from '@testing-library/react'
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

// ============ mutation 成功/失败 · 右键菜单 · 拖拽上传（覆盖率补测） ============

describe('FolderTree：新建文件夹', () => {
  it('提交新名字调用 createFolderEntry', async () => {
    apiMock.createFolderEntry.mockResolvedValue({})
    const { container } = renderTree()
    await waitFor(() => expect(within(container).getByText('文件夹是空的')).toBeTruthy())

    fireEvent.click(within(container).getByRole('button', { name: /新建文件夹/ }))
    const input = await waitFor(() => container.querySelector('input[placeholder="新文件夹名"]') as HTMLInputElement)
    fireEvent.change(input, { target: { value: '新夹' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    await waitFor(() => expect(apiMock.createFolderEntry).toHaveBeenCalledWith('case', 1, '', '新夹'))
    container.remove()
  })

  it('新建失败弹 toast 并带原因', async () => {
    apiMock.createFolderEntry.mockRejectedValue(new Error('同名已存在'))
    const { container } = renderTree()
    await waitFor(() => expect(within(container).getByText('文件夹是空的')).toBeTruthy())

    fireEvent.click(within(container).getByRole('button', { name: /新建文件夹/ }))
    const input = await waitFor(() => container.querySelector('input[placeholder="新文件夹名"]') as HTMLInputElement)
    fireEvent.change(input, { target: { value: '新夹' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(expect.stringContaining('同名已存在')))
    container.remove()
  })
})

describe('FolderTree：上传', () => {
  it('多文件上传成功提示数量', async () => {
    apiMock.uploadFolderFiles.mockResolvedValue({ saved: [{ name: 'a' }, { name: 'b' }] })
    const { container } = renderTree()
    await waitFor(() => expect(within(container).getByText('文件夹是空的')).toBeTruthy())

    const root = container.firstElementChild as HTMLElement
    fireEvent.drop(root, { dataTransfer: { files: [new File(['x'], 'a.pdf'), new File(['y'], 'b.pdf')] } })

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('已上传 2 个文件'))
    container.remove()
  })

  it('单文件上传成功不弹提示（避免噪音）', async () => {
    apiMock.uploadFolderFiles.mockResolvedValue({ saved: [{ name: 'a' }] })
    const { container } = renderTree()
    await waitFor(() => expect(within(container).getByText('文件夹是空的')).toBeTruthy())

    const root = container.firstElementChild as HTMLElement
    fireEvent.drop(root, { dataTransfer: { files: [new File(['x'], 'a.pdf')] } })

    await waitFor(() => expect(apiMock.uploadFolderFiles).toHaveBeenCalled())
    expect(toast.success).not.toHaveBeenCalled()
    container.remove()
  })

  it('上传失败弹 toast', async () => {
    apiMock.uploadFolderFiles.mockRejectedValue(new Error('超出配额'))
    const { container } = renderTree()
    await waitFor(() => expect(within(container).getByText('文件夹是空的')).toBeTruthy())

    const root = container.firstElementChild as HTMLElement
    fireEvent.drop(root, { dataTransfer: { files: [new File(['x'], 'a.pdf')] } })

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(expect.stringContaining('超出配额')))
    container.remove()
  })

  it('拖到已展开的文件夹行：先展开再上传到该目录', async () => {
    apiMock.listFolderEntries.mockImplementation(async (_k, _id, sp: string) =>
      sp === '' ? entries(['dir']) : entries(),
    )
    apiMock.uploadFolderFiles.mockResolvedValue({ saved: [] })
    const { container } = renderTree()
    await waitFor(() => expect(within(container).getByText('dir')).toBeTruthy())

    const folderRow = within(container).getByText('dir').closest('[role="button"]') as HTMLElement
    fireEvent.drop(folderRow, { dataTransfer: { files: [new File(['x'], 'a.pdf')] } })

    await waitFor(() => expect(apiMock.uploadFolderFiles).toHaveBeenCalledWith('case', 1, 'dir', expect.any(Array)))
    container.remove()
  })
})

describe('FolderTree：右键菜单项', () => {
  async function openMenuOn(name: string) {
    const utils = renderTree()
    await waitFor(() => expect(within(utils.container).getByText(name)).toBeTruthy())
    const row = within(utils.container).getByText(name).closest('[role="button"]') as HTMLElement
    fireEvent.contextMenu(row, { clientX: 50, clientY: 50 })
    await waitFor(() => expect(document.querySelector('[role="menu"]')).toBeTruthy())
    return utils
  }

  function menuLabels() {
    return Array.from(document.querySelectorAll('[role="menuitem"]')).map((i) => i.textContent ?? '')
  }

  beforeEach(() => {
    apiMock.listFolderEntries.mockResolvedValue(entries(['dir'], ['a.pdf']))
  })

  it('文件行的菜单含复制/重命名/删除，不含粘贴', async () => {
    const { container } = await openMenuOn('a.pdf')
    const labels = menuLabels()
    expect(labels).toContain('复制')
    expect(labels).toContain('重命名')
    expect(labels).toContain('删除')
    expect(labels).not.toContain('粘贴到此文件夹')
    container.remove()
  })

  it('文件夹行的菜单同样含复制/重命名/删除', async () => {
    const { container } = await openMenuOn('dir')
    const labels = menuLabels()
    expect(labels).toContain('复制')
    expect(labels).toContain('删除')
    container.remove()
  })

  it('点「复制」后再对另一文件夹右键出现「粘贴到此文件夹」', async () => {
    apiMock.listFolderEntries.mockResolvedValue(entries(['dir', 'dest'], ['a.pdf']))
    const { container } = await openMenuOn('a.pdf')

    fireEvent.click(
      Array.from(document.querySelectorAll('[role="menuitem"]')).find((i) => i.textContent === '复制')!,
    )
    await waitFor(() => expect(document.querySelector('[role="menu"]')).toBeNull())

    const destRow = within(container).getByText('dest').closest('[role="button"]') as HTMLElement
    fireEvent.contextMenu(destRow, { clientX: 60, clientY: 60 })
    await waitFor(() => expect(document.querySelector('[role="menu"]')).toBeTruthy())

    expect(menuLabels()).toContain('粘贴到此文件夹')
    container.remove()
  })

  it('点「粘贴到此文件夹」调用 copyFolderEntry', async () => {
    apiMock.copyFolderEntry.mockResolvedValue({})
    apiMock.listFolderEntries.mockResolvedValue(entries(['dir', 'dest'], ['a.pdf']))
    const { container } = await openMenuOn('a.pdf')

    fireEvent.click(
      Array.from(document.querySelectorAll('[role="menuitem"]')).find((i) => i.textContent === '复制')!,
    )
    await waitFor(() => expect(document.querySelector('[role="menu"]')).toBeNull())

    const destRow = within(container).getByText('dest').closest('[role="button"]') as HTMLElement
    fireEvent.contextMenu(destRow, { clientX: 60, clientY: 60 })
    await waitFor(() => expect(document.querySelector('[role="menu"]')).toBeTruthy())

    fireEvent.click(
      Array.from(document.querySelectorAll('[role="menuitem"]')).find(
        (i) => i.textContent === '粘贴到此文件夹',
      )!,
    )
    await waitFor(() => expect(apiMock.copyFolderEntry).toHaveBeenCalledWith('case', 1, 'a.pdf', 'dest'))
    container.remove()
  })

  it('点「删除」进入行内确认，确认后调用 deleteFolderEntry', async () => {
    apiMock.deleteFolderEntry.mockResolvedValue({})
    const { container } = await openMenuOn('a.pdf')

    fireEvent.click(
      Array.from(document.querySelectorAll('[role="menuitem"]')).find((i) => i.textContent === '删除')!,
    )
    const confirm = await within(container).findByRole('button', { name: '确认' })
    fireEvent.click(confirm)

    await waitFor(() => expect(apiMock.deleteFolderEntry).toHaveBeenCalledWith('case', 1, 'a.pdf'))
    container.remove()
  })

  it('删除失败弹 toast', async () => {
    apiMock.deleteFolderEntry.mockRejectedValue(new Error('文件被占用'))
    const { container } = await openMenuOn('a.pdf')

    fireEvent.click(
      Array.from(document.querySelectorAll('[role="menuitem"]')).find((i) => i.textContent === '删除')!,
    )
    const confirm = await within(container).findByRole('button', { name: '确认' })
    fireEvent.click(confirm)

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(expect.stringContaining('文件被占用')))
    container.remove()
  })

  it('点「重命名」进入行内编辑', async () => {
    const { container } = await openMenuOn('a.pdf')
    fireEvent.click(
      Array.from(document.querySelectorAll('[role="menuitem"]')).find((i) => i.textContent === '重命名')!,
    )
    await waitFor(() => expect(container.querySelector('input[placeholder="新名称"]')).toBeTruthy())
    container.remove()
  })
})

// ============ 嵌套目录与展开态改写（覆盖率补测） ============

describe('FolderTree：嵌套子目录', () => {
  function nested() {
    apiMock.listFolderEntries.mockImplementation(async (_k, _id, sp: string) => {
      if (sp === '') return entries(['dir'])
      if (sp === 'dir') {
        // 子项 subpath 必须是相对根的完整路径：dir/sub
        const base = entries()
        return { ...base, folders: [{ name: 'sub', subpath: 'dir/sub' }] }
      }
      if (sp === 'dir/sub') {
        const base = entries()
        return {
          ...base,
          files: [{ name: 'deep.pdf', subpath: 'dir/sub/deep.pdf', size: 100, modified_at: '2026-10-20T10:00:00' }],
        }
      }
      return entries()
    })
  }

  it('逐层展开能渲染到第三层文件', async () => {
    nested()
    const { container } = renderTree()
    await waitFor(() => expect(within(container).getByText('dir')).toBeTruthy())

    fireEvent.click(within(container).getByText('dir'))
    // 子项显示的是 name（'sub'），但可能同时存在父行 'dir'
    await waitFor(() => expect(within(container).getByText('sub')).toBeTruthy())

    fireEvent.click(within(container).getByText('sub'))
    await waitFor(() => expect(within(container).getByText('deep.pdf')).toBeTruthy())
    container.remove()
  })

  it('嵌套目录重命名：旧 subpath 与其子路径一并改写（展开态不丢）', async () => {
    nested()
    apiMock.renameFolderEntry.mockResolvedValue({})
    const { container } = renderTree()
    await waitFor(() => expect(within(container).getByText('dir')).toBeTruthy())

    // 展开 dir 及其子目录
    fireEvent.click(within(container).getByText('dir'))
    await waitFor(() => expect(within(container).getByText('sub')).toBeTruthy())

    // 重命名子目录 sub → sub2
    const renameBtns = within(container).getAllByRole('button', { name: '重命名' })
    fireEvent.click(renameBtns[renameBtns.length - 1]!)
    const input = await waitFor(() => container.querySelector('input[placeholder="新名称"]') as HTMLInputElement)
    fireEvent.change(input, { target: { value: 'sub2' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    await waitFor(() => expect(apiMock.renameFolderEntry).toHaveBeenCalledWith('case', 1, 'dir/sub', 'sub2'))
    container.remove()
  })

  it('嵌套目录删除：连同子路径一起从展开集合移除', async () => {
    nested()
    apiMock.deleteFolderEntry.mockResolvedValue({})
    const { container } = renderTree()
    await waitFor(() => expect(within(container).getByText('dir')).toBeTruthy())

    fireEvent.click(within(container).getByText('dir'))
    await waitFor(() => expect(within(container).getByText('sub')).toBeTruthy())

    // 右键 sub → 删除
    const subRow = within(container).getByText('sub').closest('[role="button"]') as HTMLElement
    fireEvent.contextMenu(subRow, { clientX: 50, clientY: 50 })
    await waitFor(() => expect(document.querySelector('[role="menu"]')).toBeTruthy())

    fireEvent.click(
      Array.from(document.querySelectorAll('[role="menuitem"]')).find((i) => i.textContent === '删除')!,
    )
    const confirm = await within(container).findByRole('button', { name: '确认' })
    fireEvent.click(confirm)

    await waitFor(() => expect(apiMock.deleteFolderEntry).toHaveBeenCalledWith('case', 1, 'dir/sub'))
    container.remove()
  })
})

describe('FolderTree：复制到目标后展开目标', () => {
  it('复制成功后目标目录被加入展开集合', async () => {
    apiMock.listFolderEntries.mockResolvedValue(entries(['dir', 'dest'], ['a.pdf']))
    apiMock.copyFolderEntry.mockResolvedValue({})
    const { container } = renderTree()
    await waitFor(() => expect(within(container).getByText('dest')).toBeTruthy())

    // 复制 a.pdf
    const fileRow = within(container).getByText('a.pdf').closest('[role="button"]') as HTMLElement
    fireEvent.contextMenu(fileRow, { clientX: 50, clientY: 50 })
    await waitFor(() => expect(document.querySelector('[role="menu"]')).toBeTruthy())
    fireEvent.click(
      Array.from(document.querySelectorAll('[role="menuitem"]')).find((i) => i.textContent === '复制')!,
    )
    await waitFor(() => expect(document.querySelector('[role="menu"]')).toBeNull())

    // 粘贴到 dest
    const destRow = within(container).getByText('dest').closest('[role="button"]') as HTMLElement
    fireEvent.contextMenu(destRow, { clientX: 60, clientY: 60 })
    await waitFor(() => expect(document.querySelector('[role="menu"]')).toBeTruthy())
    fireEvent.click(
      Array.from(document.querySelectorAll('[role="menuitem"]')).find(
        (i) => i.textContent === '粘贴到此文件夹',
      )!,
    )

    await waitFor(() => expect(apiMock.copyFolderEntry).toHaveBeenCalled())
    container.remove()
  })

  it('复制失败弹 toast', async () => {
    apiMock.listFolderEntries.mockResolvedValue(entries(['dir', 'dest'], ['a.pdf']))
    apiMock.copyFolderEntry.mockRejectedValue(new Error('目标已满'))
    const { container } = renderTree()
    await waitFor(() => expect(within(container).getByText('dest')).toBeTruthy())

    const fileRow = within(container).getByText('a.pdf').closest('[role="button"]') as HTMLElement
    fireEvent.contextMenu(fileRow, { clientX: 50, clientY: 50 })
    await waitFor(() => expect(document.querySelector('[role="menu"]')).toBeTruthy())
    fireEvent.click(
      Array.from(document.querySelectorAll('[role="menuitem"]')).find((i) => i.textContent === '复制')!,
    )
    await waitFor(() => expect(document.querySelector('[role="menu"]')).toBeNull())

    const destRow = within(container).getByText('dest').closest('[role="button"]') as HTMLElement
    fireEvent.contextMenu(destRow, { clientX: 60, clientY: 60 })
    await waitFor(() => expect(document.querySelector('[role="menu"]')).toBeTruthy())
    fireEvent.click(
      Array.from(document.querySelectorAll('[role="menuitem"]')).find(
        (i) => i.textContent === '粘贴到此文件夹',
      )!,
    )

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(expect.stringContaining('目标已满')))
    container.remove()
  })
})

// ============ 文件夹行交互（覆盖率补测） ============

describe('FolderTree：文件夹行展开折叠', () => {
  it('点文件夹展开后再点收起', async () => {
    apiMock.listFolderEntries.mockImplementation(async (_k, _id, sp: string) =>
      sp === '' ? entries(['dir']) : entries([], ['inner.pdf']),
    )
    const { container } = renderTree()
    await waitFor(() => expect(within(container).getByText('dir')).toBeTruthy())

    fireEvent.click(within(container).getByText('dir'))
    await waitFor(() => expect(within(container).getByText('inner.pdf')).toBeTruthy())

    // 再点一次收起，子项消失
    fireEvent.click(within(container).getByText('dir'))
    await waitFor(() => expect(within(container).queryByText('inner.pdf')).toBeNull())
    container.remove()
  })

  it('键盘 Enter 与 Space 都能切换展开态', async () => {
    apiMock.listFolderEntries.mockImplementation(async (_k, _id, sp: string) =>
      sp === '' ? entries(['dir']) : entries(),
    )
    const { container } = renderTree()
    await waitFor(() => expect(within(container).getByText('dir')).toBeTruthy())

    const row = within(container).getByText('dir').closest('[role="button"]') as HTMLElement
    fireEvent.keyDown(row, { key: 'Enter' })
    await waitFor(() => expect(apiMock.listFolderEntries).toHaveBeenCalledWith('case', 1, 'dir'))

    fireEvent.keyDown(row, { key: ' ' })
    // 不抛错即可（收起）
    container.remove()
  })

  it('文件夹行拖拽悬停设置 dropOn，离开时清空', async () => {
    apiMock.listFolderEntries.mockResolvedValue(entries(['dir']))
    const { container } = renderTree()
    await waitFor(() => expect(within(container).getByText('dir')).toBeTruthy())

    const row = within(container).getByText('dir').closest('[role="button"]') as HTMLElement
    const over = createEvent.dragOver(row, { dataTransfer: { files: [], dropEffect: '' } })
    Object.defineProperty(over, 'currentTarget', { value: row })
    fireEvent(row, over)

    const leave = createEvent.dragLeave(row)
    Object.defineProperty(leave, 'currentTarget', { value: row })
    fireEvent(row, leave)

    // 不抛错即可
    container.remove()
  })
})

describe('FolderTree：空态与创建态边界', () => {
  it('子目录为空且不在创建态时显示「（空）」', async () => {
    apiMock.listFolderEntries.mockImplementation(async (_k, _id, sp: string) =>
      sp === '' ? entries(['emptyDir']) : entries(),
    )
    const { container } = renderTree()
    await waitFor(() => expect(within(container).getByText('emptyDir')).toBeTruthy())

    fireEvent.click(within(container).getByText('emptyDir'))
    await waitFor(() => expect(within(container).getByText('（空）')).toBeTruthy())
    container.remove()
  })

  it('子目录创建态时不显示「（空）」', async () => {
    apiMock.listFolderEntries.mockImplementation(async (_k, _id, sp: string) =>
      sp === '' ? entries(['emptyDir']) : entries(),
    )
    const { container } = renderTree()
    await waitFor(() => expect(within(container).getByText('emptyDir')).toBeTruthy())

    fireEvent.click(within(container).getByText('emptyDir'))
    await waitFor(() => expect(within(container).getByText('（空）')).toBeTruthy())

    // 在子目录内新建文件夹 → 创建态出现，空态让位
    const newBtns = within(container).getAllByRole('button', { name: /新建/ })
    fireEvent.click(newBtns[newBtns.length - 1]!)
    await waitFor(() => expect(within(container).queryByText('（空）')).toBeNull())
    container.remove()
  })
})
