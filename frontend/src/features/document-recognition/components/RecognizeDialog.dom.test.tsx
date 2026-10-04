// @vitest-environment jsdom
/**
 * RecognizeDialog（记一笔 · 识别并确认弹窗）组件渲染单测（jsdom + 真实 timers）。
 *
 * mock 边界：../api 全量接口 + ../hooks/use-recognize（识别编排桩，phase 可控）。
 * 组件已拆出 use-candidate-rows / use-confirm-actions，这里走真实实现，
 * 验证弹窗对两条路径的编排：文字模式（候选行编辑/勾选/写入回调/失败保持打开）
 * 与文件模式（submitting 等待态、error 态、ready 后候选确认与忽略下推 confirmDates）。
 */
import { type ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api', () => ({
  recognizeFile: vi.fn(),
  getTask: vi.fn(),
  bindTask: vi.fn(),
  confirmDates: vi.fn(),
  revokeDate: vi.fn(),
  searchCasesForBinding: vi.fn(),
}))
vi.mock('../hooks/use-recognize', () => ({ useRecognize: vi.fn() }))

import { confirmDates } from '../api'
import type { CandidateRow } from '../domain'
import { useRecognize } from '../hooks/use-recognize'
import type { TaskOut } from '../types'

import { RecognizeDialog } from './RecognizeDialog'

const useRecognizeMock = vi.mocked(useRecognize)
const confirmDatesMock = vi.mocked(confirmDates)

const onClose = vi.fn()
const onSaved = vi.fn()
const onConfirmText = vi.fn()

function makeTextRow(key: string, over: Partial<CandidateRow> = {}): CandidateRow {
  return {
    key,
    candidateId: null,
    checked: true,
    dueLocal: '2026-10-05T09:30',
    reminderType: 'hearing',
    label: '开庭',
    contextText: '定于10月5日上午9:30开庭',
    content: '定于10月5日上午9:30开庭',
    source: 'text',
    confidence: null,
    status: 'pending',
    reminderId: null,
    ...over,
  }
}

function makeTask(partial: Partial<TaskOut> = {}): TaskOut {
  return {
    task_id: 5,
    status: 'success',
    file_path: null,
    file_url: null,
    recognition: null,
    binding: null,
    date_candidates: [],
    contacts: [],
    address: null,
    recommendations: [],
    binding_mode: 'standalone',
    date_confirmation_status: null,
    error_message: null,
    created_at: '2026-10-01T10:00:00',
    finished_at: null,
    ...partial,
  }
}

function stubRecognize(over: Partial<ReturnType<typeof useRecognize>> = {}) {
  useRecognizeMock.mockReturnValue({
    phase: 'idle',
    hint: '',
    error: null,
    task: null,
    submit: vi.fn(),
    refresh: vi.fn(async () => {}),
    reset: vi.fn(),
    ...over,
  })
}

/** CaseBindingSection 内部有 useQuery，文件模式 ready 后需要 QueryClient 上下文 */
function withQuery(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
}

function setupTextMode(rows: CandidateRow[]) {
  return render(
    withQuery(
      <RecognizeDialog
        open
        onClose={onClose}
        onSaved={onSaved}
        file={null}
        textRows={rows}
        onConfirmText={onConfirmText}
      />,
    ),
  )
}

function setupFileMode(file: File | null, recognize: Partial<ReturnType<typeof useRecognize>>) {
  stubRecognize(recognize)
  return render(withQuery(<RecognizeDialog open onClose={onClose} onSaved={onSaved} file={file} />))
}

