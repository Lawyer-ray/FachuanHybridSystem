/**
 * 页级识别质量（`draft/page-quality.ts`）的单测。
 *
 * 锁的是契约里最容易写错的那几条：
 * - 收窄只认有限数字，脏条目丢而不是整体强转；
 * - 草稿里按**源**（`mi`）分槽存：多份 PDF 的页号各自从 1 开始，只拿页号跨源比对
 *   会把「A 份的 P5 取字失败」贴到 B 份的 P5 上（给错页比不提示更糟）；
 * - 派生一律按 `ref.mi` 查对应源再判 `ref.p`，跨源合并段**逐条**判定；
 * - `null` 落草稿时只清该源那一槽，最后一槽清空则整个键消失（回到旧草稿口径）。
 */
import { describe, expect, it } from 'vitest'

import { adoptLegacyPageQuality, withPageQuality } from './state'
import type { PageQuality, PageQualityByMi, Segment } from '../types'

import {
  docHintPagesOf,
  docTodosOf,
  graphicPagesOf,
  ocrFailedPagesOf,
  qualityOf,
  readPageQuality,
  sparsePagesOf,
} from './page-quality'

function seg(refs: [number, number][]): Pick<Segment, 'refs'> {
  return { refs: refs.map(([mi, p]) => ({ mi, p })) }
}

/** 一份识别结果按源（素材下标 `mi`）装进槽里 */
function byMi(mi: number, quality: PageQuality): PageQualityByMi {
  return { [String(mi)]: quality }
}

describe('qualityOf：按源取槽', () => {
  const by = { '0': { graphic_pages: [5] }, '2': { sparse_pages: [7] } }

  it('取对应源那一槽', () => {
    expect(qualityOf(by, 0)).toEqual({ graphic_pages: [5] })
    expect(qualityOf(by, 2)).toEqual({ sparse_pages: [7] })
  })

  it('没有这一槽 / 整份缺省 → null（旧草稿与「这份没跑到」同一口径）', () => {
    expect(qualityOf(by, 1)).toBeNull()
    expect(qualityOf(null, 0)).toBeNull()
    expect(qualityOf(undefined, 0)).toBeNull()
  })
})

describe('graphicPagesOf / sparsePagesOf', () => {
  const quality = readPageQuality({ graphic_pages: [2, 147, 148], sparse_pages: [149], blank_pages: [] })!

  it('按段内页序返回覆盖到的页', () => {
    expect(graphicPagesOf(seg([[0, 1], [0, 2], [0, 3]]), byMi(0, quality))).toEqual([2])
  })

  it('跨源重复页号按位置保留：两个源都有 P147 时跳转需要两条都在', () => {
    expect(graphicPagesOf(seg([[0, 147], [1, 147]]), { '0': quality, '1': quality })).toEqual([147, 147])
  })

  it('没有质量数据 / seg 为空时返回空数组', () => {
    expect(graphicPagesOf(seg([[0, 1]]), null)).toEqual([])
    expect(graphicPagesOf(null, byMi(0, quality))).toEqual([])
    expect(sparsePagesOf(seg([[0, 1]]), byMi(0, quality))).toEqual([])
  })

  it('稀疏页单独取（图上的几个字 / 拍糊的一页）', () => {
    expect(sparsePagesOf(seg([[0, 149]]), byMi(0, quality))).toEqual([149])
  })
})

describe('ocrFailedPagesOf：取字失败的页必须能被单独告警', () => {
  // 回归 2026-11-25 材料包 617 的 p12：整页关键事实因为「一个字都没读到」
  // 被判成 blank，界面上只有一句「空白页」——律师会以为原件本来就没字。
  const quality = readPageQuality({ ocr_failed_pages: [12, 34], blank_pages: [7] })

  it('只有 ocr_failed_pages 也算「有质量数据」，不能返回 null', () => {
    expect(quality).not.toBeNull()
    expect(readPageQuality({ ocr_failed_pages: [12] })).not.toBeNull()
  })

  it('按段内页序返回覆盖到的失败页', () => {
    const by = byMi(0, quality!)
    expect(ocrFailedPagesOf(seg([[0, 11], [0, 12], [0, 13]]), by)).toEqual([12])
    expect(ocrFailedPagesOf(seg([[0, 12], [1, 12]]), { '0': quality!, '1': quality! })).toEqual([12, 12])
  })

  it('空白页不算取字失败（两者必须分开）', () => {
    expect(ocrFailedPagesOf(seg([[0, 7]]), byMi(0, quality!))).toEqual([])
  })

  it('没有质量数据 / seg 为空时返回空数组', () => {
    expect(ocrFailedPagesOf(seg([[0, 12]]), null)).toEqual([])
    expect(ocrFailedPagesOf(null, byMi(0, quality!))).toEqual([])
  })
})

