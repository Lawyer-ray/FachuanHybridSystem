// @vitest-environment jsdom
/**
 * 内联「本段识别分歧」测试（jsdom）。
 *
 * 关键行为：
 * 1. 只显示**当前段覆盖的页**的分歧（全卷 332 条不能全塞进侧栏）
 * 2. refs 跳号（切出几页 / 删页后是 [1,3,7]）时判断仍正确
 * 3. 「采用」把这个引擎的文本原样回传，由调用方写回正文
 * 4. 当前段没分歧时整块不渲染（不占版面、不留空标题）
 */
import { fireEvent, render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { uniqueDisagreementKeys } from '../../draft'
import type { EngineDisagreement, Segment } from '../../types'
import { EngineDisagreementsInline } from './EngineDisagreementsInline'

function seg(pages: number[], over: Partial<Segment> = {}): Segment {
  return {
    id: 'seg-a',
    t: '',
    fn: '证据.pdf',
    refs: pages.map((p) => ({ mi: 0, p })),
    manual: false,
    ...over,
  }
}

function dis(over: Partial<EngineDisagreement> = {}): EngineDisagreement {
  return {
    page_no: 3,
    kind: 'char',
    severity: 'high',
    variants: [
      { engine: 'mineru', text: '示例甲' },
      { engine: 'paddleocr_vl', text: '示例乙' },
    ] as EngineDisagreement['variants'],
    context: '借款人',
    anchor_hit: false,
    similarity: 0.8,
    ...over,
  }
}

function renderInline(
  items: EngineDisagreement[],
  s: Segment | null,
  over: Partial<Parameters<typeof EngineDisagreementsInline>[0]> = {},
) {
  return render(<EngineDisagreementsInline seg={s} items={items} keys={uniqueDisagreementKeys(items)} {...over} />)
}

describe('EngineDisagreementsInline', () => {
  it('只显示本段覆盖页的分歧，别的页不渲染', () => {
    const items = [dis({ page_no: 3 }), dis({ page_no: 99 })]
    const { baseElement } = renderInline(items, seg([1, 2, 3]))
    const rows = baseElement.querySelectorAll('[data-engine-inline-row]')
    expect(rows).toHaveLength(1)
    expect(baseElement.textContent).toContain('第3页')
    expect(baseElement.textContent).not.toContain('第99页')
  })

  it('refs 跳号（切出/删页后是 [1,3,7]）时仍按页号判断，不用减法下标', () => {
    // 旧实现用 page_no - firstPage 当下标，这里 7 - 1 = 6 会越界 → 漏判
    const items = [dis({ page_no: 7 }), dis({ page_no: 2 })]
    const { baseElement } = renderInline(items, seg([1, 3, 7]))
    const rows = baseElement.querySelectorAll('[data-engine-inline-row]')
    expect(rows).toHaveLength(1)
    expect(baseElement.textContent).toContain('第7页')
  })

  it('当前段没有分歧时整块不渲染（不占版面）', () => {
    const { baseElement } = renderInline([dis({ page_no: 99 })], seg([1, 2]))
    expect(baseElement.querySelector('[data-engine-inline]')).toBeNull()
  })

  it('seg 为 null 时不渲染', () => {
    const { baseElement } = renderInline([dis()], null)
    expect(baseElement.querySelector('[data-engine-inline]')).toBeNull()
  })

  it('显示两个引擎的文本，全部自动换行（不用 truncate 截断）', () => {
    const { baseElement } = renderInline([dis()], seg([3]))
    expect(baseElement.textContent).toContain('示例甲')
    expect(baseElement.textContent).toContain('示例乙')
    // 正文 dd 必须 break-words；truncate 会把内容截成一行省略号，窄栏下等于看不见
    const dds = Array.from(baseElement.querySelectorAll('[data-engine-inline-row] dd'))
    expect(dds.length).toBe(2)
    dds.forEach((dd) => {
      expect(dd.className).toContain('break-words')
      expect(dd.className).not.toContain('truncate')
    })
  })

  it('点「采用」回传该侧的整段文字与页号', () => {
    const onAdopt = vi.fn()
    const { baseElement } = renderInline([dis()], seg([3]), { onAdopt })
    const buttons = Array.from(baseElement.querySelectorAll('button')).filter((b) => b.textContent === '采用')
    expect(buttons).toHaveLength(2)
    fireEvent.click(buttons[1]!)
    // 引擎标识不再回传（下游只看文本，见 use-engine-adopt），文字仍是该侧那一份
    expect(onAdopt).toHaveBeenCalledWith(3, '示例乙', expect.any(String))
  })

  it('空文本的一侧显示「（无此行）」且不给「采用」按钮', () => {
    const items = [
      dis({
        kind: 'missing',
        variants: [
          { engine: 'mineru', text: '' },
          { engine: 'paddleocr_vl', text: '只有这侧有' },
        ] as EngineDisagreement['variants'],
      }),
    ]
    const { baseElement } = renderInline(items, seg([3]), { onAdopt: vi.fn() })
    expect(baseElement.textContent).toContain('（无此行）')
    const buttons = Array.from(baseElement.querySelectorAll('button')).filter((b) => b.textContent === '采用')
    expect(buttons).toHaveLength(1) // 只有有文字的那侧可采纳
  })

  it('勾「已核对」回传唯一键', () => {
    const onToggleChecked = vi.fn()
    const items = [dis()]
    const keys = uniqueDisagreementKeys(items)
    const { baseElement } = renderInline(items, seg([3]), { onToggleChecked })
    fireEvent.click(baseElement.querySelector('input[type="checkbox"]')!)
    expect(onToggleChecked).toHaveBeenCalledWith(keys[0], true)
  })

  it('标题显示本段条数，可折叠', () => {
    const { baseElement } = renderInline([dis({ page_no: 3 })], seg([3]))
    expect(baseElement.textContent).toContain('本段识别分歧')
    expect(baseElement.textContent).toContain('1')
    const toggle = baseElement.querySelector('[data-engine-inline] > button')!
    fireEvent.click(toggle)
    expect(baseElement.querySelectorAll('[data-engine-inline-row]')).toHaveLength(0)
  })

  it('用的是容器查询而非媒体查询（宽度由拖拽决定，与视口宽无关）', () => {
    const { baseElement } = renderInline([dis()], seg([3]))
    const section = baseElement.querySelector('[data-engine-inline]')!
    expect(section.className).toContain('@container')
    const row = baseElement.querySelector('[data-engine-inline-row] > dl > div')!
    expect(row.className).toContain('@[220px]:flex-row')
  })
})

describe('EngineDisagreementsInline：差异高亮与双击定位', () => {
  it('只高亮归一化后仍有差异的字（纯标点差异不高亮）', () => {
    const items = [
      dis({
        variants: [
          { engine: 'mineru', text: '客户姓名:张甲某 余额1208元' },
          { engine: 'paddleocr_vl', text: '客户姓名：张甲某 余额1208元' },
        ] as EngineDisagreement['variants'],
      }),
    ]
    const { baseElement } = renderInline(items, seg([3]))
    // 只有全半角冒号不同 → 一个 mark 都不该有
    expect(baseElement.querySelectorAll('mark[data-diff-changed]')).toHaveLength(0)
  })

  it('真错字用 mark 标出来', () => {
    const items = [
      dis({
        variants: [
          { engine: 'mineru', text: '张甲某贷款余额1208元' },
          { engine: 'paddleocr_vl', text: '张乙某贷款余额1208元' },
        ] as EngineDisagreement['variants'],
      }),
    ]
    const { baseElement } = renderInline(items, seg([3]))
    const marks = Array.from(baseElement.querySelectorAll('mark[data-diff-changed]'))
    expect(marks.length).toBeGreaterThan(0)
    expect(marks.map((m) => m.textContent).join('')).toContain('甲')
  })

  it('双击整行触发 onJump（跳到原页 + 画框 + 滚到坐标）', () => {
    const onJump = vi.fn()
    const items = [dis()]
    const keys = uniqueDisagreementKeys(items)
    const { baseElement } = renderInline(items, seg([3]), { onJump })
    fireEvent.doubleClick(baseElement.querySelector('[data-engine-inline-row]')!)
    expect(onJump).toHaveBeenCalledWith(3, keys[0])
  })

  it('行上有可双击的提示（title），律师能发现这个入口', () => {
    const { baseElement } = renderInline([dis()], seg([3]), { onJump: vi.fn() })
    const row = baseElement.querySelector('[data-engine-inline-row]')!
    expect(row.getAttribute('title')).toContain('双击')
  })
})

describe('EngineDisagreementsInline：全文与折叠', () => {
  it('显示全文而不是摘要（摘要带省略号，判断不了哪侧对）', () => {
    const full = '甲'.repeat(300)
    const items = [
      dis({
        variants: [
          { engine: 'mineru', text: '甲'.repeat(120) + '…', full_text: full },
          { engine: 'paddleocr_vl', text: '乙'.repeat(120) + '…', full_text: '乙'.repeat(300) },
        ] as EngineDisagreement['variants'],
      }),
    ]
    const { baseElement } = renderInline(items, seg([3]))
    // 折叠时给「展开全文（300 字）」，说明后端到底给了多少
    expect(baseElement.textContent).toContain('展开全文（300 字）')
    expect(baseElement.textContent).not.toContain('…')
  })

  it('点「展开全文」显示后 300 字', () => {
    const items = [
      dis({
        variants: [
          { engine: 'mineru', text: '摘要…', full_text: 'A'.repeat(300) },
          { engine: 'paddleocr_vl', text: '摘要…', full_text: 'B'.repeat(300) },
        ] as EngineDisagreement['variants'],
      }),
    ]
    const { baseElement } = renderInline(items, seg([3]))
    const btns = Array.from(baseElement.querySelectorAll('button[data-expand-fulltext]'))
    expect(btns.length).toBeGreaterThan(0)
    fireEvent.click(btns[0]!)
    // 展开后出现「收起」
    expect(baseElement.textContent).toContain('收起')
  })

  it('采用/修改回传的是**全文**而不是摘要（摘要拿去 includes 正文必然失败）', () => {
    const onAdopt = vi.fn()
    const onEdit = vi.fn()
    const full = '完整的正文这一行'.repeat(30)
    const items = [
      dis({
        variants: [
          { engine: 'mineru', text: '完整的正文…', full_text: full },
          { engine: 'paddleocr_vl', text: '另一侧…', full_text: full + 'X' },
        ] as EngineDisagreement['variants'],
      }),
    ]
    const { baseElement } = renderInline(items, seg([3]), { onAdopt, onEdit })
    const adopt = Array.from(baseElement.querySelectorAll('button')).find((b) => b.textContent === '采用')!
    fireEvent.click(adopt)
    expect(onAdopt).toHaveBeenCalledWith(3, full, expect.any(String))

    const edit = Array.from(baseElement.querySelectorAll('button')).find((b) => b.textContent?.includes('修改'))!
    fireEvent.click(edit)
    expect(onEdit).toHaveBeenCalledWith(3, full, expect.any(String))
  })
})
