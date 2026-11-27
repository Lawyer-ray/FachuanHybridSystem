// @vitest-environment jsdom
/**
 * ContractFileOverlays：诉讼页与非诉页共用的「AI 审查」出口。
 *
 * 抽出来的理由：两页的文件夹来源、审查参数完全相同。各写一份必然漂移——之前
 * 非诉页接好了 AI 审查而诉讼页根本没接，就是因为代码长在页面里。
 *
 * 「整页编辑器」（`?file=`）已从这里删掉：它读 searchParams 却没有任何地方写入，
 * 属于生产里打不开的死分支；画布本身由 DealDocLayout 的「沉浸编辑」兜住。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const navMock = vi.hoisted(() => ({ navigate: vi.fn() }))

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => navMock.navigate }
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

vi.mock('@/lib/download-ticket', () => ({ withDownloadTicket: async (p: string) => p }))

import { ContractFileOverlays } from './ContractFileOverlays'

beforeEach(() => {
  navMock.navigate.mockReset()
})

function setup(over: Partial<Parameters<typeof ContractFileOverlays>[0]> = {}) {
  const onReviewClose = vi.fn()
  render(
    <ContractFileOverlays
      ownerId={318}
      client="某公司"
      reviewTarget={null}
      onReviewClose={onReviewClose}
      {...over}
    />,
  )
  return { onReviewClose }
}

describe('ContractFileOverlays', () => {
  it('没有 in-flight 审查时不渲染任何东西（不再有 ?file= 那条分支）', () => {
    const { container } = render(
      <ContractFileOverlays ownerId={1} reviewTarget={null} onReviewClose={vi.fn()} />,
    )
    expect(container.textContent).toBe('')
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
})
