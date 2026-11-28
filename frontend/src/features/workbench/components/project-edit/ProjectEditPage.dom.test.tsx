// @vitest-environment jsdom
/**
 * 项目编辑页的接线测试（jsdom）。
 *
 * 钉住的是「这一页会不会写错数据」，不是排版：
 * - 只提交改过的字段；没改动时保存不可点；
 * - 收费改动必须先过二次确认，确认后带 `confirm_finance=true`
 *   （不带的话后端直接 400「关键财务操作需二次确认」）；
 * - 校验不通过时一个请求都不许发；
 * - 保存成功要回详情页，并把新值写进详情页用的同一个缓存键。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ getContract: vi.fn(), updateContract: vi.fn() }))
vi.mock('../../api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api')>()),
  ...api,
}))

const nav = vi.hoisted(() => ({ navigate: vi.fn() }))
vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => nav.navigate }
})

const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }))
vi.mock('sonner', () => ({ toast: toastMock }))

import type { ContractListItem } from '../../types'
import { ProjectEditPage } from './ProjectEditPage'

const CONTRACT = {
  id: 7,
  name: '某银行与某公司金融借款合同纠纷诉讼委托合同',
  case_type: 'civil',
  status: 'active',
  specified_date: '2026-03-11',
  start_date: '2026-03-11',
  end_date: null,
  is_filed: false,
  fee_mode: '固定收费',
  fixed_amount: '50000.00',
  risk_rate: null,
  custom_terms: '',
  representation_stages: ['一审'],
} as unknown as ContractListItem

function renderPage(path = '/projects/7/edit') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/projects/:id/edit" element={<ProjectEditPage />} />
          <Route path="/projects" element={<div>PROJECT_LIST</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  api.getContract.mockResolvedValue(CONTRACT)
  api.updateContract.mockImplementation(async (_id: number, payload: object) => ({
    ...CONTRACT,
    ...payload,
  }))
})

describe('ProjectEditPage · 基本渲染', () => {
  it('把合同现有值填进表单（收费标签回填成代码对应的选项）', async () => {
    renderPage()
    const name = (await screen.findByDisplayValue(CONTRACT.name)) as HTMLInputElement
    expect(name.value).toBe(CONTRACT.name)
    // 固定收费 → FIXED 选项被选中
    const fee = screen.getByLabelText('收费方式') as HTMLSelectElement
    expect(fee.value).toBe('FIXED')
    // 中文标签「一审」回填成代码 first_trial 的勾选状态
    expect((screen.getByLabelText('一审') as HTMLInputElement).checked).toBe(true)
  })

  it('没有改动时保存不可点（避免发空 PUT）', async () => {
    renderPage()
    const save = await screen.findByRole('button', { name: '保存' })
    expect((save as HTMLButtonElement).disabled).toBe(true)
  })

  it('非法 id 重定向回项目列表', async () => {
    renderPage('/projects/abc/edit')
    expect(await screen.findByText('PROJECT_LIST')).toBeTruthy()
    expect(api.getContract).not.toHaveBeenCalled()
  })
})

describe('ProjectEditPage · 保存', () => {
  it('只提交改过的字段，并按 new 值刷新缓存后回详情页', async () => {
    renderPage()
    const name = (await screen.findByDisplayValue(CONTRACT.name)) as HTMLInputElement
    fireEvent.change(name, { target: { value: '新名字' } })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))

    await waitFor(() => expect(api.updateContract).toHaveBeenCalledTimes(1))
    expect(api.updateContract).toHaveBeenCalledWith(7, { name: '新名字' }, { confirmFinance: false })
    await waitFor(() => expect(nav.navigate).toHaveBeenCalledWith('/projects/7', { replace: true }))
    expect(toastMock.success).toHaveBeenCalledWith('已保存')
  })

  it('校验不通过时不发请求（清空名称 → 报错）', async () => {
    renderPage()
    const name = (await screen.findByDisplayValue(CONTRACT.name)) as HTMLInputElement
    fireEvent.change(name, { target: { value: '  ' } })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))

    expect(await screen.findByText('名称不能为空')).toBeTruthy()
    expect(api.updateContract).not.toHaveBeenCalled()
  })

  it('改收费先弹二次确认，确认后带 confirm_finance', async () => {
    renderPage()
    const amount = (await screen.findByDisplayValue('50000.00')) as HTMLInputElement
    fireEvent.change(amount, { target: { value: '60000' } })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))

    // 还没发请求：先让人看清楚代价
    expect(await screen.findByText('确认修改收费？')).toBeTruthy()
    expect(api.updateContract).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: '确认保存' }))
    await waitFor(() =>
      expect(api.updateContract).toHaveBeenCalledWith(7, { fixed_amount: 60000 }, { confirmFinance: true }),
    )
  })

  it('保存失败：后端文案原样展示，且停在编辑页不清空输入', async () => {
    api.updateContract.mockRejectedValueOnce(new Error('关键财务操作需二次确认'))
    renderPage()
    const amount = (await screen.findByDisplayValue('50000.00')) as HTMLInputElement
    fireEvent.change(amount, { target: { value: '60000' } })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))
    fireEvent.click(await screen.findByRole('button', { name: '确认保存' }))

    await waitFor(() => expect(toastMock.error).toHaveBeenCalled())
    expect(nav.navigate).not.toHaveBeenCalled()
    expect((screen.getByDisplayValue('60000') as HTMLInputElement).value).toBe('60000')
  })
})
