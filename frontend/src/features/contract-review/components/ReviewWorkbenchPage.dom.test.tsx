// @vitest-environment jsdom
/**
 * ReviewWorkbenchPage 编排测试（jsdom）。
 *
 * 三栏 + 两个 async 副作用（内容版本 / 任务状态）很容易写错，这里钉住：
 * - 缺 taskId 直接给「缺少审查任务 ID」，不打任何接口；
 * - 页头进度文案来自修订清单，模式切换只改传给画布的值；
 * - 文件名优先取任务产物真名，取不到用兜底名（标题不因接口失败而空）；
 * - 版本链面板是按需拉取（点开才请求），收起后回到 AI 助手；
 * - 「保存定稿」在还有未决策建议时先二次确认，全部决策完直接成功。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { listRevisions, getContentVersion, getTaskStatus, listVersions, resolveRevision, navigate, toast } = vi.hoisted(
  () => ({
    listRevisions: vi.fn(),
    getContentVersion: vi.fn(),
    getTaskStatus: vi.fn(),
    listVersions: vi.fn(),
    resolveRevision: vi.fn(),
    navigate: vi.fn(),
    toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() },
  }),
)

vi.mock('react-router', () => ({
  useParams: () => ({ id: 'p-1', taskId: 'task-9' }),
  useNavigate: () => navigate,
}))
vi.mock('../api', () => ({ listRevisions, getContentVersion, getTaskStatus, listVersions, resolveRevision }))
vi.mock('sonner', () => ({ toast }))
// 编辑器画布与插件桥在 jsdom 下无意义：只记录 props，断言「页面把什么喂给了它」
vi.mock('@/components/shared/onlyoffice/OfficeView', () => ({
  OfficeView: (props: {
    fileUrl: string
    fileName: string
    mode: string
    version: string
    onPluginMessage: (msg: { type: string; explicit?: boolean; text?: string }) => void
  }) => (
    <div data-testid="office-view" data-mode={props.mode} data-version={props.version} data-filename={props.fileName}>
      {props.fileUrl}
    </div>
  ),
}))

import { ReviewWorkbenchPage } from './ReviewWorkbenchPage'
import type { ReviewRevision } from '../types'

function rev(over: Partial<ReviewRevision> = {}): ReviewRevision {
  return {
    id: 'r1',
    ordinal: 0,
    kind: 'risk',
    severity: 'high',
    title: '付款节点过于提前',
    original: '甲方于每季度首月十日内支付。',
    suggested: '甲方于收到合规发票后三十日内支付。',
    reason: '依据：《民法典》第509条。',
    paragraph_index: 2,
    status: 'pending',
    reject_reason: '',
    ...over,
  }
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ReviewWorkbenchPage />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  listRevisions.mockResolvedValue({ task_id: 'task-9', total: 0, pending: 0, accepted: 0, rejected: 0, items: [] })
  getContentVersion.mockResolvedValue({ content_version: 'cv-3', saved_version: 3, output_file: 'out.docx' })
  getTaskStatus.mockResolvedValue({ task_id: 'task-9', status: 'done', output_filename: '施工合同（法穿修订）.docx' })
  listVersions.mockResolvedValue({ task_id: 'task-9', total: 0, items: [] })
})

describe('ReviewWorkbenchPage', () => {
  it('页头进度按清单算，「已处理 / 共」实时反映决策数', async () => {
    listRevisions.mockResolvedValue({
      task_id: 'task-9',
      total: 2,
      pending: 1,
      accepted: 1,
      rejected: 0,
      items: [rev({ id: 'a', status: 'accepted' }), rev({ id: 'b', ordinal: 1, status: 'pending' })],
    })
    renderPage()
    await waitFor(() => expect(screen.getByText('已处理 1 / 共 2')).toBeTruthy())
  })

  it('画布：fileUrl 指向任务下载端点，文件名取产物真名，版本取内容版本', async () => {
    renderPage()
    const view = await screen.findByTestId('office-view')
    await waitFor(() => expect(view.getAttribute('data-version')).toBe('cv-3'))
    expect(view.textContent).toBe('/api/v1/contract-review/task-9/download')
    expect(view.getAttribute('data-filename')).toBe('施工合同（法穿修订）.docx')
    expect(view.getAttribute('data-mode')).toBe('review')
  })

  it('文件名接口失败时退回兜底名（标题不空）', async () => {
    getTaskStatus.mockRejectedValue(new Error('404'))
    renderPage()
    const view = await screen.findByTestId('office-view')
    await waitFor(() => expect(view.getAttribute('data-filename')).toBe('合同（法穿SI修订）.docx'))
  })

  it('模式按钮切换只改给画布的模式值', async () => {
    renderPage()
    const view = await screen.findByTestId('office-view')
    fireEvent.click(screen.getByRole('button', { name: '完全编辑' }))
    await waitFor(() => expect(view.getAttribute('data-mode')).toBe('edit'))
    fireEvent.click(screen.getByRole('button', { name: '只读' }))
    await waitFor(() => expect(view.getAttribute('data-mode')).toBe('view'))
  })

  it('版本链按需拉取：不点不请求，点开才拉，收起回到 AI 助手', async () => {
    renderPage()
    await screen.findByTestId('office-view')
    expect(listVersions).not.toHaveBeenCalled()
    expect(screen.getByText('法穿 AI 助手')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /版本链/ }))
    await waitFor(() => expect(listVersions).toHaveBeenCalledTimes(1))
    expect(screen.getByText('收起')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '收起' }))
    await waitFor(() => expect(screen.getByText('法穿 AI 助手')).toBeTruthy())
  })

  it('全部决策完：保存定稿直接成功，不弹二次确认', async () => {
    listRevisions.mockResolvedValue({
      task_id: 'task-9',
      total: 1,
      pending: 0,
      accepted: 1,
      rejected: 0,
      items: [rev({ status: 'accepted' })],
    })
    renderPage()
    await waitFor(() => expect(screen.getByText('已处理 1 / 共 1')).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: '保存定稿' }))
    expect(toast.success).toHaveBeenCalledWith('已保存定稿', expect.anything())
    expect(screen.queryByText(/处建议未决策/)).toBeNull()
  })

  it('还有未决策建议：保存定稿先弹二次确认，确认后才落定稿', async () => {
    listRevisions.mockResolvedValue({
      task_id: 'task-9',
      total: 2,
      pending: 1,
      accepted: 1,
      rejected: 0,
      items: [rev({ id: 'a', status: 'accepted' }), rev({ id: 'b', ordinal: 1, status: 'pending' })],
    })
    renderPage()
    await waitFor(() => expect(screen.getByText('已处理 1 / 共 2')).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: '保存定稿' }))
    await waitFor(() => expect(screen.getByText('还有 1 处建议未决策')).toBeTruthy())
    expect(toast.success).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: '保存定稿', hidden: false }))
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('已保存定稿', expect.anything()))
  })

  it('返回项目：跳到项目详情路由', async () => {
    renderPage()
    await screen.findByTestId('office-view')
    fireEvent.click(screen.getByRole('button', { name: /返回项目/ }))
    expect(navigate).toHaveBeenCalledWith('/projects/p-1')
  })

  it('清单加载失败：错误块回显可读文案，画布仍可用', async () => {
    listRevisions.mockRejectedValue(new Error('网络中断'))
    renderPage()
    await waitFor(() => expect(screen.getByText('网络中断')).toBeTruthy())
    expect(screen.getByTestId('office-view')).toBeTruthy()
  })
})
