// @vitest-environment jsdom
/**
 * ProjectDetailPage 分流测试。
 *
 * 这一层存在的理由：`nonlit` 是 non-litigation 的缩写，属实现分类而不是用户
 * 概念。旧实现把非诉挂在 `/projects/:id/nonlit`，还在 DealDetailPage 里把直达
 * `/projects/:id` 的非诉委托悄悄重定向过去——用户在地址栏看到 URL 自己变了。
 *
 * 现在一条 URL，按 `deal.lit` 决定左栏：有法院程序 → 案件程序链；无 → 合同文件夹。
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

const hookMock = vi.hoisted(() => ({ deal: { lit: true } as { lit: boolean } | null }))

vi.mock('./use-deal-detail-page', () => ({
  useDealDetailPage: () => ({ deal: hookMock.deal }),
}))
vi.mock('./DealDetailPage', () => ({ DealDetailPage: () => <div>LIT_PAGE</div> }))
vi.mock('./NonLitDetailPage', () => ({ NonLitDetailPage: () => <div>NONLIT_PAGE</div> }))
vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router")>()
  return { ...actual, useParams: () => ({ id: '318' }) }
})

import { ProjectDetailPage } from './ProjectDetailPage'

describe('ProjectDetailPage 分流', () => {
  it('有法院程序（lit=true）→ 诉讼详情页', () => {
    hookMock.deal = { lit: true }
    render(<ProjectDetailPage />)
    expect(screen.getByText('LIT_PAGE')).toBeTruthy()
    expect(screen.queryByText('NONLIT_PAGE')).toBeNull()
  })

  it('非诉（lit=false）→ 非诉详情页', () => {
    hookMock.deal = { lit: false }
    render(<ProjectDetailPage />)
    expect(screen.getByText('NONLIT_PAGE')).toBeTruthy()
    expect(screen.queryByText('LIT_PAGE')).toBeNull()
  })

  it('数据未就绪时不崩（按非诉兜底，等真实 lit 到位再切）', () => {
    hookMock.deal = null
    expect(() => render(<ProjectDetailPage />)).not.toThrow()
  })
})
