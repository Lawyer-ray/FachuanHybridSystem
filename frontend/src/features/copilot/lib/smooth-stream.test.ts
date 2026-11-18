/**
 * smooth-stream 纯函数测试（node 环境，无 React）。
 *
 * 两条不变量压在这里：
 * - 切点永远落在码点边界（emoji / 生僻字不能被砍成半个代理对）；
 * - 表格行不能半行放出去（半行会被 markdown 当段落排版，每格闪一次）。
 */
import { describe, expect, it } from 'vitest'

import {
  SMOOTH_STREAM_BACKLOG_DIVISOR,
  SMOOTH_STREAM_MIN_STEP,
  advanceCodePoints,
  nextStreamCut,
} from './smooth-stream'

describe('advanceCodePoints：码点边界', () => {
  it('count <= 0 原样返回 from', () => {
    expect(advanceCodePoints('abc', 1, 0)).toBe(1)
    expect(advanceCodePoints('abc', 1, -3)).toBe(1)
  })

  it('纯 ASCII 按 1 个单元一位推进', () => {
    expect(advanceCodePoints('abcdef', 0, 3)).toBe(3)
    expect(advanceCodePoints('abcdef', 2, 2)).toBe(4)
  })

  it('emoji（😀，4 个 UTF-16 单元）整颗跨过，不切代理对', () => {
    const text = '😀'
    expect(text.length).toBe(2) // 一个码点、两个单元
    expect(advanceCodePoints(text, 0, 1)).toBe(2)
    expect(advanceCodePoints(`a${text}b`, 1, 1)).toBe(3)
  })

  it('生僻字（𠮷，代理对）整颗跨过', () => {
    const text = '𠮷'
    expect(text.length).toBe(2)
    expect(advanceCodePoints(text, 0, 1)).toBe(2)
    // 切点落在字符内部的下标上时也不会退回半步
    expect(advanceCodePoints(`x${text}y`, 1, 1)).toBe(3)
  })

  it('混合文本里连续两个代理对字符各算 1 个码点', () => {
    const text = '😀𠮷a'
    expect(text.length).toBe(5)
    expect(advanceCodePoints(text, 0, 2)).toBe(4)
    expect(advanceCodePoints(text, 0, 3)).toBe(5)
  })

  it('超出末尾时钳到 text.length', () => {
    expect(advanceCodePoints('ab', 0, 99)).toBe(2)
    expect(advanceCodePoints('😀', 0, 5)).toBe(2)
  })

  it('裸高代理（无低位跟随）按 1 个单元推进，不越界', () => {
    const lone = `\uD800x`
    expect(advanceCodePoints(lone, 0, 1)).toBe(1)
  })

  it('from 为负时按 0 起算', () => {
    expect(advanceCodePoints('abc', -2, 2)).toBe(2)
  })
})

describe('nextStreamCut：积压越多放越快', () => {
  it('空积压时直接返回全文长度', () => {
    expect(nextStreamCut('abcdef', 6)).toBe(6)
    expect(nextStreamCut('abcdef', 99)).toBe(6)
  })

  it('小积压按最小步长放（MIN_STEP）', () => {
    // backlog = 10，ceil(10/8) = 2，与 MIN_STEP 相等
    expect(nextStreamCut('abcdefghij', 0)).toBe(SMOOTH_STREAM_MIN_STEP)
  })

  it('积压越大每拍放出的字越多（单调不减）', () => {
    const full = 'x'.repeat(400)
    const small = nextStreamCut(full, 380) - 380 // backlog 20
    const medium = nextStreamCut(full, 240) - 240 // backlog 160
    const large = nextStreamCut(full, 80) - 80 // backlog 320
    expect(medium).toBeGreaterThan(small)
    expect(large).toBeGreaterThan(medium)
  })

  it('步长等于 ceil(backlog / DIVISOR)（不低于 MIN_STEP）', () => {
    const full = 'x'.repeat(1000)
    const from = 200
    const expected = Math.max(
      SMOOTH_STREAM_MIN_STEP,
      Math.ceil((full.length - from) / SMOOTH_STREAM_BACKLOG_DIVISOR),
    )
    expect(nextStreamCut(full, from)).toBe(from + expected)
  })
})

