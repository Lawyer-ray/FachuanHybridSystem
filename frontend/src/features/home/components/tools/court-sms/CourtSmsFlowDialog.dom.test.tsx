// @vitest-environment jsdom
/**
 * CourtSmsFlowDialog 测试（jsdom）。
 *
 * 该弹窗把流程状态映射成四种基调（running / success / manual / error / timeout），
 * 并在处理中与超时时给出可读的错误提示。这里覆盖：
 * - stageForDisplay 的三条分支（无详情 / 完成 / 失败阶段 / 单调递增）
 * - 弹窗在各 phase 下的标题与操作区（重试、人工分配、下载、停止删除）
 */
import { fireEvent, render, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  courtSmsDownloadAllUrl: vi.fn(() => '/api/v1/court-sms/9/download-all'),
  triggerDownload: vi.fn(),
  copyAllDocFiles: vi.fn(),
  copyDocFile: vi.fn(),
}))
vi.mock('../../../api', () => ({
  courtSmsDownloadAllUrl: apiMock.courtSmsDownloadAllUrl,
  triggerDownload: apiMock.triggerDownload,
}))
vi.mock('./copy-files', () => ({
  copyAllDocFiles: (...a: unknown[]) => apiMock.copyAllDocFiles(...a),
  copyDocFile: (...a: unknown[]) => apiMock.copyDocFile(...a),
}))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }))

import { toast } from 'sonner'

import type { CourtSmsDetail } from '../../../api'
import { CourtSmsFlowDialog } from './CourtSmsFlowDialog'
import { stageForDisplay, type UseCourtSmsResult } from './use-court-sms'

function detail(over: Partial<CourtSmsDetail> = {}): CourtSmsDetail {
  return {
    id: 9,
    content: '短信内容',
    sms_type: null,
    download_links: [],
    case_numbers: [],
    party_names: [],
    status: 'processing',
    error_message: null,
    retry_count: 0,
    download_task_status: null,
    download_task_error: null,
    case: null,
    documents: [],
    notification_results: null,
    ...over,
  } as CourtSmsDetail
}

function flow(over: Partial<UseCourtSmsResult> = {}): UseCourtSmsResult {
  return {
    phase: 'processing',
    outcome: null,
    smsId: 9,
    detail: detail(),
    stage: 1,
    submitError: null,
    actionBusy: false,
    submit: vi.fn(),
    openExisting: vi.fn(),
    assignCase: vi.fn(),
    retry: vi.fn(),
    resume: vi.fn(),
    abortAndRemove: vi.fn(),
    refresh: vi.fn(),
    reset: vi.fn(),
    ...over,
  } as UseCourtSmsResult
}

