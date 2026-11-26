/**
 * 页级识别风险（退化页 / 表格列数突变）的单测。
 *
 * 锁的是契约里那几条最容易写错的事：
 * - 两个键**跨层**：`degenerate_pages` 在 summary 顶层，`column_anomalies` 在
 *   `summary.table_geometry` 里（同一块还带 `enabled` 开关与零值键）；
 * - 旧任务的 summary 整块缺键 → `null`（调用方整块不渲染，与引入前逐位一致）；
 * - 收窄只认有限数字，脏条目丢而不是整体强转；
 * - 落草稿时 `null` 要**清旧键**（重跑后留着上一次的退化页号是假信息）。
 */
import { describe, expect, it } from 'vitest'

import { withPageAnomaly } from './state'
import type { ColumnAnomaly, PageAnomaly, Segment } from '../types'

import {
  columnAnomaliesOf,
  columnAnomalyOf,
  columnAnomalyPagesOf,
  degeneratePagesOf,
  readPageAnomaly,
  riskPageKeysOf,
} from './page-anomaly'

function seg(refs: [number, number][]): Pick<Segment, 'refs'> {
  return { refs: refs.map(([mi, p]) => ({ mi, p })) }
}

describe('readPageAnomaly：跨层读取与空值判定', () => {
  it('缺键 / 非对象 / 空对象一律 null（旧任务就是这样）', () => {
    expect(readPageAnomaly(undefined)).toBeNull()
    expect(readPageAnomaly(null)).toBeNull()
    expect(readPageAnomaly('oops')).toBeNull()
    expect(readPageAnomaly({})).toBeNull()
  })

  it('旧任务：summary 里有别的键、但没有这两个键 → null（一个字都不该加）', () => {
    const summary = { page_quality: { ocr_failed_pages: [12] }, inconsistencies: [{ canonical: '甲' }] }
    expect(readPageAnomaly(summary)).toBeNull()
  })

  it('读出顶层 degenerate_pages', () => {
    const a = readPageAnomaly({ degenerate_pages: [12, 34] })
    expect(a?.degenerate_pages).toEqual([12, 34])
    expect(a?.column_anomalies).toEqual([])
  })

  it('读出 summary.table_geometry 里的 column_anomalies（跨层，不是顶层）', () => {
    const a = readPageAnomaly({
      table_geometry: {
        enabled: true,
        column_anomaly_pages: [7],
        column_anomalies: [{ page_no: 7, prev_page_no: 6, cols: 5, prev_cols: 4 }],
      },
    })
    expect(a?.column_anomalies).toEqual([{ page_no: 7, prev_page_no: 6, cols: 5, prev_cols: 4 }])
    expect(a?.degenerate_pages).toEqual([])
  })

  it('顶层同名键不算数（只在 table_geometry 下读列数异常）', () => {
    expect(readPageAnomaly({ column_anomalies: [{ page_no: 7, prev_page_no: 6, cols: 5, prev_cols: 4 }] })).toBeNull()
  })

  it('表格几何关掉时零值键仍在 → 两者都空 → null（不渲染空提示）', () => {
    expect(
      readPageAnomaly({
        degenerate_pages: [],
        table_geometry: { enabled: false, column_anomalies: [], column_anomaly_pages: [] },
      }),
    ).toBeNull()
  })

  it('table_geometry 不是对象 / 缺 column_anomalies 时不炸，只看顶层', () => {
    expect(readPageAnomaly({ table_geometry: 'oops', degenerate_pages: [3] })?.degenerate_pages).toEqual([3])
    expect(readPageAnomaly({ table_geometry: { enabled: true }, degenerate_pages: [3] })?.column_anomalies).toEqual([])
  })

  it('数字列表只收有限数字：字符串 / NaN / Infinity / null 全丢', () => {
    const a = readPageAnomaly({ degenerate_pages: [12, '34', Number.NaN, Number.POSITIVE_INFINITY, null, 56] })
    expect(a?.degenerate_pages).toEqual([12, 56])
  })

  it('degenerate_pages 全脏 → 等同没有，仍返回 null', () => {
    expect(readPageAnomaly({ degenerate_pages: ['12', Number.NaN] })).toBeNull()
  })

  it('列数异常逐条校验：四字段缺一个 / 非数字即丢，其余照收', () => {
    const a = readPageAnomaly({
      table_geometry: {
        column_anomalies: [
          { page_no: 7, prev_page_no: 6, cols: 5, prev_cols: 4 },
          { page_no: 8, prev_page_no: 7, cols: 5 },
          { page_no: '9', prev_page_no: 8, cols: 5, prev_cols: 4 },
          { page_no: 10, prev_page_no: 9, cols: Number.NaN, prev_cols: 4 },
          null,
          'oops',
        ],
      },
    })
    expect(a?.column_anomalies).toEqual([{ page_no: 7, prev_page_no: 6, cols: 5, prev_cols: 4 }])
  })

  it('column_anomalies 不是数组 → 空列表', () => {
    expect(readPageAnomaly({ table_geometry: { column_anomalies: 'oops' }, degenerate_pages: [1] })?.column_anomalies).toEqual(
      [],
    )
  })
})

