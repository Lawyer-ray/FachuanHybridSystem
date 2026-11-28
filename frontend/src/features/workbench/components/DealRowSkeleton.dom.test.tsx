// @vitest-environment jsdom
/**
 * DealRowSkeleton（项目列表骨架行）单测（jsdom）。
 *
 * 骨架屏的全部价值是「数据到位时不跳」，所以这里钉的不是像素（jsdom 没有布局
 * 引擎），而是**同源**：骨架行与真行必须用同一个容器常量 `DEAL_ROW_SHELL`。
 * 谁哪天把真行的 padding 从 px-4 py-3 改了却没动常量、或者骨架自己另写一套
 * 类名，这两条用例就会红。
 */
import { render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { DealRow, DEAL_ROW_SHELL } from './DealRow'
import { DealRowSkeleton } from './DealRowSkeleton'
import type { WorkbenchDeal } from '../types'

function deal(): WorkbenchDeal {
  return {
    id: 1,
    client: '张三诉李四买卖合同纠纷',
    ctype: '民商事',
    lit: true,
    parties: { client: '张三', other: '李四' },
    no: '（20XX）京01民初1号',
    amount: '¥100,000',
    daysLeft: 3,
  } as unknown as WorkbenchDeal
}

describe('DealRowSkeleton', () => {
  it('按 count 渲染占位行，每行都用真行同一份容器常量', () => {
    const { container } = render(<DealRowSkeleton count={8} />)
    const rows = Array.from(container.querySelectorAll('[data-skeleton-row="deal"]'))
    expect(rows).toHaveLength(8)
    for (const row of rows) {
      // 全等而不是包含：骨架多加/少加一个结构类都算漂移
      expect(row.className).toBe(DEAL_ROW_SHELL)
    }
  })

  it('真行的容器也是这一份常量（骨架与真行不会各改各的）', () => {
    const { container } = render(
      <DealRow deal={deal()} onOpenSheet={vi.fn()} onOpenDetail={vi.fn()} />,
    )
    const row = container.querySelector('[data-deal-id]') as HTMLElement
    expect(row.className).toContain(DEAL_ROW_SHELL)
    // 交互类只在真行上，骨架不该带（骨架不可点）
    expect(row.className).toContain('cursor-pointer')
    expect(row.className).toContain('hover:bg-secondary')
  })

  it('卡片外框照抄真列表：mt-2.5 + 圆角描边卡（数据到位时框不跳）', () => {
    const { container } = render(<DealRowSkeleton count={1} />)
    const section = container.firstElementChild as HTMLElement
    expect(section.tagName).toBe('SECTION')
    expect(section.className).toContain('mt-2.5')
    const card = section.firstElementChild as HTMLElement
    expect(card.className).toContain('rounded-[14px]')
    expect(card.className).toContain('border-border')
    expect(card.className).toContain('bg-card')
  })

  it('占位块全是装饰：整块没有任何可读文本', () => {
    const { container } = render(<DealRowSkeleton count={2} />)
    expect(container.textContent).toBe('')
    const blocks = container.querySelectorAll('[data-slot="skeleton"]')
    // 每行 7 块：状态点 / 标题 / 类型标签 / 副行 / 金额 / 到期 / 两个按钮 = 8
    expect(blocks).toHaveLength(2 * 8)
    for (const block of blocks) {
      expect(block.getAttribute('aria-hidden')).toBe('true')
    }
  })
})
