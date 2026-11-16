// @vitest-environment jsdom
/**
 * 引擎分歧清单（抽屉）单测。
 *
 * 真实痛点：两个引擎在同一页对同一个名字读得不一样（「张三丰 / 张四丰」）。
 * 这张清单要做到三件事：
 *  1. 两个引擎的文本**并列摆出来**，不排先后、不标「更可能对」——裁决权在律师；
 *  2. 高危在最上面，low（版面切分差异）默认折叠，否则几十条噪声会把真分歧淹掉；
 *  3. 点一条能跳到原页并画双框；勾了「已核对」就置灰且计数减少。
 *
 * 另外：两引擎一致时必须是「一致」这句话，而不是一个空白抽屉。
 */
import { fireEvent, render, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { EngineDisagreement } from '../../types'
import { disagreementKey, uniqueDisagreementKeys } from '../../draft'
import { EngineDisagreementDrawer } from './EngineDisagreementDrawer'

function item(over: Partial<EngineDisagreement> = {}): EngineDisagreement {
  return {
    page_no: 38,
    kind: 'char',
    severity: 'high',
    variants: [
      { engine: 'mineru', text: '张三丰' },
      { engine: 'paddleocr_vl', text: '张四丰' },
    ],
    context: '卖方：赵六 张三丰',
    anchor_hit: true,
    similarity: 0.8,
    ...over,
  }
}

function renderDrawer(
  items: EngineDisagreement[],
  over: Partial<Parameters<typeof EngineDisagreementDrawer>[0]> = {},
) {
  // keys 与 items 一一对应（生产里由 ReaderBody 用 uniqueDisagreementKeys 算好）
  return render(
    <EngineDisagreementDrawer open onOpenChange={vi.fn()} items={items} keys={uniqueDisagreementKeys(items)} {...over} />,
  )
}

function rows(baseElement: HTMLElement): HTMLElement[] {
  return Array.from(baseElement.querySelectorAll<HTMLElement>('[data-engine-disagreement]'))
}

describe('EngineDisagreementDrawer', () => {
  it('两个引擎的文本并列展示，带引擎名', () => {
    const { baseElement } = renderDrawer([item()])
    const row = rows(baseElement)[0]!
    expect(within(row).getByText('MinerU')).toBeTruthy()
    expect(within(row).getByText('PaddleOCR-VL')).toBeTruthy()
    // 两条都摆出来，谁对不由前端说
    expect(row.textContent).toContain('张三丰')
    expect(row.textContent).toContain('张四丰')
    expect(row.textContent).not.toContain('正确')
  })

  it('anchor_hit 时打「含身份证号/账号」标签', () => {
    const hit = renderDrawer([item()])
    expect(rows(hit.baseElement)[0]!.textContent).toContain('含身份证号/账号')
    hit.unmount()
    const plain = renderDrawer([item({ anchor_hit: false })])
    expect(plain.container.textContent).not.toContain('含身份证号/账号')
  })

  it('高危排在最前，low 默认折叠', () => {
    const { baseElement } = renderDrawer([
      item({ severity: 'low', page_no: 1, context: '低危条目' }),
      item({ severity: 'high', page_no: 38, context: '高危条目' }),
    ])
    const visible = rows(baseElement).map((r) => r.textContent ?? '')
    expect(visible[0]).toContain('高危条目')
    // low 没展开时不在 DOM 里
    expect(visible.some((t) => t.includes('低危条目'))).toBe(false)
    expect(baseElement.textContent).toContain('低危（1）')
  })

  it('展开 low 后条目出现', () => {
    const { baseElement } = renderDrawer([item({ severity: 'low', page_no: 1, context: '低危条目' })])
    fireEvent.click(within(baseElement).getByText(/低危（1）/))
    expect(rows(baseElement).map((r) => r.textContent ?? '').join()).toContain('低危条目')
  })

  it('点一条回调 onJump(pageNo, 唯一键)，而不是组内下标', () => {
    const onJump = vi.fn()
    const a = item({ severity: 'medium', page_no: 31 })
    const b = item({ severity: 'medium', page_no: 44 })
    const { baseElement } = renderDrawer([a, b], { onJump })
    fireEvent.click(within(baseElement).getByText('第44页'))
    // 传的是 b 自己的唯一键：分组重排也不会指错条目
    expect(onJump).toHaveBeenCalledWith(44, uniqueDisagreementKeys([a, b])[1])
  })

  it('同一页两条：点第二条跳的是第二条的键，不是第一条', () => {
    // 这是「点了没反应」的根因回归：旧实现按页号 find，一页多条永远命中第一条
    const onJump = vi.fn()
    const same = { page_no: 72, severity: 'high' as const, variants: [{ engine: 'mineru', text: '' }, { engine: 'paddleocr_vl', text: '' }] }
    const a = item({ ...same })
    const b = item({ ...same })
    const keys = uniqueDisagreementKeys([a, b])
    expect(keys[0]).not.toBe(keys[1]) // 裸键撞车，靠唯一键区分
    const { baseElement } = renderDrawer([a, b], { onJump })
    const rowEls = rows(baseElement)
    expect(rowEls).toHaveLength(2)
    // 两条都在第 72 页，按钮文案相同（「第72页」），只能按行取
    fireEvent.click(within(rowEls[1]!).getByRole('button', { name: '第72页' }))
    expect(onJump).toHaveBeenCalledWith(72, keys[1])
  })

  it('勾「已核对」回调键与布尔值，且该条置灰、计数减少', () => {
    const onToggleChecked = vi.fn()
    const d = item()
    const { baseElement, rerender } = renderDrawer([d], { onToggleChecked })
    fireEvent.click(within(baseElement).getByRole('checkbox'))
    expect(onToggleChecked).toHaveBeenCalledWith(disagreementKey(d), true)

    rerender(
      <EngineDisagreementDrawer
        open
        onOpenChange={vi.fn()}
        items={[d]}
        keys={uniqueDisagreementKeys([d])}
        checked={[disagreementKey(d)]}
        onToggleChecked={onToggleChecked}
      />,
    )
    const row = rows(baseElement)[0]!
    expect(row.getAttribute('data-checked')).toBe('true')
    expect(row.className).toContain('opacity-50')
    expect(baseElement.textContent).toContain('已全部核对')
  })

  it('两引擎一致时给「识别一致」这句话，而不是空抽屉', () => {
    const { baseElement } = renderDrawer([])
    expect(baseElement.textContent).toContain('两个引擎的识别结果一致')
    expect(baseElement.textContent).toContain('两引擎识别一致')
  })

  it('missing 类的空文本显示「（无此行）」，不留白', () => {
    const { baseElement } = renderDrawer([
      item({
        kind: 'missing',
        variants: [
          { engine: 'mineru', text: '独有的一行' },
          { engine: 'paddleocr_vl', text: '' },
        ],
      }),
    ])
    expect(rows(baseElement)[0]!.textContent).toContain('（无此行）')
  })
})