describe('docHintPagesOf', () => {
  const quality = readPageQuality({
    doc_hints: { '23': 'id_card', '144': 'property_cert' },
    doc_missing: { '23': { doc: 'id_card', missing: ['姓名', '身份证号'] } },
  })!

  it('按段内页序返回覆盖到的证件页，并带上该页缺失字段', () => {
    expect(docHintPagesOf(seg([[0, 22], [0, 23], [0, 144]]), byMi(0, quality))).toEqual([
      // p23 有缺失字段：调用方据此分档提示
      { mi: 0, page: 23, doc: 'id_card', missing: ['姓名', '身份证号'] },
      // p144 没进 doc_missing：missing 给空数组，不臆造
      { mi: 0, page: 144, doc: 'property_cert', missing: [] },
    ])
    // 跨源重复页号按位置保留两次，每条带着它自己那一份的 mi
    expect(docHintPagesOf(seg([[0, 23], [1, 23]]), { '0': quality, '1': quality })).toEqual([
      { mi: 0, page: 23, doc: 'id_card', missing: ['姓名', '身份证号'] },
      { mi: 1, page: 23, doc: 'id_card', missing: ['姓名', '身份证号'] },
    ])
  })

  it('没有证件数据 / seg 为空时返回空数组', () => {
    expect(docHintPagesOf(seg([[0, 23]]), null)).toEqual([])
    expect(docHintPagesOf(null, byMi(0, quality))).toEqual([])
    // 只有图纸页数据（旧任务）时也返回空
    expect(docHintPagesOf(seg([[0, 147]]), byMi(0, readPageQuality({ graphic_pages: [147] })!))).toEqual([])
  })
})

describe('docTodosOf', () => {
  const quality = readPageQuality({
    doc_hints: { '23': 'id_card', '42': 'id_card', '144': 'property_cert', '8': 'license' },
    doc_missing: {
      '23': { doc: 'id_card', missing: ['姓名', '身份证号', '住址'] },
      // 字段都在但内容可疑（乱码 / 拍糊）：missing 为空数组，但仍要进清单
      '42': { doc: 'id_card', missing: [] },
      '144': { doc: 'property_cert', missing: ['权证号'] },
      // '8' 有 doc_hint 但不在 doc_missing 里（识别得干净）→ 不进清单
    },
  })!

  it('按缺失字段数量降序，数量相同按页号', () => {
    expect(docTodosOf(byMi(0, quality)).map((t) => t.page)).toEqual([23, 144, 42])
  })

  it('每条带页号、证件中文名、缺的字段', () => {
    const [first, second, third] = docTodosOf(byMi(0, quality))
    expect(first).toMatchObject({ page: 23, doc: 'id_card', label: '身份证', missing: ['姓名', '身份证号', '住址'] })
    expect(second).toMatchObject({ page: 144, label: '不动产权证', missing: ['权证号'] })
    // 字段都在但内容可疑的页仍然进清单，只是 missing 为空数组
    expect(third).toMatchObject({ page: 42, missing: [] })
  })

  it('不在 doc_missing 里的证件页不进清单（识别干净，律师无需补录）', () => {
    expect(docTodosOf(byMi(0, quality)).some((t) => t.page === 8)).toBe(false)
  })

  it('doc_missing 带了类型而 doc_hints 没说时，用 doc_missing 的类型', () => {
    const q = readPageQuality({ doc_missing: { '5': { doc: 'household', missing: ['姓名'] } } })!
    expect(docTodosOf(byMi(0, q))[0]).toMatchObject({ page: 5, label: '户口簿' })
  })

  it('类型完全缺失时按「证件页」兜底，不渲染空标签', () => {
    const q = readPageQuality({ doc_missing: { '5': { missing: ['姓名'] } } })!
    expect(docTodosOf(byMi(0, q))[0]).toMatchObject({ page: 5, doc: '', label: '证件页' })
  })

  it('旧任务没有数据时返回空清单', () => {
    expect(docTodosOf(null)).toEqual([])
    expect(docTodosOf(byMi(0, readPageQuality({ graphic_pages: [147] })!))).toEqual([])
  })

  /**
   * 多份 PDF 各自从 1 开始编页，所以清单里的键必须是 `${mi}:${page}`：
   * 只按页号去重会把「A 份的 P5」和「B 份的 P5」合并成一条（另一份的缺字段就消失）。
   */
  it('多份的证件页各自成条，每条带 mi', () => {
    const by = {
      '0': readPageQuality({
        doc_hints: { '5': 'id_card' },
        doc_missing: { '5': { doc: 'id_card', missing: ['姓名'] } },
      })!,
      '1': readPageQuality({
        doc_hints: { '5': 'license' },
        doc_missing: { '5': { doc: 'license', missing: [] } },
      })!,
    }
    expect(docTodosOf(by).map((t) => `${t.mi}:${t.page}`)).toEqual(['0:5', '1:5'])
  })
})

