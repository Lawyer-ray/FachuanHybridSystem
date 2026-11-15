/**
 * 双引擎分歧的纯逻辑单测。
 *
 * 真实痛点：`summary.engine_disagreements` 是自由字典数组，旧任务 / 默认单引擎路径
 * 根本没有这个键。收窄一旦漏判空，打开一个旧材料包就白屏；而分组/排序错了，
 * 高危的姓名分歧会被埋在几十条版面切分差异底下——等于没有这个功能。
 *
 * 核心原则也在这里守一道：**只找分歧，不投票**。所以没有「哪个引擎对」的断言，
 * 只有「两边都摆出来」。
 */
import { describe, expect, it } from 'vitest'

import type { EngineBlockRect, EngineDisagreement } from '../types'
import {
  disagreementKey,
  disagreementKindLabel,
  engineBlocksOfPage,
  engineLabel,
  engineShortLabel,
  groupBySeverity,
  readEngineBlocks,
  readEngineDisagreements,
  sortDisagreements,
  variantTextOf,
} from './engine'
import { setEngineChecked, withEngineDisagreements } from './state'

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

describe('readEngineDisagreements', () => {
  it('缺键 / 非数组 → 空清单（旧任务、默认单引擎都走这条）', () => {
    expect(readEngineDisagreements(undefined)).toEqual([])
    expect(readEngineDisagreements(null)).toEqual([])
    expect(readEngineDisagreements('oops')).toEqual([])
  })

  it('逐条校验：缺页号或不足两个变体的条目丢弃', () => {
    const out = readEngineDisagreements([
      item(),
      { ...item(), page_no: 0 },
      { ...item(), variants: [{ engine: 'mineru', text: '张三丰' }] },
      { ...item(), variants: 'nope' },
    ])
    expect(out).toHaveLength(1)
    expect(out[0]!.page_no).toBe(38)
  })

  it('未知 kind / severity 有兜底，不丢整条', () => {
    const out = readEngineDisagreements([item({ kind: 'other' as never, severity: 'weird' as never })])
    expect(out[0]!.kind).toBe('char')
    expect(out[0]!.severity).toBe('low')
  })

  it('分歧自带的两引擎块框一并收窄', () => {
    const out = readEngineDisagreements([
      {
        ...item(),
        blocks: [
          { engine: 'mineru', page_no: 38, text: '张三丰', rect: { x: 0.1, y: 0.2, w: 0.3, h: 0.05 }, block_type: 'text', approx: false },
          // 零面积框画出来看不见，丢弃
          { engine: 'paddleocr_vl', page_no: 38, text: '张四丰', rect: { x: 0.1, y: 0.2, w: 0, h: 0 }, block_type: 'text', approx: false },
          // 未知引擎丢弃
          { engine: 'magic', page_no: 38, text: 'x', rect: { x: 0, y: 0, w: 1, h: 1 }, block_type: 'text', approx: false },
        ],
      },
    ])
    expect(out[0]!.blocks).toHaveLength(1)
    expect(out[0]!.blocks![0]!.engine).toBe('mineru')
  })
})

describe('readEngineBlocks', () => {
  it('rect.approx 与本层 approx 任一为真即视为近似框', () => {
    const rect = { x: 0.1, y: 0.1, w: 0.2, h: 0.2 }
    const out = readEngineBlocks([
      { engine: 'mineru', page_no: 1, text: 'a', rect, block_type: 'text', approx: true },
      { engine: 'paddleocr_vl', page_no: 1, text: 'b', rect: { ...rect, approx: true }, block_type: 'text', approx: false },
    ])
    expect(out.map((b) => b.approx)).toEqual([true, true])
  })
})

describe('引擎命名', () => {
  it('全名给人看，短名给框旁的窄位置用', () => {
    expect(engineLabel('mineu' as never)).toBe('mineu')
    expect(engineLabel('mineru')).toBe('MinerU')
    expect(engineLabel('paddleocr_vl')).toBe('PaddleOCR-VL')
    // 框小，全名会盖掉框里的字
    expect(engineShortLabel('paddleocr_vl')).toBe('VL')
  })
})