/** 一份 summary → 按源存成 `PageAnomalyByMi`（`readPageAnomaly` 仍返回单份结果） */
function byMi(mi: number, summary: unknown) {
  const a = readPageAnomaly(summary)
  return a ? { [String(mi)]: a } : null
}

describe('degeneratePagesOf / columnAnomalyPagesOf：按段内页序取交集', () => {
  const anomaly = byMi(0, {
    degenerate_pages: [12],
    table_geometry: { column_anomalies: [{ page_no: 7, prev_page_no: 6, cols: 5, prev_cols: 4 }] },
  })

  it('退化页：只留本段覆盖的，按 seg.refs 顺序', () => {
    expect(degeneratePagesOf(seg([[0, 5], [0, 12], [0, 13]]), anomaly)).toEqual([12])
  })

  it('列数异常页：同口径', () => {
    expect(columnAnomalyPagesOf(seg([[0, 6], [0, 7], [0, 8]]), anomaly)).toEqual([7])
  })

  it('同一源合并段的重复页号保留两次（跳转要的是「段里那一页」）', () => {
    expect(degeneratePagesOf(seg([[0, 12], [0, 12]]), anomaly)).toEqual([12, 12])
    expect(columnAnomalyPagesOf(seg([[0, 7], [0, 7]]), anomaly)).toEqual([7, 7])
  })

  it('**跨源不串号**：A 份的 P12 退化，不能到 B 份的 P12 上（多 PDF 包页号各自从 1 开始）', () => {
    expect(degeneratePagesOf(seg([[1, 12]]), anomaly)).toEqual([])
    expect(columnAnomalyPagesOf(seg([[1, 7]]), anomaly)).toEqual([])
    // 同一段里既引 A 又引 B：只认 A 那一页
    expect(degeneratePagesOf(seg([[0, 12], [1, 12]]), anomaly)).toEqual([12])
  })

  it('段为空 / 无信号 / 无命中 → 空数组', () => {
    expect(degeneratePagesOf(null, anomaly)).toEqual([])
    expect(degeneratePagesOf(undefined, anomaly)).toEqual([])
    expect(columnAnomalyPagesOf(null, anomaly)).toEqual([])
    expect(degeneratePagesOf(seg([[0, 1]]), null)).toEqual([])
    expect(columnAnomalyPagesOf(seg([[0, 1]]), null)).toEqual([])
    expect(degeneratePagesOf(seg([[0, 1]]), {})).toEqual([])
    expect(columnAnomalyPagesOf(seg([[0, 1]]), { '0': { column_anomalies: [] } })).toEqual([])
  })
})

