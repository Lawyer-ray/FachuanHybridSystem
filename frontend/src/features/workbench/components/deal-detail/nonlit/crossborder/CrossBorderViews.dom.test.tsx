// @vitest-environment jsdom
/**
 * CrossBorderViews：跨境审查「律师拿到什么、怎么用」的六块视图组合。
 *
 * 这一层是**纯编排 + 状态归属**：六张子卡共享「当前选中的修订」与「当前维度」，
 * 由本组件持有（子卡自身由各自的测试覆盖）。所以这里只钉住编排契约：
 * - ReviewProgressCard 的进度百分比按 reviewed/total 取整，并显示检出总数
 * - lawVerified 原样透传给法条卡（核验没跑时法条卡处于未激活态）
 * - 点双语正文 / 法条卡里的修订 → picked 传到修订单（跨卡联动）
 * - 切维度 tab 由本组件持有，切完清单跟着换
 * - 逐条采纳的决定也在本组件持有，重置后清空
 *
 * 六张子卡全部 stub：本文件测的是接线，不是子卡的呈现。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const stubs = vi.hoisted(() => ({
  lawGate: vi.fn(),
  bilingual: vi.fn(),
  board: vi.fn(),
  walk: vi.fn(),
  office: vi.fn(),
}))

vi.mock('./LawGateCard', () => ({
  LawGateCard: (props: { active: boolean; onPickRev: (id: string) => void }) => {
    stubs.lawGate(props)
    return (
      <button type="button" onClick={() => props.onPickRev('r_law')}>
        LAW_GATE:{String(props.active)}
      </button>
    )
  },
}))
vi.mock('./BilingualContractCard', () => ({
  BilingualContractCard: (props: { focusRev: string | null; onPickRev: (id: string) => void }) => {
    stubs.bilingual(props)
    return (
      <button type="button" onClick={() => props.onPickRev('r_bilingual')}>
        BILINGUAL:{String(props.focusRev)}
      </button>
    )
  },
}))
vi.mock('./RevisionBoard', () => ({
  RevisionBoard: (props: { tabId: string; picked: string | null; onPickTab: (id: string) => void }) => {
    stubs.board(props)
    return (
      <button type="button" onClick={() => props.onPickTab('high')}>
        BOARD:{props.tabId}/{String(props.picked)}
      </button>
    )
  },
}))
vi.mock('./RevisionWalkCard', () => ({
  RevisionWalkCard: (props: {
    decided: Record<string, 'accept' | 'reject'>
    onDecide: (id: string, verdict: 'accept' | 'reject') => void
    onReset: () => void
    onPickRev: (id: string) => void
  }) => {
    stubs.walk(props)
    return (
      <>
        <button type="button" onClick={() => props.onDecide('r_walk', 'accept')}>
          WALK_DECIDE
        </button>
        <button type="button" onClick={() => props.onReset()}>
          WALK_RESET
        </button>
        <span>DECIDED:{JSON.stringify(props.decided)}</span>
      </>
    )
  },
}))
vi.mock('./ContractOfficeCard', () => ({
  ContractOfficeCard: () => {
    stubs.office()
    return <div>OFFICE_CARD</div>
  },
}))

import { DEMO_NL2_REVIEW_PROGRESS, DEMO_TH_CONTRACT_REVISIONS } from '../../demo-nonlit'
import { CrossBorderViews, ReviewProgressCard } from './CrossBorderViews'

beforeEach(() => {
  vi.clearAllMocks()
})

describe('ReviewProgressCard', () => {
  it('进度百分比按 reviewed / total 取整', () => {
    const { container } = render(<ReviewProgressCard />)
    const expected = Math.round((DEMO_NL2_REVIEW_PROGRESS.reviewed / DEMO_NL2_REVIEW_PROGRESS.total) * 100)
    expect(screen.getByText(`进度 ${expected}%`)).toBeTruthy()
    const bar = container.querySelector('[style*="width"]') as HTMLElement
    expect(bar.style.width).toBe(`${expected}%`)
  })

  it('已审 / 还剩 / 用时 / 审查人逐项照实显示', () => {
    const p = DEMO_NL2_REVIEW_PROGRESS
    render(<ReviewProgressCard />)
    expect(
      screen.getByText(`已审 ${p.reviewed} / ${p.total} 条 · 还剩 ${p.remain} 条 · 用时 ${p.elapsed}（预计再 ${p.eta}）`),
    ).toBeTruthy()
    expect(screen.getByText(`审查人 ${p.reviewer}`)).toBeTruthy()
    expect(screen.getByText(`最近落笔：${p.lastClause}`)).toBeTruthy()
    expect(screen.getByText(`检出修订 ${DEMO_TH_CONTRACT_REVISIONS.length} 处`)).toBeTruthy()
  })
})

describe('CrossBorderViews · 编排', () => {
  it('六块视图都在，lawVerified 透传给法条卡', () => {
    render(<CrossBorderViews lawVerified />)
    expect(screen.getByText('审查进度')).toBeTruthy()
    expect(screen.getByText('OFFICE_CARD')).toBeTruthy()
    expect(screen.getByText('LAW_GATE:true')).toBeTruthy()
    expect(screen.getByText('BILINGUAL:null')).toBeTruthy()
    expect(screen.getByText('BOARD:all/null')).toBeTruthy()
    expect(screen.getByText('WALK_DECIDE')).toBeTruthy()
  })

  it('核验没跑过时法条卡拿到 active=false', () => {
    render(<CrossBorderViews lawVerified={false} />)
    expect(screen.getByText('LAW_GATE:false')).toBeTruthy()
  })

  it('点双语正文里的修订 → 选中态同时传给修订单与正文卡（跨卡联动）', () => {
    render(<CrossBorderViews lawVerified />)
    fireEvent.click(screen.getByText('BILINGUAL:null'))
    expect(screen.getByText('BILINGUAL:r_bilingual')).toBeTruthy()
    expect(screen.getByText('BOARD:all/r_bilingual')).toBeTruthy()
  })

  it('点法条卡里的修订也会更新同一个选中态', () => {
    render(<CrossBorderViews lawVerified />)
    fireEvent.click(screen.getByText('LAW_GATE:true'))
    expect(screen.getByText('BOARD:all/r_law')).toBeTruthy()
    expect(screen.getByText('BILINGUAL:r_law')).toBeTruthy()
  })

  it('切维度 tab 由本组件持有，修订单收到新 tabId 且选中态不变', () => {
    render(<CrossBorderViews lawVerified />)
    fireEvent.click(screen.getByText('LAW_GATE:true'))
    fireEvent.click(screen.getByText('BOARD:all/r_law'))
    expect(screen.getByText('BOARD:high/r_law')).toBeTruthy()
  })

  it('逐条采纳的决定存在本组件；重置后清空', () => {
    render(<CrossBorderViews lawVerified />)
    expect(screen.getByText('DECIDED:{}')).toBeTruthy()

    fireEvent.click(screen.getByText('WALK_DECIDE'))
    expect(screen.getByText('DECIDED:{"r_walk":"accept"}')).toBeTruthy()

    fireEvent.click(screen.getByText('WALK_RESET'))
    expect(screen.getByText('DECIDED:{}')).toBeTruthy()
  })
})
