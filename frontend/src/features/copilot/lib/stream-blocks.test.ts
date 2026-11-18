/**
 * splitStreamingMarkdownBlocks：流式 markdown 的安全分块。
 *
 * 这里锁的第一条是**硬不变量**：`blocks.join('') === text`，一字不差。
 * 切点算错就会吞掉或重复换行，渲染出的 Markdown 立刻变形。
 *
 * 第二条是**保守性**：拿不准的地方必须放弃切分（整篇一块）。
 * 少切只是慢一点，错切会渲染出错误的结构（松散列表拆成两个列表、
 * 引用定义与引用分离、代码块被截断）。
 *
 * 背景见 docs/harness/pitfalls.md PIT-007。
 */

import { describe, expect, it } from 'vitest'

import { splitStreamingMarkdownBlocks } from './stream-blocks'

/** 每个用例都要过的硬不变量：拼回去必须与原文一字不差 */
function expectRoundTrip(text: string): string[] {
  const blocks = splitStreamingMarkdownBlocks(text)
  expect(blocks.join('')).toBe(text)
  return blocks
}

describe('splitStreamingMarkdownBlocks：硬不变量 join === text', () => {
  const samples = [
    '',
    '单段落',
    '段落一\n\n段落二',
    '段落一\n\n\n段落三',
    '# 标题\n\n正文',
    '- a\n- b\n\n- c',
    '```\ncode\n\nmore\n```\n\n后文',
    '前文\n\n| a | b |\n| --- | --- |\n| 1 | 2 |',
    '引用\n\n> 引用内容\n\n后文',
    '[ref]: https://example.com\n\n正文 [ref]',
    '正文\n\n   缩进续行',
    '前文\n\n<pre>\n块\n\n还在块里\n</pre>',
    '前文\r\n\r\n后文',
  ]

  it.each(samples)('拼回去与原文相等：%j', (text) => {
    expectRoundTrip(text)
  })
})

describe('splitStreamingMarkdownBlocks：边界与退化', () => {
  it('空字符串返回空数组', () => {
    expect(splitStreamingMarkdownBlocks('')).toEqual([])
  })

  it('没有空行的单段落返回整块', () => {
    expect(expectRoundTrip('一整段没有任何空行的文字')).toEqual(['一整段没有任何空行的文字'])
  })

  it('两个段落按空行切成两块', () => {
    // 切点落在空行之后，空行全部留在上一块尾部（对解析等价，且不丢字符）
    const blocks = expectRoundTrip('第一段\n\n第二段')
    expect(blocks).toHaveLength(2)
    expect(blocks[0]).toBe('第一段\n\n')
    expect(blocks[1]).toBe('第二段')
  })

  it('连续多个空行只切成两块（不产生空块），多余换行留在块里', () => {
    const blocks = expectRoundTrip('甲\n\n\n乙')
    expect(blocks).toHaveLength(2)
    expect(blocks[0]).toBe('甲\n\n')
    expect(blocks[1]).toBe('\n乙')
  })

  it('结尾的空行不产生空块', () => {
    const blocks = expectRoundTrip('正文\n\n')
    expect(blocks).toEqual(['正文\n\n'])
  })
})

describe('splitStreamingMarkdownBlocks：围栅代码块内不切', () => {
  it('代码块内的空行不切分', () => {
    const text = '正文\n\n```\n第一行\n\n第二行\n```\n\n后文'
    const blocks = expectRoundTrip(text)
    // 在「正文」后切一次。代码块内部的空行不切（否则会截断围栏）；
    // 代码块结束后的空行也不切（保守），所以代码块与后文合为第二块。
    expect(blocks).toHaveLength(2)
    expect(blocks[1]).toContain('第一行')
    expect(blocks[1]).toContain('第二行')
    expect(blocks[1]).toContain('后文')
  })

  it('未闭合的围栅（流式中）从围栏起保持一块，不在围栏内切', () => {
    const text = '正文\n\n```\n还没写完的代码'
    const blocks = expectRoundTrip(text)
    // 「正文」是完整段落可以切；围栏开在流式中途，其内部绝不能再切
    expect(blocks).toHaveLength(2)
    expect(blocks[0]).toBe('正文\n\n')
    expect(blocks[1]).toBe('```\n还没写完的代码')
  })

  it('收尾围栏带语言名不能当作关闭', () => {
    // 第一个 ``` 开门，```js 是块内的一行代码而不是收尾，因此后面仍不切分
    const text = '正文\n\n```\na\n```js\nb\n\nc'
    const blocks = expectRoundTrip(text)
    // 围栏未闭合（```js 不是收尾），所以从围栏开始到文末整块保留
    expect(blocks).toHaveLength(2)
    expect(blocks[1]).toContain('```js')
    expect(blocks[1]).toContain('\n\nc')
  })

  it('围栏内的列表项不被当作容器块', () => {
    const text = '```\n- 这是代码不是列表\n\n- 仍是代码\n```'
    expect(expectRoundTrip(text)).toHaveLength(1)
  })
})