/**
 * 跨源不串号：A 份 P5 有信号、B 份 P5 一切正常（所以 B 在草稿里根本没有槽）。
 * 这是 `pageQualityByMi` 存在的唯一理由——旧单值实现下 A 的 P5 会显示到 B 的 P5 上。
 */
describe('跨源不串号', () => {
  const by: PageQualityByMi = byMi(
    0,
    readPageQuality({ ocr_failed_pages: [5], graphic_pages: [5], sparse_pages: [5] })!,
  )

  it('B 份的 P5 一条提示都不出（取字失败 / 图纸 / 稀疏都不串过来）', () => {
    expect(ocrFailedPagesOf(seg([[1, 5]]), by)).toEqual([])
    expect(graphicPagesOf(seg([[1, 5]]), by)).toEqual([])
    expect(sparsePagesOf(seg([[1, 5]]), by)).toEqual([])
  })

  it('A 份的 P5 仍然是信号（不是把整块提示关掉）', () => {
    expect(ocrFailedPagesOf(seg([[0, 5]]), by)).toEqual([5])
    expect(graphicPagesOf(seg([[0, 5]]), by)).toEqual([5])
  })

  it('跨源合并段按 ref 逐条判定：只有 A 那一条命中（不取第一个 ref 的 mi）', () => {
    expect(ocrFailedPagesOf(seg([[0, 5], [1, 5]]), by)).toEqual([5])
    expect(graphicPagesOf(seg([[0, 5], [1, 5]]), by)).toEqual([5])
    // 顺序反过来结果不变：判定跟着 ref 走，不跟着位置走
    expect(ocrFailedPagesOf(seg([[1, 5], [0, 5]]), by)).toEqual([5])
  })

  it('证件页同理：A 份的证件页提示不出现在 B 份的同号页上', () => {
    const docs = byMi(
      0,
      readPageQuality({
        doc_hints: { '5': 'id_card' },
        doc_missing: { '5': { doc: 'id_card', missing: ['姓名'] } },
      })!,
    )
    expect(docHintPagesOf(seg([[1, 5]]), docs)).toEqual([])
    expect(docHintPagesOf(seg([[0, 5]]), docs)).toEqual([
      { mi: 0, page: 5, doc: 'id_card', missing: ['姓名'] },
    ])
  })
})

describe('withPageQuality：按源落草稿，null 只清该槽', () => {
  const empty = { mats: [], segs: [], infos: [] }
  const a5: PageQuality = { ocr_failed_pages: [5] }
  const b5: PageQuality = { graphic_pages: [5] }

  it('按 mi 分槽写入', () => {
    const d = withPageQuality(withPageQuality(empty, 0, a5), 1, b5)
    expect(d.pageQualityByMi).toEqual({ '0': a5, '1': b5 })
  })

  it('**多份各自保留**：后一份不再整键覆盖前一份（回写后两个槽都在）', () => {
    const d = withPageQuality(withPageQuality(empty, 0, a5), 1, b5)
    expect(d.pageQualityByMi?.['0']).toEqual(a5)
    expect(d.pageQualityByMi?.['1']).toEqual(b5)
  })

  it('重跑某一份且本次没信号（null）→ 只删那一槽，别的源原样', () => {
    const d = withPageQuality(withPageQuality(empty, 0, a5), 1, b5)
    const next = withPageQuality(d, 0, null)
    expect(next.pageQualityByMi).toEqual({ '1': b5 })
    expect(next.mats).toEqual([])
  })

  it('null 且没有旧键 → 返回原引用（不制造无意义的新对象）', () => {
    expect(withPageQuality(empty, 0, null)).toBe(empty)
  })

  it('最后一槽也被清掉 → 整个键消失（回到「与引入前逐位一致」）', () => {
    const cleared = withPageQuality(withPageQuality(empty, 0, a5), 0, null)
    expect(cleared.pageQualityByMi).toBeUndefined()
    expect('pageQualityByMi' in cleared).toBe(false)
  })
})

