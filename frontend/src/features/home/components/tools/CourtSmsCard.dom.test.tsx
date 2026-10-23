// @vitest-environment jsdom
/**
 * CourtSmsCard 测试（jsdom）。
 *
 * 覆盖：空短信不提交、提交成功后清空并开弹窗、提交失败保留输入、
 * 处理中按钮禁用、重开入口在各 phase/outcome 下的文案、历史入口。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const flowMock = vi.hoisted(() => ({
  phase: 'idle' as string,
  outcome: null as string | null,
  smsId: null as number | null,
  detail: null,
  stage: 0,
  submitError: null,
  actionBusy: false,
  submit: vi.fn(async () => true),
  openExisting: vi.fn(),
  assignCase: vi.fn(),
  retry: vi.fn(),
  resume: vi.fn(),
  abortAndRemove: vi.fn(),
  refresh: vi.fn(async () => {}),
  reset: vi.fn(),
}))

vi.mock('./court-sms/use-court-sms', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./court-sms/use-court-sms')>()
  return { ...actual, useCourtSms: () => flowMock }
})
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }))
vi.mock('./court-sms/CourtSmsFlowDialog', () => ({
  CourtSmsFlowDialog: ({ open }: { open: boolean }) => (open ? <div>流程弹窗</div> : null),
}))
vi.mock('./court-sms/CourtSmsHistoryDialog', () => ({
  CourtSmsHistoryDialog: ({ open, onPick }: { open: boolean; onPick: (id: number) => void }) =>
    open ? (
      <div>
        历史弹窗<button type="button" onClick={() => onPick(42)}>选一条</button>
      </div>
    ) : null,
}))

import { toast } from 'sonner'

import { CourtSmsCard } from './CourtSmsCard'

function wrap(children: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

function typeSms(v: string) {
  const ta = screen.getByPlaceholderText(/粘贴短信全文/) as HTMLTextAreaElement
  fireEvent.change(ta, { target: { value: v } })
  return ta
}

function clickSubmit() {
  const btn = Array.from(document.querySelectorAll('button')).find((b) =>
    /提交短信|处理中/.test(b.textContent ?? ''),
  ) as HTMLButtonElement
  fireEvent.click(btn)
  return btn
}

beforeEach(() => {
  vi.clearAllMocks()
  flowMock.phase = 'idle'
  flowMock.outcome = null
  flowMock.smsId = null
  flowMock.submit = vi.fn(async () => true)
})

describe('CourtSmsCard：提交', () => {
  it('空短信提示且不提交', () => {
    const { unmount } = render(wrap(<CourtSmsCard />))
    clickSubmit()
    expect(toast.info).toHaveBeenCalledWith('先粘贴一条法院短信')
    expect(flowMock.submit).not.toHaveBeenCalled()
    unmount()
  })

  it('纯空白也不提交', () => {
    const { unmount } = render(wrap(<CourtSmsCard />))
    typeSms('   ')
    clickSubmit()
    expect(flowMock.submit).not.toHaveBeenCalled()
    unmount()
  })

  it('提交成功后清空输入并打开流程弹窗', async () => {
    flowMock.submit = vi.fn(async () => true)
    const { unmount } = render(wrap(<CourtSmsCard />))
    const ta = typeSms('某某法院：开庭通知')

    clickSubmit()
    await waitFor(() => expect(flowMock.submit).toHaveBeenCalledWith('某某法院：开庭通知'))
    await waitFor(() => expect(screen.getByText('流程弹窗')).toBeTruthy())
    expect(ta.value).toBe('')
    unmount()
  })

  it('提交失败不清空输入、不开弹窗', async () => {
    flowMock.submit = vi.fn(async () => false)
    const { unmount } = render(wrap(<CourtSmsCard />))
    const ta = typeSms('短信内容')

    clickSubmit()
    await waitFor(() => expect(flowMock.submit).toHaveBeenCalled())
    await new Promise((r) => setTimeout(r, 30))
    expect(ta.value).toBe('短信内容')
    expect(screen.queryByText('流程弹窗')).toBeNull()
    unmount()
  })
})

describe('CourtSmsCard：处理中', () => {
  it('processing 时提交按钮禁用并显示「处理中」', () => {
    flowMock.phase = 'processing'
    const { unmount } = render(wrap(<CourtSmsCard />))
    const btn = clickSubmit()
    expect(btn.disabled).toBe(true)
    expect(btn.textContent).toContain('处理中')
    unmount()
  })

  it('processing 时显示「处理中 · 查看」重开入口', () => {
    flowMock.phase = 'processing'
    const { unmount } = render(wrap(<CourtSmsCard />))
    expect(screen.getByText('处理中 · 查看')).toBeTruthy()
    unmount()
  })

  it('timeout 时显示「后台运行 · 查看」', () => {
    flowMock.phase = 'timeout'
    const { unmount } = render(wrap(<CourtSmsCard />))
    expect(screen.getByText('后台运行 · 查看')).toBeTruthy()
    unmount()
  })

  it('completed 终态显示「已完成 · 查看」', () => {
    flowMock.phase = 'done'
    flowMock.outcome = 'completed'
    const { unmount } = render(wrap(<CourtSmsCard />))
    expect(screen.getByText('已完成 · 查看')).toBeTruthy()
    unmount()
  })

  it('manual 终态显示「待分配案件 · 查看」', () => {
    flowMock.phase = 'done'
    flowMock.outcome = 'manual'
    const { unmount } = render(wrap(<CourtSmsCard />))
    expect(screen.getByText('待分配案件 · 查看')).toBeTruthy()
    unmount()
  })

  it('failed 终态显示「处理失败 · 查看」', () => {
    flowMock.phase = 'done'
    flowMock.outcome = 'failed'
    const { unmount } = render(wrap(<CourtSmsCard />))
    expect(screen.getByText('处理失败 · 查看')).toBeTruthy()
    unmount()
  })

  it('idle 时不显示重开入口，显示提交提示', () => {
    const { unmount } = render(wrap(<CourtSmsCard />))
    expect(screen.queryByText(/· 查看/)).toBeNull()
    expect(screen.getByText(/提交后弹窗跟进全流程/)).toBeTruthy()
    unmount()
  })
})

describe('CourtSmsCard：历史与重开', () => {
  it('点历史打开历史弹窗', () => {
    const { unmount } = render(wrap(<CourtSmsCard />))
    const btn = Array.from(document.querySelectorAll('button')).find((b) => b.textContent === '历史') as HTMLElement
    fireEvent.click(btn)
    expect(screen.getByText('历史弹窗')).toBeTruthy()
    unmount()
  })

  it('从历史选一条会跟进该记录并打开流程弹窗', async () => {
    const { unmount } = render(wrap(<CourtSmsCard />))
    const histBtn = Array.from(document.querySelectorAll('button')).find((b) => b.textContent === '历史') as HTMLElement
    fireEvent.click(histBtn)
    fireEvent.click(screen.getByText('选一条'))

    expect(flowMock.openExisting).toHaveBeenCalledWith(42)
    await waitFor(() => expect(screen.getByText('流程弹窗')).toBeTruthy())
    unmount()
  })

  it('终态下点重开入口会先 refresh 再打开弹窗', async () => {
    flowMock.phase = 'done'
    flowMock.outcome = 'completed'
    const { unmount } = render(wrap(<CourtSmsCard />))

    fireEvent.click(screen.getByText('已完成 · 查看'))
    await waitFor(() => expect(flowMock.refresh).toHaveBeenCalled())
    expect(screen.getByText('流程弹窗')).toBeTruthy()
    unmount()
  })
})