describe('splitStreamingMarkdownBlocks：保守退化为整块', () => {
  it('松散列表（项间有空行）不被拆开', () => {
    const text = '- 第一项\n\n- 第二项'
    expect(expectRoundTrip(text)).toHaveLength(1)
  })

  it('空行后接缩进续行不切', () => {
    const text = '段落\n\n   缩进续行仍属上一段'
    expect(expectRoundTrip(text)).toHaveLength(1)
  })

  it('空行后接引用块不切（引用可跨空行）', () => {
    const text = '正文\n\n> 引用第一段\n\n> 引用第二段'
    expect(expectRoundTrip(text)).toHaveLength(1)
  })

  it('链接引用定义使整篇保持一块', () => {
    const text = '正文\n\n[ref]: https://example.com'
    expect(expectRoundTrip(text)).toHaveLength(1)
  })

  it('脚注定义使整篇保持一块', () => {
    const text = '正文\n\n[^1]: 脚注内容'
    expect(expectRoundTrip(text)).toHaveLength(1)
  })

  it('未闭合的原始 HTML 块整篇一块', () => {
    const text = '正文\n\n<pre>\n没闭合'
    expect(expectRoundTrip(text)).toHaveLength(1)
  })

  it('回归：已闭合的 HTML 块内部含空行时，绝不能从中间劈开', () => {
    // 2026-11-18 修正的真实 bug：原实现只在切点处判断「是否处于未闭合 HTML 块」，
    // 漏了「HTML 块开在切点之前」这种形态，于是把 <pre> 块从中间劈成两段。
    const text = 'a\n\n<pre>\nraw\n\nstill raw\n</pre>'
    const blocks = expectRoundTrip(text)
    expect(blocks).toHaveLength(2)
    expect(blocks[1]).toBe('<pre>\nraw\n\nstill raw\n</pre>')
  })

  it('已闭合的原始 HTML 块之后可以切', () => {
    const text = '<pre>一行</pre>\n\n后文'
    const blocks = expectRoundTrip(text)
    expect(blocks).toHaveLength(2)
    expect(blocks[1]).toBe('后文')
  })
})

describe('splitStreamingMarkdownBlocks：正常切分场景', () => {
  it('标题与正文切两块', () => {
    const blocks = expectRoundTrip('# 标题\n\n正文内容')
    expect(blocks).toHaveLength(2)
    expect(blocks[0]).toBe('# 标题\n\n')
  })

  it('表格整体不被切开（表格内没有空行）', () => {
    const text = '前文\n\n| a | b |\n| --- | --- |\n| 1 | 2 |'
    const blocks = expectRoundTrip(text)
    expect(blocks).toHaveLength(2)
    expect(blocks[1]).toContain('| --- | --- |')
  })

  it('多个段落穿插代码块，块数与内容都正确', () => {
    const text = [
      '段落一',
      '',
      '段落二',
      '',
      '```ts',
      'const a = 1',
      '',
      'const b = 2',
      '```',
      '',
      '段落三',
    ].join('\n')

    const blocks = expectRoundTrip(text)
    // 代码块与其后的段落之间那个空行不构成安全切点（围栏闭合行之后
    // spansAcrossBlank 覆盖到代码块内部），因此合并为一块。
    // 少切只是慢一点，错切会渲染出错 —— 这是有意的保守。
    expect(blocks).toHaveLength(3)
    expect(blocks[0]).toBe('段落一\n\n')
    expect(blocks[1]).toBe('段落二\n\n')
    expect(blocks[2]).toContain('const a = 1')
    expect(blocks[2]).toContain('const b = 2')
    expect(blocks[2]).toContain('段落三')
  })

  it('CRLF 换行同样能正确切分且不丢字符', () => {
    const blocks = expectRoundTrip('第一段\r\n\r\n第二段')
    expect(blocks).toHaveLength(2)
    expect(blocks[1]).toBe('第二段')
  })

  it('流式生长过程中反复切分，每一帧都满足拼回等值', () => {
    const full = '第一段\n\n第二段\n\n```\n代码\n\n代码\n```\n\n第三段'
    for (let i = 0; i <= full.length; i += 1) {
      const partial = full.slice(0, i)
      expect(splitStreamingMarkdownBlocks(partial).join('')).toBe(partial)
    }
  })
})
