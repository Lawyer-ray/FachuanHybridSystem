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
  source: 'sms' as 'sms' | 'material',
  intake: null,
  submit: vi.fn(async () => true),
  submitFiles: vi.fn(async () => true),
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
  flowMock.source = 'sms'
  flowMock.intake = null
  flowMock.submit = vi.fn(async () => true)
  flowMock.submitFiles = vi.fn(async () => true)
})

/** 切到「客户材料」页签 */
function switchToMaterial() {
  const tab = screen.getByRole('tab', { name: '客户材料' }) as HTMLElement
  fireEvent.click(tab)
}

function dropZone() {
  return screen.getByRole('button', { name: '拖入或点击选择案件材料' }) as HTMLElement
}

function clickSubmitMaterial() {
  const btn = Array.from(document.querySelectorAll('button')).find((b) =>
    /提交材料|处理中/.test(b.textContent ?? ''),
  ) as HTMLButtonElement
  fireEvent.click(btn)
  return btn
}

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

describe('CourtSmsCard：客户材料模式', () => {
  it('默认停在法院短信模式，没有拖放区', () => {
    const { unmount } = render(wrap(<CourtSmsCard />))
    expect(screen.getByPlaceholderText(/粘贴短信全文/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: '拖入或点击选择案件材料' })).toBeNull()
    unmount()
  })

  it('切到客户材料：出现拖放区与备注框，不再显示短信输入框', () => {
    const { unmount } = render(wrap(<CourtSmsCard />))
    switchToMaterial()

    expect(dropZone()).toBeTruthy()
    expect(screen.getByPlaceholderText(/客户微信转来的判决书/)).toBeTruthy()
    expect(screen.queryByPlaceholderText(/粘贴短信全文/)).toBeNull()
    unmount()
  })

  it('没有文件时点提交：提示且不调用 submitFiles', () => {
    const { unmount } = render(wrap(<CourtSmsCard />))
    switchToMaterial()
    clickSubmitMaterial()

    expect(toast.info).toHaveBeenCalledWith('先拖入或选择案件材料')
    expect(flowMock.submitFiles).not.toHaveBeenCalled()
    unmount()
  })

  it('拖入文件后列表可见，提交时把文件交给 submitFiles', async () => {
    const { unmount } = render(wrap(<CourtSmsCard />))
    switchToMaterial()

    const file = new File(['x'], '判决书.pdf', { type: 'application/pdf' })
    fireEvent.drop(dropZone(), { dataTransfer: { files: [file] } })

    expect(screen.getByText('判决书.pdf')).toBeTruthy()
    clickSubmitMaterial()

    await waitFor(() => expect(flowMock.submitFiles).toHaveBeenCalledTimes(1))
    const filesArg = (flowMock.submitFiles.mock.calls[0] as unknown as [File[]])[0]!
    expect(filesArg).toHaveLength(1)
    expect(filesArg[0]?.name).toBe('判决书.pdf')
    unmount()
  })

  it('备注随文件一起提交', async () => {
    const { unmount } = render(wrap(<CourtSmsCard />))
    switchToMaterial()

    fireEvent.drop(dropZone(), { dataTransfer: { files: [new File(['x'], 'a.pdf', { type: 'application/pdf' })] } })
    const note = screen.getByPlaceholderText(/客户微信转来的判决书/) as HTMLInputElement
    fireEvent.change(note, { target: { value: '客户转来' } })
    clickSubmitMaterial()

    await waitFor(() => expect(flowMock.submitFiles).toHaveBeenCalledWith(expect.any(Array), '客户转来'))
    unmount()
  })

  it('提交成功后清空文件列表与备注', async () => {
    const { unmount } = render(wrap(<CourtSmsCard />))
    switchToMaterial()

    fireEvent.drop(dropZone(), { dataTransfer: { files: [new File(['x'], 'a.pdf', { type: 'application/pdf' })] } })
    clickSubmitMaterial()

    await waitFor(() => expect(flowMock.submitFiles).toHaveBeenCalled())
    await waitFor(() => expect(screen.queryByText('a.pdf')).toBeNull())
    unmount()
  })

  it('提交失败保留文件列表（可重试）', async () => {
    flowMock.submitFiles = vi.fn(async () => false)
    const { unmount } = render(wrap(<CourtSmsCard />))
    switchToMaterial()

    fireEvent.drop(dropZone(), { dataTransfer: { files: [new File(['x'], 'b.pdf', { type: 'application/pdf' })] } })
    clickSubmitMaterial()

    await waitFor(() => expect(flowMock.submitFiles).toHaveBeenCalled())
    expect(screen.getByText('b.pdf')).toBeTruthy()
    unmount()
  })

  it('拖到不支持的文件：提示跳过且不入列', () => {
    const { unmount } = render(wrap(<CourtSmsCard />))
    switchToMaterial()

    fireEvent.drop(dropZone(), { dataTransfer: { files: [new File(['x'], '录屏.mov')] } })

    expect(toast.warning).toHaveBeenCalled()
    expect(screen.queryByText('录屏.mov')).toBeNull()
    unmount()
  })

  it('处理中时页签禁用，不能切换来源', () => {
    flowMock.phase = 'processing'
    const { unmount } = render(wrap(<CourtSmsCard />))
    expect((screen.getByRole('tab', { name: '客户材料' }) as HTMLButtonElement).disabled).toBe(true)
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
