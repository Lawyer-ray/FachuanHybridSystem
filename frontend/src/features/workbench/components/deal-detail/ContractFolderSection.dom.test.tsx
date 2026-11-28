// @vitest-environment jsdom
/**
 * 合同文件夹一节：**先查绑定再决定要不要拉目录**。
 *
 * 未绑定时不请求 `folder-entries`（否则控制台一条 404，界面上也只有一句兜底错误），
 * 而是给一句说明 + 一个手工绑定入口；绑定走 `POST /contracts/{id}/folder-binding`。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  getContractFolderBinding: vi.fn(),
  bindContractFolder: vi.fn(),
  listFolderEntries: vi.fn(async () => ({ browsable: true, folders: [], files: [], message: null })),
}))
vi.mock('../../api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api')>()),
  ...api,
}))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import { ContractFolderSection } from './ContractFolderSection'

const BINDING = {
  id: 1,
  contract_id: 7,
  folder_path: '/tmp/合同',
  folder_path_display: '/tmp/合同',
  storage_type: 'local',
  is_accessible: true,
}

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('ContractFolderSection', () => {
  it('未绑定：给说明 + 绑定入口，且**不**去拉目录（避免 404 噪音）', async () => {
    api.getContractFolderBinding.mockResolvedValue(null)
    wrap(<ContractFolderSection contractId={7} />)

    expect(await screen.findByText(/还没有绑定合同文件夹/)).toBeTruthy()
    expect(screen.getByText('＋ 绑定文件夹')).toBeTruthy()
    expect(api.listFolderEntries).not.toHaveBeenCalled()
  })

  it('已绑定：渲染目录树（这时才请求 folder-entries）', async () => {
    api.getContractFolderBinding.mockResolvedValue(BINDING)
    wrap(<ContractFolderSection contractId={7} />)

    await waitFor(() => expect(api.listFolderEntries).toHaveBeenCalled())
    expect(screen.queryByText(/还没有绑定合同文件夹/)).toBeNull()
  })

  it('手工绑定：提交绝对路径后调用绑定接口', async () => {
    api.getContractFolderBinding.mockResolvedValueOnce(null).mockResolvedValue(BINDING)
    api.bindContractFolder.mockResolvedValue(BINDING)
    wrap(<ContractFolderSection contractId={7} />)

    fireEvent.click(await screen.findByText('＋ 绑定文件夹'))
    fireEvent.change(await screen.findByLabelText('文件夹路径'), {
      target: { value: '/Users/x/新工作/200-诉讼/某某案' },
    })
    fireEvent.click(screen.getByRole('button', { name: '绑定' }))

    await waitFor(() =>
      expect(api.bindContractFolder).toHaveBeenCalledWith(7, '/Users/x/新工作/200-诉讼/某某案'),
    )
  })

  it('绑定失败：错误原样展示，弹窗不关', async () => {
    api.getContractFolderBinding.mockResolvedValue(null)
    api.bindContractFolder.mockRejectedValueOnce(new Error('路径不存在'))
    wrap(<ContractFolderSection contractId={7} />)

    fireEvent.click(await screen.findByText('＋ 绑定文件夹'))
    fireEvent.change(await screen.findByLabelText('文件夹路径'), { target: { value: '/nope' } })
    fireEvent.click(screen.getByRole('button', { name: '绑定' }))

    expect(await screen.findByText(/路径不存在/)).toBeTruthy()
  })
})