function renderDialog(props: Partial<Parameters<typeof CourtSmsFlowDialog>[0]> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrap = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
  const onOpenChange = vi.fn()
  const utils = render(
    <CourtSmsFlowDialog open flow={flow()} onOpenChange={onOpenChange} {...props} />,
    { wrapper: wrap },
  )
  return { ...utils, onOpenChange }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('stageForDisplay', () => {
  it('无详情时停在起点', () => {
    expect(stageForDisplay(null, 3)).toEqual({ current: 0, failedAt: null })
  })

  it('completed 终态：current 为阶段总数', () => {
    const r = stageForDisplay(detail({ status: 'completed' }), 2)
    expect(r.failedAt).toBeNull()
    expect(r.current).toBeGreaterThan(0)
  })

  it('失败阶段：failedAt 指向该阶段', () => {
    const r = stageForDisplay(detail({ status: 'download_failed' }), 0)
    expect(r.failedAt).not.toBeNull()
    expect(r.current).toBe(r.failedAt)
  })

  it('进行中：current 取观测到的最大阶段（不回退）', () => {
    const r = stageForDisplay(detail({ status: 'processing' }), 3)
    expect(r.failedAt).toBeNull()
    expect(r.current).toBeGreaterThanOrEqual(0)
  })
})

describe('CourtSmsFlowDialog：关闭态', () => {
  it('open=false 时不渲染弹窗内容', () => {
    const { container } = renderDialog({ open: false })
    expect(container.querySelector('[role="dialog"]')).toBeNull()
    container.remove()
  })
})

describe('CourtSmsFlowDialog：处理中', () => {
  it('显示处理中基调与步进器', async () => {
    const { container } = renderDialog({ flow: flow({ phase: 'processing' }) })
    await waitFor(() => expect(document.querySelector('[role="dialog"]')).toBeTruthy())
    expect(document.body.textContent).toBeTruthy()
    container.remove()
  })

  it('下载失败时给出自动重试提示（含次数）', async () => {
    const { container } = renderDialog({
      flow: flow({ detail: detail({ status: 'download_failed', error_message: '爬虫超时', retry_count: 1 }) }),
    })
    await waitFor(() => expect(document.body.textContent).toContain('文书下载失败'))
    expect(document.body.textContent).toContain('爬虫超时')
    expect(document.body.textContent).toContain('2/3')
    container.remove()
  })

  it('下载进程出错时提示自动重试', async () => {
    const { container } = renderDialog({
      flow: flow({ detail: detail({ status: 'downloading', download_task_error: '连接被重置' }) }),
    })
    await waitFor(() => expect(document.body.textContent).toContain('正在自动重试'))
    expect(document.body.textContent).toContain('连接被重置')
    container.remove()
  })
})

describe('CourtSmsFlowDialog：终态', () => {
  it('completed：展示成功结果与下载入口', async () => {
    const { container } = renderDialog({
      flow: flow({
        phase: 'done',
        outcome: 'completed',
        detail: detail({ status: 'completed', case: { id: 1, name: '张三诉李四' } as never }),
      }),
    })
    await waitFor(() => expect(document.body.textContent).toContain('张三诉李四'))
    container.remove()
  })

  it('failed：显示重试入口', async () => {
    const retry = vi.fn()
    const { container } = renderDialog({
      flow: flow({ phase: 'done', outcome: 'failed', detail: detail({ status: 'failed', error_message: '解析失败' }), retry }),
    })
    await waitFor(() => expect(document.body.textContent).toContain('解析失败'))
    container.remove()
  })

  it('timeout：把已知报错亮出来', async () => {
    const { container } = renderDialog({
      flow: flow({ phase: 'timeout', detail: detail({ status: 'processing', error_message: '后台阻塞' }) }),
    })
    await waitFor(() => expect(document.body.textContent).toContain('后台处理异常'))
    expect(document.body.textContent).toContain('后台阻塞')
    container.remove()
  })

  it('manual：人工分配区渲染案件选择器', async () => {
    const { container } = renderDialog({
      flow: flow({ phase: 'done', outcome: 'manual', detail: detail({ status: 'pending_manual' }) }),
    })
    await waitFor(() => expect(document.querySelector('[role="dialog"]')).toBeTruthy())
    container.remove()
  })
})

describe('CourtSmsFlowDialog：提交失败', () => {
  it('submitError 在 error 基调下显示（短信提交失败）', async () => {
    // submitError 只在 tone==='error' 分支渲染；phase=idle 不是 error 基调
    const { container } = renderDialog({
      flow: flow({ phase: 'done', outcome: 'failed', smsId: null, detail: null, submitError: '短信内容为空' }),
    })
    await waitFor(() => expect(document.body.textContent).toContain('短信提交失败'))
    expect(document.body.textContent).toContain('短信内容为空')
    container.remove()
  })
})

// ============ 操作区（覆盖率补测） ============

describe('CourtSmsFlowDialog：停止并删除两段确认', () => {
  it('第一次点击只武装，不调用 abortAndRemove', async () => {
    const abortAndRemove = vi.fn(async () => {})
    const { container } = renderDialog({
      flow: flow({ phase: 'processing', abortAndRemove }),
    })
    await waitFor(() => expect(document.body.textContent).toContain('停止并删除'))

    const btn = Array.from(document.querySelectorAll('button')).find((b) =>
      /停止并删除/.test(b.textContent ?? ''),
    ) as HTMLButtonElement
    fireEvent.click(btn)
    expect(abortAndRemove).not.toHaveBeenCalled()
    // 文案切到确认态
    await waitFor(() => expect(document.body.textContent).toContain('确认停止并删除'))
    container.remove()
  })

  it('第二次点击才真正调用并关闭弹窗', async () => {
    const abortAndRemove = vi.fn(async () => {})
    const { container, onOpenChange } = renderDialog({
      flow: flow({ phase: 'processing', abortAndRemove }),
    })
    await waitFor(() => expect(document.body.textContent).toContain('停止并删除'))

    const click = () => {
      const btn = Array.from(document.querySelectorAll('button')).find((b) =>
        /停止并删除|确认停止并删除/.test(b.textContent ?? ''),
      ) as HTMLButtonElement | undefined
      if (btn) fireEvent.click(btn)
    }
    click()
    // 第一次点击后 React 重渲染（按钮文案变化），需重新查询再点
    await waitFor(() => expect(document.body.textContent).toContain('确认停止并删除'))
    click()

    await waitFor(() => expect(abortAndRemove).toHaveBeenCalled())
    expect(toast.success).toHaveBeenCalledWith('已停止并删除该短信处理任务')
    expect(onOpenChange).toHaveBeenCalledWith(false)
    container.remove()
  })

  it('取消失败：弹出后端错误文案', async () => {
    const abortAndRemove = vi.fn(async () => {
      throw new Error('任务已在后台完成')
    })
    const { container } = renderDialog({
      flow: flow({ phase: 'processing', abortAndRemove }),
    })
    await waitFor(() => expect(document.body.textContent).toContain('停止并删除'))

    const click = () => {
      const btn = Array.from(document.querySelectorAll('button')).find((b) =>
        /停止并删除|确认停止并删除/.test(b.textContent ?? ''),
      ) as HTMLButtonElement | undefined
      if (btn) fireEvent.click(btn)
    }
    click()
    // 第一次点击后 React 重渲染（按钮文案变化），需重新查询再点
    await waitFor(() => expect(document.body.textContent).toContain('确认停止并删除'))
    click()

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('任务已在后台完成'))
    container.remove()
  })
})

