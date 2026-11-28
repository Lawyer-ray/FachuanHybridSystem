// @vitest-environment jsdom
/**
 * 记日志 / 新增期限两个弹窗的接线测试。
 *
 * 钉住的是**请求形状**（后端字段名与二选一绑定），不是排版：
 * - 记日志必须带 case_id（合同没有时间轴），勾了「同时设期限」才多带 reminder_*；
 * - 新增期限挂「委托」与挂「案件」分别只发 contract_id / case_id —— 后端对
 *   ReminderIn 的三选一有 CheckConstraint，多发一个 null 也算一次绑定尝试；
 * - 校验没过不许发请求。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  createReminder: vi.fn(),
  createCaseLog: vi.fn(),
  listReminderTypes: vi.fn(),
}))
vi.mock('../../api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api')>()),
  ...api,
}))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import { AddDeadlineDialog } from './AddDeadlineDialog'
import { AddLogDialog } from './AddLogDialog'

function wrap(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>)
}

beforeEach(() => {
  vi.clearAllMocks()
  api.listReminderTypes.mockResolvedValue([
    { value: 'hearing', label: '开庭' },
    { value: 'other', label: '其他' },
  ])
  api.createReminder.mockResolvedValue(undefined)
  api.createCaseLog.mockResolvedValue({ id: 1 })
})

describe('AddLogDialog', () => {
  it('只记日志：发 case_id + content，不带 reminder 字段', async () => {
    const onSaved = vi.fn()
    wrap(<AddLogDialog open caseId={11} caseLabel="一审" onClose={vi.fn()} onSaved={onSaved} />)

    fireEvent.change(screen.getByLabelText('日志内容'), { target: { value: '收到传票' } })
    fireEvent.click(screen.getByRole('button', { name: '记下' }))

    await waitFor(() =>
      expect(api.createCaseLog).toHaveBeenCalledWith({ caseId: 11, content: '收到传票' }),
    )
    expect(onSaved).toHaveBeenCalled()
  })

  it('勾了「同时设一个期限」才带 reminderType / reminderTime', async () => {
    wrap(<AddLogDialog open caseId={11} caseLabel="一审" onClose={vi.fn()} onSaved={vi.fn()} />)

    fireEvent.change(screen.getByLabelText('日志内容'), { target: { value: '收到传票' } })
    fireEvent.click(screen.getByLabelText('同时设一个期限'))
    fireEvent.change(screen.getByLabelText('到期日期'), { target: { value: '2026-12-20' } })
    fireEvent.change(screen.getByLabelText('到期时间'), { target: { value: '09:30' } })
    fireEvent.click(screen.getByRole('button', { name: '记下' }))

    await waitFor(() => expect(api.createCaseLog).toHaveBeenCalledTimes(1))
    const arg = api.createCaseLog.mock.calls[0]![0]
    expect(arg).toMatchObject({ caseId: 11, content: '收到传票', reminderTime: '2026-12-20T09:30:00' })
    expect(typeof arg.reminderType).toBe('string')
  })

  it('内容为空时提交按钮不可点（不发空日志）', () => {
    wrap(<AddLogDialog open caseId={11} caseLabel="一审" onClose={vi.fn()} onSaved={vi.fn()} />)
    expect((screen.getByRole('button', { name: '记下' }) as HTMLButtonElement).disabled).toBe(true)
  })
})

describe('AddDeadlineDialog', () => {
  it('默认挂「整个委托」：只发 contract_id', async () => {
    const onSaved = vi.fn()
    wrap(
      <AddDeadlineDialog
        open
        contractId={7}
        cases={[{ id: 3, proc: '一审' }]}
        onClose={vi.fn()}
        onSaved={onSaved}
      />,
    )

    fireEvent.change(screen.getByLabelText('期限内容'), { target: { value: '开庭' } })
    fireEvent.click(screen.getByRole('button', { name: '新增' }))

    await waitFor(() => expect(api.createReminder).toHaveBeenCalledTimes(1))
    const arg = api.createReminder.mock.calls[0]![0]
    expect(arg).toMatchObject({ contractId: 7, content: '开庭' })
    expect(arg).not.toHaveProperty('caseId')
    expect(onSaved).toHaveBeenCalled()
  })

  it('切到某个案件：只发 case_id，不再发 contract_id', async () => {
    wrap(
      <AddDeadlineDialog
        open
        contractId={7}
        cases={[{ id: 3, proc: '一审' }]}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />,
    )

    fireEvent.change(screen.getByLabelText('期限归属'), { target: { value: 'case:3' } })
    fireEvent.change(screen.getByLabelText('期限内容'), { target: { value: '举证期限' } })
    fireEvent.click(screen.getByRole('button', { name: '新增' }))

    await waitFor(() => expect(api.createReminder).toHaveBeenCalledTimes(1))
    const arg = api.createReminder.mock.calls[0]![0]
    expect(arg).toMatchObject({ caseId: 3, content: '举证期限' })
    expect(arg).not.toHaveProperty('contractId')
  })

  it('类型下拉来自后端 /reminders/types（不在前端硬编码中文）', async () => {
    wrap(
      <AddDeadlineDialog open contractId={7} cases={[]} onClose={vi.fn()} onSaved={vi.fn()} />,
    )
    await waitFor(() => expect(api.listReminderTypes).toHaveBeenCalled())
    expect(await screen.findByRole('option', { name: '开庭' })).toBeTruthy()
  })
})
