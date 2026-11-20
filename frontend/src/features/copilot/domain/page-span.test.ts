/**
 * 工具结果里的页标解析。
 *
 * 两个不变量必须同时成立：
 * 1. 页标**不能留在正文里**（否则材料原文中间会冒出 `[page: 12]` 这种噪音）；
 * 2. 页归属不能错位（页标之后、下一个页标之前的内容属于这一页——错位一格
 *    就等于把「第 12 段」的定位指到了别的材料段上）。
 */

import { describe, expect, it } from 'vitest'

import { splitPageSpans } from './page-span'

describe('splitPageSpans：多页切分', () => {
  it('按页标切成多段，每段带上自己的页号', () => {
    const text = '[page: 1]\n第一页正文\n[page: 2]\n第二页正文'
    expect(splitPageSpans(text)).toEqual([
      { page: 1, text: '第一页正文' },
      { page: 2, text: '第二页正文' },
    ])
  })

  it('页标被剔除，正文里不再残留 [page: N]', () => {
    const spans = splitPageSpans('[page: 3]甲方应于 30 日内付款[page: 4]乙方有权解除')
    const joined = spans.map((span) => span.text).join('')
    expect(joined).not.toContain('[page')
    expect(joined).not.toContain('page:')
    expect(spans[0]?.text).toBe('甲方应于 30 日内付款')
  })

  it('页标在段落中间也切得开（解析器按行插标，不保证落在段首）', () => {
    const spans = splitPageSpans('前一句[page: 2]后一句')
    expect(spans).toEqual([
      { page: undefined, text: '前一句' },
      { page: 2, text: '后一句' },
    ])
  })

  it('容忍页标里的空格与大小写（解析器换实现时不至于整篇失效）', () => {
    expect(splitPageSpans('[Page: 7]\n正文')).toEqual([{ page: 7, text: '正文' }])
    expect(splitPageSpans('[page:12]\n正文')).toEqual([{ page: 12, text: '正文' }])
  })

  it('同一页被切了两段（分块解析）→ 合并，不让「第 3 段」出现两次', () => {
    expect(splitPageSpans('[page: 3]甲[page: 3]乙')).toEqual([{ page: 3, text: '甲\n乙' }])
  })

  it('连续页标之间的空段丢弃（不渲染空壳）', () => {
    expect(splitPageSpans('[page: 1][page: 2]\n正文')).toEqual([{ page: 2, text: '正文' }])
  })
})

describe('splitPageSpans：无页标 / 空输入', () => {
  it('没有页标 → 单段 page: undefined（老数据照常渲染）', () => {
    expect(splitPageSpans('整段没有页标的原文')).toEqual([
      { page: undefined, text: '整段没有页标的原文' },
    ])
  })

  it('首尾空白裁掉（贴进气泡不该多出空行）', () => {
    expect(splitPageSpans('\n\n  正文  \n\n')).toEqual([{ page: undefined, text: '正文' }])
  })

  it('空 / 全空白 → 空数组（调用方据此不渲染）', () => {
    expect(splitPageSpans('')).toEqual([])
    expect(splitPageSpans('  \n\t\n ')).toEqual([])
  })

  it('重复调用不串状态（lastIndex 复位：正则带 g 标志时最容易踩的坑）', () => {
    const first = splitPageSpans('[page: 1]甲')
    const second = splitPageSpans('[page: 1]甲')
    expect(second).toEqual(first)
  })
})