describe('disagreementKey / 已核对', () => {
  it('同一条分歧重跑换顺序后键不变（否则勾会挂到别的条目上）', () => {
    const a = item()
    const b = item({ variants: [...item().variants].reverse() })
    expect(disagreementKey(a)).toBe(disagreementKey(b))
  })

  it('内容变了就是另一条（该重新看）', () => {
    expect(disagreementKey(item())).not.toBe(
      disagreementKey(item({ variants: [{ engine: 'mineru', text: '张三丰' }, { engine: 'paddleocr_vl', text: '张三封' }] })),
    )
  })

  it('setEngineChecked 勾/取消；重复勾不改引用', () => {
    const draft = { mats: [], segs: [], infos: [] }
    const on = setEngineChecked(draft, 'k1', true)
    expect(on.engineChecked).toEqual(['k1'])
    expect(setEngineChecked(on, 'k1', true)).toBe(on)
    expect(setEngineChecked(on, 'k1', false).engineChecked).toEqual([])
  })
})

describe('withEngineDisagreements', () => {
  it('空清单不写入，但会清掉上一次的分歧与勾（它们描述的是上一次识别）', () => {
    const base = { mats: [], segs: [], infos: [], engineDisagreements: [item()], engineChecked: ['x'] }
    const next = withEngineDisagreements(base, [])
    expect(next.engineDisagreements).toBeUndefined()
    expect(next.engineChecked).toBeUndefined()
  })

  it('本来就是空的不改引用（避免无谓的保存与重渲染）', () => {
    const base = { mats: [], segs: [], infos: [] }
    expect(withEngineDisagreements(base, [])).toBe(base)
  })

  it('有分歧时写入并清空旧的核对记录', () => {
    const base = { mats: [], segs: [], infos: [], engineChecked: ['stale'] }
    const next = withEngineDisagreements(base, [item()])
    expect(next.engineDisagreements).toHaveLength(1)
    expect(next.engineChecked).toEqual([])
  })
})

describe('sortDisagreements / groupBySeverity', () => {
  it('high 在前；同级里锚点命中的在前，再按相似度低的在前', () => {
    const sorted = sortDisagreements([
      item({ severity: 'low', page_no: 1, anchor_hit: false }),
      item({ severity: 'medium', page_no: 31, anchor_hit: false, similarity: 0.9 }),
      item({ severity: 'medium', page_no: 32, anchor_hit: true, similarity: 0.5 }),
      item({ severity: 'high', page_no: 38 }),
    ])
    expect(sorted.map((d) => d.page_no)).toEqual([38, 32, 31, 1])
  })

  it('分组时 low 单独给；unchecked 只数还没勾的', () => {
    const list = [item(), item({ severity: 'low', page_no: 3 }), item({ severity: 'medium', page_no: 31 })]
    const groups = groupBySeverity(list, new Set([disagreementKey(list[0]!)]))
    expect(groups.high).toHaveLength(1)
    expect(groups.medium).toHaveLength(1)
    expect(groups.low).toHaveLength(1)
    expect(groups.unchecked).toBe(2)
  })
})

describe('engineBlocksOfPage', () => {
  const seg = { id: 's1', refs: [{ mi: 0, p: 30 }, { mi: 0, p: 31 }], blocks: [] }
  const block = (page: number, engine: EngineBlockRect['engine'] = 'mineru'): EngineBlockRect => ({
    engine,
    page_no: page,
    text: 'x',
    rect: { x: 0, y: 0, w: 1, h: 1 },
    block_type: 'text',
    approx: false,
  })

  it('取本页的框（段起始页偏移口径与 Flow.hitsByPage 一致）', () => {
    const out = engineBlocksOfPage(seg, 31, [block(30), block(31), block(32)])
    expect(out.map((b) => b.page_no)).toEqual([31])
  })

  it('段边界之外的页不画（否则会画到邻段页卡上）', () => {
    expect(engineBlocksOfPage(seg, 32, [block(32)])).toHaveLength(0)
  })
})

describe('variantTextOf / disagreementKindLabel', () => {
  it('missing 类的空变体原样是空串，由 UI 决定怎么写', () => {
    expect(variantTextOf(item(), 'paddleocr_vl')).toBe('张四丰')
    expect(variantTextOf(item(), 'textin')).toBe('')
  })

  it('类型码有中文标签，未知码原样显示', () => {
    expect(disagreementKindLabel('char')).toBe('差一字')
    expect(disagreementKindLabel('missing')).toBe('仅一侧有')
    expect(disagreementKindLabel('other' as never)).toBe('other')
  })
})