/**
 * 页级质量必须能落库（v27.16.8 修正）。
 *
 * 原先 `DraftStateToSave = Omit<DraftState, 'pageQuality'>`，理由是「落盘后会和
 * 律师后来的切段错位」。但那个担心代码里已经天然解决——`graphicPagesOf` 是拿
 * `seg.refs` 与 `byMi.*_pages` **实时求交集**，段变了提示跟着变。
 * 而不落库的代价很实在：**刷新一次提示就没了**，得重新点「自动识别」才看得到，
 * 而这个功能的意义恰恰是「打开就知道哪页要核对」。
 */
describe('pageQuality 持久化契约', () => {
  it('withPageQuality 产出的槽经过 JSON 往返后完整保留', () => {
    const quality: PageQuality = {
      graphic_pages: [147, 148],
      sparse_pages: [23],
      blank_pages: [],
      details: { '147': '疑似图形页' },
      doc_hints: { '23': 'id_card' },
      doc_missing: { '23': { doc: 'id_card', missing: ['姓名', '身份证号'] } },
    }
    const draft = withPageQuality({ mats: [], segs: [], infos: [] } as never, 1, quality)
    const roundTripped = JSON.parse(JSON.stringify(draft)) as { pageQualityByMi?: PageQualityByMi }

    expect(roundTripped.pageQualityByMi).toEqual({ '1': quality })
  })

  it('切段后图形页标记跟着段走（证明持久化不会产生错位假提示）', () => {
    const by = byMi(0, { graphic_pages: [147, 148] })
    // 原段覆盖 144-150，含两页图形页
    const wide = { refs: [144, 145, 146, 147, 148, 149, 150].map((p) => ({ mi: 0, p })) }
    // 拆一刀：只剩 144-146，图形页被划到另一段
    const narrow = { refs: [144, 145, 146].map((p) => ({ mi: 0, p })) }

    expect(graphicPagesOf(wide, by)).toEqual([147, 148])
    expect(graphicPagesOf(narrow, by)).toEqual([])
  })
})

describe('adoptLegacyPageQuality：存量草稿的单值 pageQuality', () => {
  const legacy = { ocr_failed_pages: [5], graphic_pages: [7] }

  it('单源草稿：归到那个源（老包打开后提示不消失）', () => {
    const d = { mats: [], segs: [{ refs: [{ mi: 3, p: 5 }] }], infos: [], pageQuality: legacy } as never
    const out = adoptLegacyPageQuality(d)
    expect(out.pageQualityByMi).toEqual({ '3': legacy })
    expect('pageQuality' in out).toBe(false)
  })

  it('没有任何引用的空草稿：归到 0', () => {
    const d = { mats: [], segs: [], infos: [], pageQuality: legacy } as never
    expect(adoptLegacyPageQuality(d).pageQualityByMi).toEqual({ '0': legacy })
  })

  it('**多源**草稿：无法判断归属，丢弃（错配到别的源比不显示更糟）', () => {
    const d = {
      mats: [],
      segs: [{ refs: [{ mi: 0, p: 5 }] }, { refs: [{ mi: 1, p: 5 }] }],
      infos: [],
      pageQuality: legacy,
    } as never
    const out = adoptLegacyPageQuality(d)
    expect(out.pageQualityByMi).toBeUndefined()
    expect('pageQuality' in out).toBe(false)
  })

  it('新形状优先：已有 pageQualityByMi 时不再看旧键', () => {
    const fresh = { ocr_failed_pages: [9] }
    const d = {
      mats: [],
      segs: [{ refs: [{ mi: 3, p: 5 }] }],
      infos: [],
      pageQuality: legacy,
      pageQualityByMi: { '3': fresh },
    } as never
    expect(adoptLegacyPageQuality(d).pageQualityByMi).toEqual({ '3': fresh })
  })

  it('没有旧键时返回原引用（不制造无意义的新对象）', () => {
    const d = { mats: [], segs: [], infos: [] } as never
    expect(adoptLegacyPageQuality(d)).toBe(d)
  })
})
