// @vitest-environment jsdom
/**
 * ReviewLaunchDrawer 测试（jsdom）。
 *
 * 这是「先定参数再让 AI 跑」的入口，契约错了整批建议都会方向反：
 * - 立场可选、默认甲方；
 * - 至少选一项审查内容，全不选要拦住；
 * - 交代 chips 与 textarea 双向同步；
 * - 提交顺序：取文件 → 上传 → 确认立场（缺一步都会导致流水线不启动）。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api', () => ({
  uploadContract: vi.fn(),
  confirmParty: vi.fn(),
  listRevisions: vi.fn(),
  resolveRevision: vi.fn(),
  getTaskStatus: vi.fn(),
}))

import { confirmParty, uploadContract } from '../api'
import { ReviewLaunchDrawer } from './ReviewLaunchDrawer'

const uploadMock = vi.mocked(uploadContract)
const confirmMock = vi.mocked(confirmParty)

function setup(over: Partial<Parameters<typeof ReviewLaunchDrawer>[0]> = {}) {
  const onStarted = vi.fn()
  const onClose = vi.fn()
  const loadFile = vi.fn().mockResolvedValue(new ArrayBuffer(8))
  render(
    <ReviewLaunchDrawer
      open
      fileName="装修工程合同.docx"
      loadFile={loadFile}
      onClose={onClose}
      onStarted={onStarted}
      {...over}
    />,
  )
  return { onStarted, onClose, loadFile }
}

beforeEach(() => {
  uploadMock.mockReset()
  confirmMock.mockReset()
})

describe('ReviewLaunchDrawer', () => {
  it('默认立场为甲方、默认勾选条款审查/错别字/评估报告', () => {
    setup()
    expect(screen.getByText('甲方')).toBeTruthy()
    const checks = screen.getAllByRole('checkbox') as HTMLInputElement[]
    expect(checks.filter((c) => c.checked)).toHaveLength(3)
  })

  it('可切换立场为乙方（按钮进入选中态）', () => {
    setup({ partyHint: 'AI 依据：抬头为甲方' })
    fireEvent.click(screen.getByText('乙方'))
    const btn = screen.getByText('乙方').closest('button') as HTMLButtonElement
    expect(btn.className).toContain('border-foreground')
  })

  it('全不选审查内容时拦住，不发起任何请求', async () => {
    const { loadFile } = setup()
    const checks = screen.getAllByRole('checkbox') as HTMLInputElement[]
    for (const c of checks.filter((x) => x.checked)) fireEvent.click(c)

    fireEvent.click(screen.getByRole('button', { name: /开始审查/ }))

    await waitFor(() => expect(screen.getByText('至少选一项审查内容')).toBeTruthy())
    expect(loadFile).not.toHaveBeenCalled()
    expect(uploadMock).not.toHaveBeenCalled()
  })

  it('完整提交：取文件 → 上传 → 确认立场与步骤 → 回调 taskId', async () => {
    uploadMock.mockResolvedValue({
      task_id: 'task-1',
      status: 'parties_identified',
      contract_title: '装修工程合同',
      parties: {},
    })
    confirmMock.mockResolvedValue({ task_id: 'task-1', status: 'confirmed' })
    const { onStarted, loadFile } = setup()

    fireEvent.click(screen.getByRole('button', { name: /开始审查/ }))

    await waitFor(() => expect(onStarted).toHaveBeenCalledWith('task-1'))

    expect(loadFile).toHaveBeenCalledTimes(1)
    expect(uploadMock).toHaveBeenCalledTimes(1)
    // 上传的是 File（带正确文件名）
    const uploaded = uploadMock.mock.calls[0]?.[0] as File
    expect(uploaded.name).toBe('装修工程合同.docx')

    // 确认里带上立场与勾选的步骤
    const payload = confirmMock.mock.calls[0]?.[1]
    if (!payload) throw new Error('confirmParty 未被调用')
    expect(payload.represented_party).toBe('party_a')
    expect(payload.selected_steps).toEqual(
      expect.arrayContaining(['contract_review', 'typo_check', 'review_report']),
    )
    expect(payload.selected_steps).not.toContain('format_document')
  })

  it('交代 chips 与 textarea 同步', () => {
    setup()
    const ta = screen.getByPlaceholderText(/客户有没有特别在意的点/) as HTMLTextAreaElement

    fireEvent.click(screen.getByRole('button', { name: '这单一定要压工期' }))
    expect(ta.value).toContain('这单一定要压工期')

    // 再点一次取消
    fireEvent.click(screen.getByRole('button', { name: '这单一定要压工期' }))
    expect(ta.value).not.toContain('这单一定要压工期')
  })

  it('客户交代必须真传给后端（否则律师写了也没用）', async () => {
    uploadMock.mockResolvedValue({
      task_id: 'task-note',
      status: 'parties_identified',
      contract_title: '装修工程合同',
      parties: {},
    })
    confirmMock.mockResolvedValue({ task_id: 'task-note', status: 'confirmed' })
    setup({ parties: { party_a: '联胜酒店', party_b: '某装饰公司' }, partyHint: '抬头命中联胜' })

    fireEvent.click(screen.getByRole('button', { name: '这单一定要压工期' }))
    fireEvent.click(screen.getByRole('button', { name: /开始审查/ }))

    await waitFor(() => expect(confirmMock).toHaveBeenCalledTimes(1))
    const payload = confirmMock.mock.calls[0]?.[1]
    if (!payload) throw new Error('confirmParty 未被调用')
    // 以前这里只弹个 toast、根本没传，模型不知道客户想压工期
    expect(payload.client_note).toContain('压工期')
    expect(payload.client_demands).toEqual(expect.arrayContaining(['这单一定要压工期']))
    // 立场方向的语义锚点：我方单位全名与判断依据
    expect(payload.our_client_name).toBe('联胜酒店')
    expect(payload.stance_basis).toBe('抬头命中联胜')
  })

  it('上传失败给出错误提示且不跳转', async () => {
    uploadMock.mockRejectedValue(new Error('文件过大'))
    const { onStarted } = setup()

    fireEvent.click(screen.getByRole('button', { name: /开始审查/ }))

    await waitFor(() => expect(screen.getByText('文件过大')).toBeTruthy())
    expect(onStarted).not.toHaveBeenCalled()
  })

  it('关闭按钮触发 onClose', () => {
    const { onClose } = setup()
    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    expect(onClose).toHaveBeenCalled()
  })
})
