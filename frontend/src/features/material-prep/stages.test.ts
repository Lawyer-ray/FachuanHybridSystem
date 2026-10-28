import { describe, expect, it } from 'vitest'

import { PACK_STAGES, PREP_STAGES, isPackStage, parseStage } from './stages'

/**
 * 阶段模型的纯逻辑测试。
 *
 * 这几条看似琐碎，但它们是「收件箱与材料包同页」这个结构的地基：
 * 页签顺序一旦被随手改成字母序、或 parseStage 对脏值放行，
 * URL / 计数 / 主区域三者就会各自指向不同阶段。
 */
describe('stages：流水线顺序', () => {
  it('页签顺序即漏斗顺序：收件箱在待处理之前', () => {
    expect(PREP_STAGES.map((s) => s.key)).toEqual(['inbox', 'todo', 'done', 'filed'])
  })

  it('PACK_STAGES 是去掉收件箱后的材料包三态（供 PackGrid / 三态计数用）', () => {
    // 收件箱不是材料包状态：混进来会让材料包视图多出一个不属于它的页签
    expect(PACK_STAGES.map((s) => s.key)).toEqual(['todo', 'done', 'filed'])
  })
})

describe('stages：isPackStage', () => {
  it('三个材料包状态为真，收件箱为假', () => {
    expect(isPackStage('todo')).toBe(true)
    expect(isPackStage('done')).toBe(true)
    expect(isPackStage('filed')).toBe(true)
    expect(isPackStage('inbox')).toBe(false)
  })
})

describe('stages：parseStage', () => {
  it('合法值原样返回', () => {
    expect(parseStage('inbox')).toBe('inbox')
    expect(parseStage('todo')).toBe('todo')
    expect(parseStage('done')).toBe('done')
    expect(parseStage('filed')).toBe('filed')
  })

  it('缺省（无 query）落回收件箱——漏斗第一段是页面的默认问题', () => {
    expect(parseStage(null)).toBe('inbox')
    expect(parseStage('')).toBe('inbox')
  })

  it('非法值一律回落收件箱，不因脏 URL 白屏', () => {
    expect(parseStage('nope')).toBe('inbox')
    expect(parseStage('<script>')).toBe('inbox')
    // 大小写敏感：'TODO' 不是合法阶段，避免「看着像就放行」的模糊匹配
    expect(parseStage('TODO')).toBe('inbox')
  })
})
