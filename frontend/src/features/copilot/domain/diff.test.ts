import { describe, expect, it } from 'vitest'

import { foldRows, hunkRows, lineDiff } from './diff'

/** 把 hunks 压成「首字符 + 文本」的紧凑断言形状，读起来跟 unified diff 一样 */
function shape(hunks: ReturnType<typeof lineDiff>['hunks']): string[][] {
  return hunks.map((h) => h.lines)
}

describe('lineDiff', () => {
  it('完全相同 → 0 个 hunk（调用方据此不渲染）', () => {
    const diff = lineDiff('第一段\n第二段', '第一段\n第二段')
    expect(diff.hunks).toEqual([])
    expect(diff.truncated).toBe(false)
  })

  it('改一段：只包住被改行与上下文，行号对得上', () => {
    const before = ['甲', '乙', '丙', '丁', '戊'].join('\n')
    const after = ['甲', '乙', '丙改', '丁', '戊'].join('\n')
    const diff = lineDiff(before, after)
    // context=3 且只有 5 行：上下文取到两端为止
    expect(shape(diff.hunks)).toEqual([
      [' 甲', ' 乙', '-丙', '+丙改', ' 丁', ' 戊'],
    ])
    const [hunk] = diff.hunks
    if (!hunk) throw new Error('应当产出 1 个 hunk')
    // 旧侧从第 1 行开始（甲），新侧同样
    expect(hunk.oldStart).toBe(1)
    expect(hunk.newStart).toBe(1)
    expect(hunk.oldLines).toBe(5)
    expect(hunk.newLines).toBe(5)
  })

  it('纯新增一行：oldLines 为 0，仍给出可寻址的 oldStart', () => {
    const diff = lineDiff('甲\n乙', '甲\n乙\n丙', 3)
    expect(shape(diff.hunks)).toEqual([[' 甲', ' 乙', '+丙']])
    expect(diff.hunks[0]?.oldLines).toBe(2)
    expect(diff.hunks[0]?.newLines).toBe(3)
  })

  it('首尾相同的长文只产出一个窄 hunk（剪公共前后缀生效）', () => {
    const lines = Array.from({ length: 200 }, (_, i) => `第${i}行`)
    const before = lines.join('\n')
    const changed = [...lines]
    changed[100] = '第100行（改）'
    const diff = lineDiff(before, changed.join('\n'))
    expect(diff.hunks).toHaveLength(1)
    expect(diff.hunks[0]?.lines).toHaveLength(8) // 3 上下文 + 1 删 + 1 增 + 3 上下文
    expect(diff.hunks[0]?.oldStart).toBe(98) // 第 97..99 行是上下文，第 100 行起是改动
  })

  it('两处相隔很远的改动 → 两个 hunk（上下文不重叠就不合并）', () => {
    const lines = Array.from({ length: 40 }, (_, i) => `第${i}行`)
    const changed = [...lines]
    changed[2] = 'A'
    changed[30] = 'B'
    const diff = lineDiff(lines.join('\n'), changed.join('\n'), 1)
    expect(diff.hunks).toHaveLength(2)
  })

  it('空原文（新建/整篇写入）→ 全是新增', () => {
    const diff = lineDiff('', '甲\n乙')
    expect(shape(diff.hunks)).toEqual([['+甲', '+乙']])
    expect(diff.hunks[0]?.oldLines).toBe(0)
    expect(diff.hunks[0]?.newLines).toBe(2)
  })

  it('整篇清空 → 全是删除', () => {
    const diff = lineDiff('甲\n乙', '')
    expect(shape(diff.hunks)).toEqual([['-甲', '-乙']])
    expect(diff.hunks[0]?.newLines).toBe(0)
  })

  it('超预算不猜：退化成整篇替换并标记 truncated', () => {
    const before = Array.from({ length: 900 }, (_, i) => `a${i}`).join('\n')
    const after = Array.from({ length: 900 }, (_, i) => `b${i}`).join('\n')
    const diff = lineDiff(before, after)
    expect(diff.truncated).toBe(true)
    expect(diff.hunks).toHaveLength(1)
    expect(diff.hunks[0]?.oldLines).toBe(900)
    expect(diff.hunks[0]?.newLines).toBe(900)
  })

  it('末尾换行不产生一行假改动', () => {
    expect(lineDiff('甲\n乙\n', '甲\n乙').hunks).toEqual([])
  })
})

describe('hunkRows', () => {
  it('上下文两侧计数，删除只走旧侧，新增只走新侧', () => {
    const [hunk] = lineDiff('甲\n乙\n丙', '甲\n丙').hunks
    if (!hunk) throw new Error('应当产出 1 个 hunk')
    expect(hunkRows(hunk)).toEqual([
      { kind: 'context', old: 1, new: 1, text: '甲' },
      { kind: 'del', old: 2, text: '乙' },
      { kind: 'context', old: 3, new: 2, text: '丙' },
    ])
  })
})

describe('foldRows', () => {
  const rows = Array.from({ length: 10 }, (_, i) => ({ kind: 'context' as const, old: i, new: i, text: `${i}` }))

  it('未超预算原样返回', () => {
    expect(foldRows(rows, 16)).toEqual({ rows, hidden: 0 })
  })

  it('超预算留头尾（关键信息常在被替换段两端）', () => {
    const folded = foldRows(rows, 4)
    expect(folded.hidden).toBe(6)
    expect(folded.rows.map((r) => r.text)).toEqual(['0', '1', '8', '9'])
  })

  it('maxLines 为 0 时不折叠（调用方关了折叠）', () => {
    expect(foldRows(rows, 0)).toEqual({ rows, hidden: 0 })
  })
})