describe('nextStreamCut：表格行', () => {
  it('表格行还没写完（找不到换行）时停在行首等', () => {
    const full = '前文\n| a | b'
    // 从行首开始切，本拍不放字，避免半行被当段落
    const cut = nextStreamCut(full, 3)
    expect(cut).toBe(3)
    expect(full.slice(0, cut)).toBe('前文\n')
  })

  it('行首带缩进的表格行同样识别', () => {
    const full = '正文\n   | 标题'
    const lineStart = full.indexOf('   |')
    expect(nextStreamCut(full, lineStart)).toBe(lineStart)
  })

  it('表格行写完时整行一次放出（含换行符）', () => {
    const full = '前文\n| a | b |\n后续正文'
    const lineStart = 3
    const lineEnd = full.indexOf('\n', lineStart) + 1
    // 从行首切：步长远小于整行，但必须一次放到行尾
    expect(nextStreamCut(full, lineStart)).toBe(lineEnd)
    expect(full.slice(0, lineEnd)).toBe('前文\n| a | b |\n')
  })

  it('从行内起切、普通步长落在行内时，仍整行放到行尾', () => {
    // from=4 落在表格行内（第 3–12 字符是 | a | b | ），step≈8 使 cut≈12 落在行内，
    // 于是必须吸附到 lineEnd=13 一次放出整行 —— 否则会先渲染出半行表格导致闪列。
    const full = `前文\n| a | b |\n${'x'.repeat(50)}`
    const lineEnd = full.indexOf('\n', 3) + 1
    const cut = nextStreamCut(full, 4)
    expect(cut).toBe(lineEnd)
    expect(full.slice(0, cut)).toBe('前文\n| a | b |\n')
  })

  it('切点本身已越过行尾时按普通切点返回，不倒退', () => {
    // 让 step 大到一次就跨过整行：全文 400 字 → step = max(2, ceil(400/8)) = 50，
    // 表格行只占第 3–13，cut=50 已远在行尾之后，此时不应再吸附（否则会倒退到 13）。
    const full = `前文\n| a | b |\n${'x'.repeat(400)}`
    const lineEnd = full.indexOf('\n', 3) + 1
    const cut = nextStreamCut(full, 0)
    expect(cut).toBeGreaterThan(lineEnd)
    expect(cut).toBeLessThanOrEqual(full.length)
  })

  it('非表格行按普通步长返回，不吸附到行首', () => {
    const full = '第一行文字\n第二行文字还没写完'
    const cut = nextStreamCut(full, 0)
    expect(cut).toBeLessThan(full.length)
    expect(cut).toBeGreaterThan(0)
  })
})

describe('nextStreamCut：切点合法性', () => {
  const samples = [
    '',
    'plain text with no newline',
    '前文\n| a | b |\n正文继续很长很长很长',
    '😀𠮷 emoji 与生僻字混排\n| c | d |',
    `${'x'.repeat(100)}\n| 表头 | 值 |\n${'y'.repeat(100)}`,
  ]

  it('恒在 [from, full.length] 之间，不越界、不倒退', () => {
    for (const full of samples) {
      for (let from = 0; from <= full.length; from += 1) {
        const cut = nextStreamCut(full, from)
        expect(cut).toBeGreaterThanOrEqual(from)
        expect(cut).toBeLessThanOrEqual(full.length)
      }
    }
  })

  it('切出的文本始终是原文前缀', () => {
    for (const full of samples) {
      for (let from = 0; from <= full.length; from += 1) {
        const cut = nextStreamCut(full, from)
        expect(full.startsWith(full.slice(0, cut))).toBe(true)
        expect(full.slice(0, cut).startsWith(full.slice(0, from))).toBe(true)
      }
    }
  })

  it('不会切出半个代理对', () => {
    const full = 'a😀b𠮷c'
    for (let from = 0; from <= full.length; from += 1) {
      const cut = nextStreamCut(full, from)
      if (cut === 0 || cut === full.length) continue
      const head = full.slice(0, cut)
      const lastCode = head.charCodeAt(head.length - 1)
      // 切点前一位不能是孤立的高代理
      expect(lastCode >= 0xd800 && lastCode <= 0xdbff).toBe(false)
    }
  })

  it('停等（cut === from）只发生在表格行未写完的情形', () => {
    const full = '正文\n| a | b'
    const lineStart = full.indexOf('|')
    expect(nextStreamCut(full, lineStart)).toBe(lineStart)
    // 非表格上下文永远不会原地不动
    expect(nextStreamCut('普通正文还没完', 0)).toBeGreaterThan(0)
  })
})
