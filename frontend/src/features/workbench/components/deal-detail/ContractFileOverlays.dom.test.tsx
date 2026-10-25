// @vitest-environment jsdom
/**
 * ContractFileOverlays：诉讼页与非诉页共用的「AI 审查 / 整页编辑」出口。
 *
 * 抽出来的理由：两页的文件夹来源、审查参数、整页编辑器完全相同。各写一份必然
 * 漂移——之前非诉页接好了 AI 审查而诉讼页根本没接，就是因为代码长在页面里。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const navMock = vi.hoisted(() => ({ navigate: vi.fn() }))
const paramsMock = vi.hoisted(() => ({ current: new URLSearchParams() }))

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return {
    ...actual,
    useNavigate: () => navMock.navigate,
    useSearchParams: () => [paramsMock.current, vi.fn()] as const,
  }
})

vi.mock('@/features/contract-review', () => ({
  ReviewLaunchDrawer: (p: { fileName: string; onStarted: (t: string) => void; open: boolean }) =>
    p.open ? (
      <div data-testid="review-drawer">
        {p.fileName}
        <button type="button" onClick={() => p.onStarted('task-9')}>
          start
        </button>
      </div>
    ) : null,
}))

vi.mock('./FilePreview', () => ({
  FilePreview: (p: { file: { name: string }; onBack: () => void; onReview: (f: unknown) => void }) => (
    <div data-testid="full-editor">
      EDITOR:{p.file.name}
      <button type="button" onClick={p.onBack}>
        back
      </button>
      <button type="button" onClick={() => p.onReview({ subpath: 'a/b.docx', name: 'b.docx' })}>
        to-review
      </button>
    </div>
  ),
}))

vi.mock('@/lib/download-ticket', () => ({ withDownloadTicket: async (p: string) => p }))

import { ContractFileOverlays } from './ContractFileOverlays'

beforeEach(() => {
  navMock.navigate.mockReset()
  paramsMock.current = new URLSearchParams()
})

function setup(over: Partial<Parameters<typeof ContractFileOverlays>[0]> = {}) {
  const onReviewClose = vi.fn()
  const onReviewStart = vi.fn()
  render(
    <ContractFileOverlays
      ownerId={318}
      client="某公司"
      other="对方公司"
      reviewTarget={null}
      onReviewClose={onReviewClose}
      onReviewStart={onReviewStart}
      {...over}
    />,
  )
  return { onReviewClose, onReviewStart }
}

describe('ContractFileOverlays', () => {
  it('无 ?file= 且无 reviewTarget 时不渲染任何东西', () => {
    const { container } = render(
      <ContractFileOverlays
        ownerId={1}
        reviewTarget={null}
        onReviewClose={vi.fn()}
        onReviewStart={vi.fn()}
      />,
    )
    expect(container.textContent).toBe('')
  })

  it('?file= 存在时整页显示编辑器', () => {
    paramsMock.current = new URLSearchParams({ file: '1-合同/顾问合同.docx' })
    setup()
    expect(screen.getByTestId('full-editor').textContent).toContain('顾问合同.docx')
  })

  it('reviewTarget 存在时显示审查抽屉', () => {
    setup({ reviewTarget: { subpath: 'a.docx', name: 'a.docx' } })
    expect(screen.getByTestId('review-drawer').textContent).toContain('a.docx')
  })

  it('审查启动后跳复审台（诉讼页与非诉页同一条路由）', async () => {
    const { onReviewClose } = setup({ reviewTarget: { subpath: 'a.docx', name: 'a.docx' } })
    fireEvent.click(screen.getByText('start'))
    await waitFor(() => expect(navMock.navigate).toHaveBeenCalledWith('/projects/318/review/task-9'))
    expect(onReviewClose).toHaveBeenCalled()
  })

  it('编辑器里点 AI 审查：先关编辑器，再把文件交回页面', () => {
    paramsMock.current = new URLSearchParams({ file: '1-合同/顾问合同.docx' })
    const { onReviewStart } = setup()
    fireEvent.click(screen.getByText('to-review'))
    expect(onReviewStart).toHaveBeenCalledWith({ subpath: 'a/b.docx', name: 'b.docx' })
  })
})
