// @vitest-environment jsdom
/**
 * 跨页不一致清单（抽屉）单测。
 *
 * 真实痛点：同一枚章被识别 150+ 次，其中 5 次错成另一种写法。
 * 律师逐页翻不可能发现，所以这份清单必须做到三件事：
 *  1. 有统计证据的那种（kind=frequency）才点名「疑似错字」，多的那个是基准；
 *  2. high 排最前（最该看的永远在最上面）；
 *  3. 点页号能回到那一页——只能看不能跳的清单等于让人自己再去找。
 *
 * 另外两条回归：旧任务没有这项统计时给一句解释而不是空白抽屉；
 * **姓名聚类（entity_cluster）绝不能说「疑似错字」**——那会让律师把两个真人合并成一个。
 */
import { fireEvent, render, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Inconsistency } from '../../types'
import { InconsistencyDrawer } from './InconsistencyDrawer'

function item(over: Partial<Inconsistency> = {}): Inconsistency {
  return {
    canonical: '测试甲',
    variant: '测试乙',
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
    expect(within(baseElement).getByText('「测试乙」')).toBeTruthy()
    expect(within(baseElement).getByText(/出现 5 次/).textContent).toContain('178 次写作「测试甲」')
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

/**
 * 后端逐条给 kind（frequency / entity_cluster / id_malformed），三种判据的证据强度
 * 完全不同，文案必须分支。最危险的回归：把姓名聚类说成「疑似错字」——同姓同名首字的
 * 兄弟姐妹完全可能落进同一簇，律师照着改就把两个真人合并成一个。
 */
describe('InconsistencyDrawer：按 kind 分文案', () => {
  const cluster = () => item({ kind: 'entity_cluster', confidence: 'medium', canonical_count: 2, variant_count: 2 })
  // 证号用合成占位串（不写真实/仿真身份证号，避免隐私门禁与误认）：
  // 结构合法性由后端判，前端这里只锁「文案有没有点明结构异常 + 给出唯一合法候选」
  const malformed = () => item({
    kind: 'id_malformed',
    confidence: 'medium',
    canonical: '合法证号甲',
    variant: '异常证号乙',
    canonical_count: 1,
    variant_count: 1,
  })

  it('frequency：保持原文案与「疑似错字」标签', () => {
    const { baseElement } = renderDrawer([item({ kind: 'frequency' })])
    expect(within(baseElement).getByText('疑似错字')).toBeTruthy()
    expect(within(baseElement).getByText(/出现 5 次/).textContent).toContain('178 次写作「测试甲」')
  })

  it('缺 kind（旧任务产物 / 旧草稿）回退 frequency 文案', () => {
    const { baseElement } = renderDrawer([item()])
    expect(within(baseElement).getByText('疑似错字')).toBeTruthy()
    expect(baseElement.textContent).toContain('178 次写作「测试甲」')
  })

  it('未知 kind（后端将来加判据）也回退 frequency，不整块崩', () => {
    const { baseElement } = renderDrawer([item({ kind: 'brand_new_kind' })])
    expect(within(baseElement).getByText('疑似错字')).toBeTruthy()
  })

  it('entity_cluster：标签「姓名多写法候选」，只请核对是否同一人，不说哪个对', () => {
    const { baseElement } = renderDrawer([cluster()])
    expect(within(baseElement).getByText('姓名多写法候选')).toBeTruthy()
    expect(baseElement.textContent).toContain('同一角色下另有「测试甲」等写法，请核对是否同一人')
    // 绝不能出现「疑似错字」，也不能用次数暗示 canonical 是正确答案
    expect(baseElement.textContent).not.toContain('疑似错字')
    expect(baseElement.textContent).not.toContain('次写作')
    expect(baseElement.textContent).not.toContain('出现 2 次')
  })

  it('id_malformed：标签「证件号结构异常」，文案点明位数结构不合法 + 唯一合法候选', () => {
    const { baseElement } = renderDrawer([malformed()])
    expect(within(baseElement).getByText('证件号结构异常')).toBeTruthy()
    expect(baseElement.textContent).toContain('位数结构不合法')
    expect(baseElement.textContent).toContain('唯一合法候选「合法证号甲」')
    expect(baseElement.textContent).not.toContain('疑似错字')
  })

  it('三种 kind 混排：有统计证据的 frequency（high）排在两类 medium 之前', () => {
    const { baseElement } = renderDrawer([cluster(), malformed(), item({ kind: 'frequency' })])
    const rows = Array.from(baseElement.querySelectorAll('li')).map((li) => li.textContent ?? '')
    expect(rows[0]).toContain('疑似错字')
    expect(rows.slice(1).join('|')).toContain('姓名多写法候选')
    expect(rows.slice(1).join('|')).toContain('证件号结构异常')
  })

  it('分支后页号仍可点跳转（新判据也要能翻回原页核对）', () => {
    const onGotoPage = vi.fn()
    const { baseElement } = renderDrawer([cluster()], { onGotoPage })
    fireEvent.click(within(baseElement).getByText('p45'))
    expect(onGotoPage).toHaveBeenCalledWith(45)
  })

  it('抽屉说明不再把全部条目说成「两种写法」（聚类是 ≥3 种）', () => {
    const { baseElement } = renderDrawer([cluster()])
    expect(baseElement.textContent).toContain('出现多种写法')
  })
})
