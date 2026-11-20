/**
 * 段名拆分：头部可截断、尾部必须完整。
 *
 * 这里的每一条都对着「两份材料只差页号」的真实场景——尾部（`-P20.pdf`）被裁掉，
 * 律师就无法从左栏认出哪一份是哪一份，而这个错认会直接带到下载与归案。
 */
import { describe, expect, it } from 'vitest'

import { splitNameTail } from './segment-name'

describe('splitNameTail：尾巴怎么切', () => {
  it('保留扩展名 + 紧邻的页号标记', () => {
    expect(splitNameTail('1-授权委托书某甲某乙V1-P20.pdf')).toEqual({
      head: '1-授权委托书某甲某乙V1',
      tail: '-P20.pdf',
    })
  })

  it('页区间写法同样保留（-P3-9.md）', () => {
    expect(splitNameTail('行政复议答复书（某某某很长的说明）-P3-9.md')).toEqual({
      head: '行政复议答复书（某某某很长的说明）',
      tail: '-P3-9.md',
    })
  })

  it('没有页号时只保住扩展名', () => {
    expect(splitNameTail('关于某某某工伤认定的情况说明.docx')).toEqual({
      head: '关于某某某工伤认定的情况说明',
      tail: '.docx',
    })
  })

  it('下划线分隔的页号也认（_P12.pdf）', () => {
    expect(splitNameTail('证据清单_某某某有限公司_P12.pdf')).toEqual({
      head: '证据清单_某某某有限公司',
      tail: '_P12.pdf',
    })
  })
})

describe('splitNameTail：不切的情形', () => {
  it('拆分后头部不足 6 个字 → 不拆（整段本来就放得下）', () => {
    expect(splitNameTail('起诉状.pdf')).toEqual({ head: '起诉状.pdf', tail: '' })
  })

  it('没有扩展名 → 不拆', () => {
    expect(splitNameTail('整份')).toEqual({ head: '整份', tail: '' })
  })

  it('拆分永远不丢字：头 + 尾恒等于原名', () => {
    const names = ['起诉状.pdf', 'P20.pdf', 'a-P20.pdf', '很长很长很长很长的名字-P147-148.pdf', '没有扩展名的材料']
    for (const n of names) {
      const { head, tail } = splitNameTail(n)
      expect(head + tail).toBe(n)
    }
  })
})
