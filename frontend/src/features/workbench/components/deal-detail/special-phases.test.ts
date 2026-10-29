import { describe, expect, it } from 'vitest'

import { buildDeliverables, buildPhases } from './special-phases'
import { nextVersion, splitVersion } from './special-term'

describe('splitVersion：文件名 → 文书名 + 版本', () => {
  it('吃掉结尾的 v 版本串，书名号保留在名称里', () => {
    expect(splitVersion('《股东协议》v2.docx')).toEqual({ name: '《股东协议》', version: 'v2' })
    expect(splitVersion('《公司章程（草案）》V3.pdf')).toEqual({ name: '《公司章程（草案）》', version: 'v3' })
  })

  it('中文「第N版 / 第N稿」归一成 vN', () => {
    expect(splitVersion('尽调报告 第2版.docx')).toEqual({ name: '尽调报告', version: 'v2' })
    expect(splitVersion('尽调报告（第1稿）.pdf').version).toBeUndefined()
    expect(splitVersion('尽调报告—第1稿.pdf')).toEqual({ name: '尽调报告', version: 'v1' })
  })

  it('没有版本串时原样返回（正文里的 v 不动）', () => {
    expect(splitVersion('社保合规')).toEqual({ name: '社保合规' })
    expect(splitVersion('Value 报告.docx')).toEqual({ name: 'Value 报告' })
  })

  it('纯版本文件名不吞成空名', () => {
    expect(splitVersion('v1.docx').name).toBe('v1')
  })
})

describe('nextVersion：同名文书的下一个版本号', () => {
  it('取最大值 +1', () => {
    expect(nextVersion(['《股东协议》v1.docx', '《股东协议》v2.docx'])).toBe('v3')
  })

  it('空集合从 v1 起', () => {
    expect(nextVersion([])).toBe('v1')
    expect(nextVersion(['无关.txt'])).toBe('v1')
  })
})

describe('buildPhases：根层目录 → 阶段行', () => {
  const roots = [
    { name: '1-合同发票', subpath: '1-合同发票', file_count: 12 },
    { name: '1-尽职调查', subpath: '1-尽职调查', file_count: 2 },
    { name: '2-方案设计', subpath: '2-方案设计', file_count: 2 },
    { name: '3-文件起草', subpath: '3-文件起草', file_count: 1 },
    { name: '4-设立登记', subpath: '4-设立登记', file_count: 0 },
    { name: '5-交割与移交', subpath: '5-交割与移交', file_count: 0 },
  ]

  it('档案目录（发票/邮寄…）不入阶段，其余按序号排序', () => {
    const phases = buildPhases(roots)
    expect(phases.map((p) => p.name)).toEqual(['尽职调查', '方案设计', '文件起草', '设立登记', '交割与移交'])
  })

  it('有文件=已完成；第一个空目录=进行中；其后=未开始', () => {
    expect(buildPhases(roots).map((p) => p.state)).toEqual(['ok', 'ok', 'ok', 'doing', 'todo'])
  })

  it('日期前缀只作阶段开始日，不进名称', () => {
    const phases = buildPhases([{ name: '1-2026.06.05-尽职调查', subpath: 'd', file_count: 1 }])
    expect(phases[0]).toMatchObject({ name: '尽职调查', startDate: '2026-06-05', state: 'ok' })
  })

  it('纯日期目录不是阶段（那是事项，归服务事项流）', () => {
    expect(buildPhases([{ name: '2026.06.05', subpath: 'x', file_count: 3 }])).toEqual([])
  })

  it('没有可识别的阶段目录时返回空数组，由页面给空态', () => {
    expect(buildPhases([{ name: '1-合同发票', subpath: 'a', file_count: 1 }])).toEqual([])
    expect(buildPhases([])).toEqual([])
  })
})

describe('buildDeliverables：阶段目录里的文件 → 交付物行', () => {
  it('docx 视为撰写中、pdf 视为定稿，并按文书名聚合多版本', () => {
    const rows = buildDeliverables([
      { name: '《股东协议》v1.docx', subpath: 'p/《股东协议》v1.docx', modified_at: '2026-10-03T10:00:00Z' },
      { name: '《公司章程（草案）》.pdf', subpath: 'p/a.pdf', modified_at: '2026-09-20T10:00:00Z' },
      { name: '.DS_Store', subpath: 'p/.DS_Store' },
    ])
    expect(rows.map((r) => [r.name, r.version, r.state, r.date])).toEqual([
      ['《公司章程（草案）》', undefined, 'ok', '2026-09-20'],
      ['《股东协议》', 'v1', 'doing', '2026-10-03'],
    ])
  })
})
