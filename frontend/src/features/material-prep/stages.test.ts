import { describe, expect, it } from 'vitest'

import {
  DEFAULT_PACK_STAGE,
  PACK_STAGES,
  PREP_SECTIONS,
  isPackStage,
  parseStage,
  sectionOf,
  stageToQuery,
} from './stages'

/**
 * 阶段模型的纯逻辑测试。
 *
 * 这几条看似琐碎，但它们是「收件箱与材料包」层级结构的地基：
 * 一级区段一旦写错、或 parseStage 对脏值放行，URL / 计数 / 主区域
 * 三者就会各自指向不同位置。
 */
describe('stages：两级导航', () => {
  it('一级只有收件箱与材料包两项（不是四个平级页签）', () => {
    // 旧模型把「收件箱」和三种材料包状态平铺成四个页签，混了
    // 「来源」与「状态」两个正交维度，还导致同一份材料被数两次。
    expect(PREP_SECTIONS.map((s) => s.key)).toEqual(['inbox', 'pack'])
    expect(PREP_SECTIONS.map((s) => s.label)).toEqual(['收件箱', '材料包'])
  })

  it('材料包二级是三个状态，顺序即漏斗顺序', () => {
    expect(PACK_STAGES.map((s) => s.key)).toEqual(['todo', 'done', 'filed'])
  })

  it('材料包区段默认落在「待处理」', () => {
    expect(DEFAULT_PACK_STAGE).toBe('todo')
  })
})

describe('stages：sectionOf 归属', () => {
  it('收件箱归 inbox，三个状态归 pack', () => {
    expect(sectionOf('inbox')).toBe('inbox')
    expect(sectionOf('todo')).toBe('pack')
    expect(sectionOf('done')).toBe('pack')
    expect(sectionOf('filed')).toBe('pack')
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

  it('旧的 ?stage=todo 链接仍然有效（历史书签 / NewProjectDialog 依赖）', () => {
    // 材料包升为一级后，状态值仍是同一个字符串，所以旧链接不需要迁移
    expect(parseStage('todo')).toBe('todo')
  })
})

describe('stages：stageToQuery', () => {
  it('收件箱是默认阶段，不写 query（保持 /material-prep 干净）', () => {
    expect(stageToQuery('inbox')).toBeNull()
  })

  it('材料包三态写入各自的 query 值', () => {
    expect(stageToQuery('todo')).toBe('todo')
    expect(stageToQuery('done')).toBe('done')
    expect(stageToQuery('filed')).toBe('filed')
  })
})
