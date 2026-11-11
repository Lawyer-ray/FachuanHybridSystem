/**
 * 要素式转换面板的小工具单测（node 环境）。
 *
 * fmtSize 决定律师看到的文件大小，边界在 1024 / 1024² 两处，
 * 换算出错会让人误判「这份 docx 是不是空的」。
 * saveBlob 会真的往 document 上挂 <a> 并 click，属于 DOM 行为，见
 * DocConvertPanel.dom.test.tsx 的下载用例；这里只测纯函数。
 */
import { describe, expect, it } from 'vitest'

import { fmtSize } from './convert-utils'

describe('fmtSize', () => {
  it('不足 1KB 直接报字节，不带小数', () => {
    expect(fmtSize(0)).toBe('0 B')
    expect(fmtSize(1)).toBe('1 B')
    expect(fmtSize(1023)).toBe('1023 B')
  })

  it('KB 段保留一位小数，边界从 1024 起切换', () => {
    expect(fmtSize(1024)).toBe('1.0 KB')
    expect(fmtSize(1536)).toBe('1.5 KB')
    // 1024² 之前仍是 KB
    expect(fmtSize(1024 * 1024 - 1)).toBe('1024.0 KB')
  })

  it('MB 段保留两位小数', () => {
    expect(fmtSize(1024 * 1024)).toBe('1.00 MB')
    expect(fmtSize(1024 * 1024 * 2.5)).toBe('2.50 MB')
    expect(fmtSize(1024 * 1024 * 12.345)).toBe('12.35 MB')
  })
})