beforeEach(() => {
  vi.clearAllMocks()
  stubRecognize()
  onConfirmText.mockResolvedValue(2)
  confirmDatesMock.mockResolvedValue({ success: true, results: [] })
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('RecognizeDialog 文字模式', () => {
  it('打开即渲染确认 UI：标题、说明与候选计数', () => {
    setupTextMode([makeTextRow('t-0'), makeTextRow('t-1', { contextText: '庭前会议另行通知', content: '庭前会议另行通知' })])
    expect(screen.getByText('文字记一笔 · 确认日期')).toBeTruthy()
    expect(screen.getByText('只有确认过的日期才会写入重要日期提醒')).toBeTruthy()
    expect(screen.getByText('0/2 已确认')).toBeTruthy()
    expect(screen.getByText('定于10月5日上午9:30开庭')).toBeTruthy()
    expect(screen.getByText('庭前会议另行通知')).toBeTruthy()
  })

  it('写入按钮数量随勾选变化：全取消后禁用', () => {
    setupTextMode([makeTextRow('t-0'), makeTextRow('t-1')])
    const confirmBtn = () => screen.getByRole('button', { name: '写入 0 条提醒' }) as HTMLButtonElement

    fireEvent.click(screen.getAllByTitle('取消写入')[0]!)
    expect(screen.getByRole('button', { name: '写入 1 条提醒' })).toBeTruthy()
    // 文字模式无「忽略」按钮（interactive=false）
    expect(screen.queryByText('忽略')).toBeNull()

    // 取消勾选后按钮 title 翻转为「勾选写入」，此时唯一的「取消写入」是第二行
    fireEvent.click(screen.getAllByTitle('取消写入')[0]!)
    const disabled = confirmBtn()
    expect(disabled.disabled).toBe(true)
  })

  it('行内编辑 override：改时间后写入回调携带新值', async () => {
    setupTextMode([makeTextRow('t-0')])
    const dt = screen.getByDisplayValue('2026-10-05T09:30')
    fireEvent.change(dt, { target: { value: '2026-10-06T14:00' } })
    fireEvent.click(screen.getByRole('button', { name: '写入 1 条提醒' }))
    await waitFor(() => expect(onConfirmText).toHaveBeenCalled())
    const sent = onConfirmText.mock.calls[0]?.[0] as CandidateRow[]
    expect(sent.length).toBe(1)
    expect(sent[0]?.dueLocal).toBe('2026-10-06T14:00')
  })

  it('写入成功：逐条创建回调后关闭弹窗并刷新外部状态', async () => {
    setupTextMode([makeTextRow('t-0'), makeTextRow('t-1')])
    fireEvent.click(screen.getByRole('button', { name: '写入 2 条提醒' }))
    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(onSaved).toHaveBeenCalled()
    expect(onConfirmText.mock.calls[0]?.[0]).toHaveLength(2)
  })

  it('写入失败：弹窗保持打开，可再次尝试', async () => {
    onConfirmText.mockRejectedValue(new Error('创建失败'))
    setupTextMode([makeTextRow('t-0')])
    fireEvent.click(screen.getByRole('button', { name: '写入 1 条提醒' }))
    await waitFor(() => expect(onConfirmText).toHaveBeenCalledTimes(1))
    expect(onClose).not.toHaveBeenCalled()
    expect(screen.getByText('文字记一笔 · 确认日期')).toBeTruthy()
    // busy 复位：按钮回到可点
    expect((screen.getByRole('button', { name: '写入 1 条提醒' }) as HTMLButtonElement).disabled).toBe(false)
  })

  it('无候选：空列表提示 + 写入按钮禁用', () => {
    setupTextMode([])
    expect(screen.getByText('未识别到关键日期')).toBeTruthy()
    const btn = screen.getByRole('button', { name: '写入 0 条提醒' }) as HTMLButtonElement
    expect(btn.disabled).toBe(true)
  })
})

describe('RecognizeDialog 文件模式', () => {
  const file = new File(['x'], 'summons.pdf', { type: 'application/pdf' })

  it('submitting 阶段：展示上传等待态（文件名 + hint + 三步进度），不出确认 footer', () => {
    setupFileMode(file, { phase: 'submitting', hint: '正在上传文书…' })
    // 文件名出现在标题与进度区两处
    expect(screen.getAllByText('summons.pdf').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('正在上传文书…')).toBeTruthy()
    expect(screen.getByText('上传文件')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /写入/ })).toBeNull()
  })

  it('error 阶段：展示后端错误与关闭按钮，点击关闭回调', () => {
    setupFileMode(file, { phase: 'error', error: 'LLM 解析超时' })
    expect(screen.getByText('LLM 解析超时')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '关闭' }))
    expect(onClose).toHaveBeenCalled()
  })

  it('ready + 待确认候选：默认勾选计入写入数，忽略走 confirmDates(skip)', async () => {
    const task = makeTask({
      binding: { success: true, case_id: 1, case_name: '王五案', case_log_id: null, message: null, error_code: null },
      date_candidates: [
        {
          id: 11,
          due_at: '2026-10-05T09:30:00',
          reminder_type: 'hearing',
          reminder_type_label: '开庭',
          context_text: '开庭通知',
          source: 'llm',
          confidence: null,
          status: 'pending',
          reminder_id: null,
          confirmed_at: null,
        },
      ],
    })
    const refresh = vi.fn(async () => {})
    setupFileMode(file, { phase: 'ready', task, refresh })
    expect(screen.getByText('关联案件')).toBeTruthy()
    expect(screen.getByText('已绑定案件：王五案')).toBeTruthy()
    expect(screen.getByRole('button', { name: '写入 1 条提醒' })).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '忽略' }))
    await waitFor(() =>
      expect(confirmDatesMock).toHaveBeenCalledWith(5, [{ candidate_id: 11, action: 'skip' }]),
    )
    expect(refresh).toHaveBeenCalled()
  })

  it('ready + 已全部处理：展示完成提示', () => {
    const task = makeTask({
      date_candidates: [
        {
          id: 12,
          due_at: '2026-10-05T09:30:00',
          reminder_type: 'hearing',
          reminder_type_label: '开庭',
          context_text: '',
          source: 'regex',
          confidence: 0.9,
          status: 'confirmed',
          reminder_id: 99,
          confirmed_at: '2026-10-01T11:00:00',
        },
      ],
    })
    setupFileMode(file, { phase: 'ready', task })
    expect(screen.getByText('已写入 #99')).toBeTruthy()
    expect(screen.getByText('全部处理完成')).toBeTruthy()
    const btn = screen.getByRole('button', { name: '写入 0 条提醒' }) as HTMLButtonElement
    expect(btn.disabled).toBe(true)
  })
})