describe('columnAnomaliesOf / columnAnomalyOf：带出「几列 vs 邻页几列」', () => {
  const anomaly = byMi(0, {
    table_geometry: {
      column_anomalies: [
        { page_no: 7, prev_page_no: 6, cols: 5, prev_cols: 4 },
        { page_no: 20, prev_page_no: 19, cols: 3, prev_cols: 4 },
      ],
    },
  })

  it('段内按页序带出每一条详情', () => {
    expect(columnAnomaliesOf(seg([[0, 20], [0, 7]]), anomaly)).toEqual<ColumnAnomaly[]>([
      { page_no: 20, prev_page_no: 19, cols: 3, prev_cols: 4 },
      { page_no: 7, prev_page_no: 6, cols: 5, prev_cols: 4 },
    ])
  })

  it('单页查询命中 / 没命中 / 空信号 → null', () => {
    expect(columnAnomalyOf(anomaly, 0, 20)).toEqual<ColumnAnomaly>({
      page_no: 20,
      prev_page_no: 19,
      cols: 3,
      prev_cols: 4,
    })
    expect(columnAnomalyOf(anomaly, 0, 8)).toBeNull()
    expect(columnAnomalyOf(null, 0, 7)).toBeNull()
    expect(columnAnomalyOf({}, 0, 7)).toBeNull()
    // 页号对但源不对 → 不给（跨源串号就是这么来的）
    expect(columnAnomalyOf(anomaly, 1, 7)).toBeNull()
  })
})

describe('riskPageKeysOf：左栏卷级计数用的 `${mi}:${p}` 键', () => {
  const anomaly = byMi(0, {
    degenerate_pages: [3],
    table_geometry: { column_anomalies: [{ page_no: 3, prev_page_no: 2, cols: 5, prev_cols: 4 }] },
  })

  it('同页两类信号各记一个键，交给调用方去重', () => {
    const keys = riskPageKeysOf(seg([[0, 3]]), anomaly)
    expect([...keys.degenerate]).toEqual(['0:3'])
    expect([...keys.column]).toEqual(['0:3'])
    expect(new Set([...keys.degenerate, ...keys.column]).size).toBe(1)
  })

  it('不同源的同号页是两个键（不能被合并成一页）', () => {
    const two = { ...anomaly, '1': { degenerate_pages: [3] } }
    const keys = riskPageKeysOf(seg([[0, 3], [1, 3]]), two)
    expect(keys.degenerate.size).toBe(2)
  })

  it('空段 / 空信号 → 两个空集合', () => {
    expect(riskPageKeysOf(null, anomaly).degenerate.size).toBe(0)
    expect(riskPageKeysOf(seg([]), null).column.size).toBe(0)
  })
})

describe('withPageAnomaly：按源落草稿，null 时删该源那一槽', () => {
  const empty = { mats: [], segs: [], infos: [] }
  const a12: PageAnomaly = { degenerate_pages: [12] }
  const a3: PageAnomaly = { degenerate_pages: [3] }

  it('按 mi 分槽写入', () => {
    const d = withPageAnomaly(withPageAnomaly(empty, 0, a12), 1, a3)
    expect(d.pageAnomalyByMi).toEqual({ '0': a12, '1': a3 })
  })

  it('**多份 PDF 各自保留**：后一份不再覆盖前一份（这是按源存的唯一理由）', () => {
    const d = withPageAnomaly(withPageAnomaly(empty, 0, a12), 1, { degenerate_pages: [] })
    expect(d.pageAnomalyByMi?.['0']).toEqual(a12)
  })

  it('null 且没有旧键 → 返回原引用（不制造无意义的新对象）', () => {
    expect(withPageAnomaly(empty, 0, null)).toBe(empty)
  })

  it('null 且该源有旧值 → 只删这一槽，别的源原样保留', () => {
    const d = withPageAnomaly(withPageAnomaly(empty, 0, a12), 1, a3)
    const next = withPageAnomaly(d, 0, null)
    expect(next.pageAnomalyByMi).toEqual({ '1': a3 })
    expect(next.mats).toEqual([])
  })

  it('最后一槽也被清掉 → 整个键消失（回到「与引入前逐位一致」）', () => {
    const d = withPageAnomaly(empty, 0, a12)
    const cleared = withPageAnomaly(d, 0, null)
    expect(cleared.pageAnomalyByMi).toBeUndefined()
    expect('pageAnomalyByMi' in cleared).toBe(false)
  })
})
