import { describe, expect, it } from 'vitest'

import { diffSegments, normalizeForDiff } from './text-diff'

describe('normalizeForDiff', () => {
  it('全半角标点折成一致（与后端 _PUNCT_MAP 同口径）', () => {
    expect(normalizeForDiff('客户姓名：曾某某')).toBe(normalizeForDiff('客户姓名: 曾某某'))
  })

  it('剥掉字面量 \\n（PaddleOCR-VL 把换行写成转义序列）', () => {
    expect(normalizeForDiff('逾期本金:\\n654.52元')).toBe(normalizeForDiff('逾期本金: 654.52元'))
  })

  it('剥掉 Markdown 标记、HTML 标签、LaTeX 命令', () => {
    expect(normalizeForDiff('# 标题')).toBe(normalizeForDiff('标题'))
    expect(normalizeForDiff('<td>正文</td>')).toBe(normalizeForDiff('正文'))
    expect(normalizeForDiff('$ \\underline{\\text{曾某某}} $')).toBe(normalizeForDiff('曾某某'))
  })
})

describe('diffSegments', () => {
  it('纯全半角标点差异不标红（否则一屏冒号高亮，真错字被淹）', () => {
    const a = '客户姓名:张甲某 客户编号:0115635142920608'
    const b = '客户姓名：张甲某 客户编号：0115635142920608'
    const segs = diffSegments(a, b)
    expect(segs.every((s) => !s.changed)).toBe(true)
  })

  it('字面量 \\n 差异不标红', () => {
    const segs = diffSegments('逾期本金:\\n654.52元', '逾期本金: 654.52元')
    expect(segs.every((s) => !s.changed)).toBe(true)
  })

  it('真错字要标出来，且只标那几个字', () => {
    const a = '截止至2023年02月02日, 张甲某贷款余额1208378.18元'
    const b = '截止至2023年02月02日, 张乙某贷款余额1208378.18元'
    const changed = diffSegments(a, b).filter((s) => s.changed)
    expect(changed.length).toBeGreaterThan(0)
    const text = changed.map((s) => s.text).join('')
    expect(text).toContain('甲')
    // 不含大段正文——只标差异字
    expect(text.length).toBeLessThan(5)
  })

  it('两侧一致时整段返回未变', () => {
    const segs = diffSegments('完全相同的一行', '完全相同的一行')
    expect(segs).toHaveLength(1)
    expect(segs[0]!.changed).toBe(false)
  })

  it('片段按序拼接即为原文（不漏字、不改序）', () => {
    const a = '甲乙丙丁戊'
    const b = '甲乙X丁戊'
    const segs = diffSegments(a, b)
    expect(segs.map((s) => s.text).join('')).toBe(a)
  })

  it('空文本不抛，返回空或未变', () => {
    expect(diffSegments('', 'x')).toEqual([])
    expect(diffSegments('x', '')).toEqual([{ text: 'x', changed: false }])
  })

  it('一侧归一化后为空（整行都是标记）不制造假高亮', () => {
    const segs = diffSegments('| --- |', '正文')
    expect(segs.every((s) => !s.changed)).toBe(true)
  })
})
