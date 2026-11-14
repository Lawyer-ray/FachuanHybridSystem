// @vitest-environment jsdom
/**
 * 跨页不一致清单（抽屉）单测。
 *
 * 真实痛点：同一枚章被识别 150+ 次，其中 5 次错成「罗问文」（应为「罗向文」）。
 * 律师逐页翻不可能发现，所以这份清单必须做到三件事：
 *  1. 少的那个写法被点名为「疑似错字」，多的那个是基准；
 *  2. high 排最前（最该看的永远在最上面）；
 *  3. 点页号能回到那一页——只能看不能跳的清单等于让人自己再去找。
 *
 * 另外：旧任务没有这项统计，空白态必须是一句解释，而不是空白抽屉。
 */
import { fireEvent, render, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Inconsistency } from '../../types'
import { InconsistencyDrawer } from './InconsistencyDrawer'

function item(over: Partial<Inconsistency> = {}): Inconsistency {
  return {
    canonical: '罗向文',
    variant: '罗问文',
    canonical_count: 178,
    variant_count: 5,
    pages: [12, 45],
    confidence: 'high',
    ...over,
  }
}

function renderDrawer(items: Inconsistency[], over: Partial<Parameters<typeof InconsistencyDrawer>[0]> = {}) {
  return render(<InconsistencyDrawer open onOpenChange={vi.fn()} items={items} {...over} />)
}

describe('InconsistencyDrawer', () => {
  it('每条列出疑似错字、基准写法与两边次数', () => {
    const { baseElement } = renderDrawer([item()])
    // 疑似错字单独成元素（视觉上是主信息），次数与基准写法在其后
    expect(within(baseElement).getByText('「罗问文」')).toBeTruthy()
    expect(within(baseElement).getByText(/出现 5 次/).textContent).toContain('178 次写作「罗向文」')
    expect(within(baseElement).getByText('疑似错字')).toBeTruthy()
  })

  it('high 排最前，未知等级排最后', () => {
    const { baseElement } = renderDrawer([
      item({ variant: '低可信错字', confidence: '' }),
      item({ variant: '高可信错字', confidence: 'high' }),
    ])
    const variants = Array.from(baseElement.querySelectorAll('li')).map((li) => li.textContent ?? '')
    expect(variants[0]).toContain('高可信错字')
    expect(variants[1]).toContain('低可信错字')
  })

  it('点页号跳原页', () => {
    const onGotoPage = vi.fn()
    const { baseElement } = renderDrawer([item()], { onGotoPage })
    fireEvent.click(within(baseElement).getByText('p45'))
    expect(onGotoPage).toHaveBeenCalledWith(45)
  })

  it('没有 onGotoPage 时页号只展示不可点', () => {
    const { baseElement } = renderDrawer([item()])
    expect(within(baseElement).queryByRole('button', { name: 'p12' })).toBeNull()
    // 页号压缩后的文案仍在
    expect(baseElement.textContent).toContain('P12, P45')
  })

  it('旧任务没有不一致数据时给出解释，而不是空白', () => {
    const { baseElement } = renderDrawer([])
    expect(baseElement.textContent).toContain('没有发现跨页不一致')
    expect(baseElement.textContent).toContain('旧任务的识别结果里没有这项统计')
    expect(baseElement.querySelectorAll('li')).toHaveLength(0)
  })

  it('页号缺的条目仍渲染，只是不可跳转', () => {
    const { baseElement } = renderDrawer([item({ pages: [] })])
    expect(baseElement.textContent).toContain('页号缺')
    expect(within(baseElement).queryByRole('button', { name: 'p12' })).toBeNull()
  })
})