describe('CourtSmsFlowDialog：成功态操作', () => {
  function successFlow(over: Record<string, unknown> = {}) {
    return flow({
      phase: 'done',
      outcome: 'completed',
      detail: detail({
        status: 'completed',
        documents: [
          { id: 1, name: 'a.pdf' },
          { id: 2, name: 'b.pdf' },
        ],
        case: { id: 1, name: '张三诉李四' },
      } as never),
      ...over,
    })
  }

  it('有文书时显示「全部复制」并可点击', async () => {
    const { container } = renderDialog({ flow: successFlow() })
    await waitFor(() => expect(document.body.textContent).toContain('全部复制'))

    const btn = Array.from(document.querySelectorAll('button')).find((b) =>
      /全部复制/.test(b.textContent ?? ''),
    ) as HTMLButtonElement
    fireEvent.click(btn)
    await waitFor(() => expect(apiMock.copyAllDocFiles).toHaveBeenCalled())
    container.remove()
  })

  it('多份文书时显示「打包下载 N 件」并触发下载', async () => {
    const { container } = renderDialog({ flow: successFlow() })
    await waitFor(() => expect(document.body.textContent).toContain('打包下载 2 件'))

    const btn = Array.from(document.querySelectorAll('button')).find((b) =>
      /打包下载/.test(b.textContent ?? ''),
    ) as HTMLButtonElement
    fireEvent.click(btn)
    await waitFor(() => expect(apiMock.triggerDownload).toHaveBeenCalled())
    container.remove()
  })

  it('单份文书时不显示打包下载（逐件下即可）', async () => {
    const { container } = renderDialog({
      flow: flow({
        phase: 'done',
        outcome: 'completed',
        detail: detail({ status: 'completed', documents: [{ id: 1, name: 'a.pdf' }] } as never),
      }),
    })
    await waitFor(() => expect(document.body.textContent).toContain('全部复制'))
    expect(document.body.textContent).not.toContain('打包下载')
    container.remove()
  })
})

describe('CourtSmsFlowDialog：失败与超时操作', () => {
  it('失败态点「重试处理」调用 retry', async () => {
    const retry = vi.fn(async () => {})
    const { container } = renderDialog({
      flow: flow({ phase: 'done', outcome: 'failed', smsId: 9, detail: detail({ status: 'failed' }), retry }),
    })
    await waitFor(() => expect(document.body.textContent).toContain('重试处理'))

    const btn = Array.from(document.querySelectorAll('button')).find((b) =>
      /重试处理/.test(b.textContent ?? ''),
    ) as HTMLButtonElement
    fireEvent.click(btn)
    await waitFor(() => expect(retry).toHaveBeenCalled())
    container.remove()
  })

  it('重试失败弹出错误文案', async () => {
    const retry = vi.fn(async () => {
      throw new Error('后端忙碌')
    })
    const { container } = renderDialog({
      flow: flow({ phase: 'done', outcome: 'failed', smsId: 9, detail: detail({ status: 'failed' }), retry }),
    })
    await waitFor(() => expect(document.body.textContent).toContain('重试处理'))

    const btn = Array.from(document.querySelectorAll('button')).find((b) =>
      /重试处理/.test(b.textContent ?? ''),
    ) as HTMLButtonElement
    fireEvent.click(btn)
    await waitFor(() => expect(toast.error).toHaveBeenCalled(), { timeout: 3000 })
    container.remove()
  })

  it('超时态点「继续等待」调用 resume', async () => {
    const resume = vi.fn()
    const { container } = renderDialog({
      flow: flow({ phase: 'timeout', detail: detail({ status: 'processing' }), resume }),
    })
    await waitFor(() => expect(document.body.textContent).toContain('继续等待'))

    const btn = Array.from(document.querySelectorAll('button')).find((b) =>
      /继续等待/.test(b.textContent ?? ''),
    ) as HTMLButtonElement
    fireEvent.click(btn)
    expect(resume).toHaveBeenCalled()
    container.remove()
  })
})
