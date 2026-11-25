/**
 * 草稿导出：段 → 请求 spec 的投影（node 环境）。
 *
 * 「没跑过自动分段的材料也要能导出」这条需求里，最容易错的是**这一层投影**：
 * 页区间取错会导出别的几页；旋转漏掉会导出歪的 PDF；跨源段硬塞一个页区间则
 * 会静默丢证据（A 素材的首页到末页，B 那几页消失）。服务端切页与打包另有
 * `tests/ci/unit/pdf_splitting/test_export_draft.py` 钉着。
 */
import { describe, expect, it } from 'vitest'

import type { BundleMat, Segment } from '../../types'
import { draftExportSpecs } from './use-segment-downloads'

const mats = [
  { partIndex: 0, n: 'a.pdf', k: 'pdf', pages: 6 },
  { partIndex: 7, n: 'b.pdf', k: 'pdf', pages: 4 },
] as unknown as BundleMat[]

function seg(over: Partial<Segment> & { id: string }): Segment {
  return { t: '', fn: '起诉状', refs: [{ mi: 0, p: 1 }], manual: true, ...over } as Segment
}

describe('draftExportSpecs', () => {
  it('取段名与页区间（首尾 refs），类型名优先于文件名', () => {
    const { specs } = draftExportSpecs(
      [seg({ id: 's1', t: '证据清单', fn: 'b.pdf', refs: [{ mi: 0, p: 2 }, { mi: 0, p: 4 }] })],
      mats,
    )
    expect(specs).toEqual([{ name: '证据清单', part_index: 0, page_start: 2, page_end: 4 }])
  })

  it('段名去掉扩展名（zip 里是 NN-名字.pdf，不能出现 NN-a.pdf.pdf）', () => {
    const { specs } = draftExportSpecs([seg({ id: 's1', t: '', fn: '借款合同.pdf' })], mats)
    expect(specs[0]?.name).toBe('借款合同')
  })

  it('素材下标换算成附件 partIndex（追加过附件后两者会漂）', () => {
    const { specs } = draftExportSpecs([seg({ id: 's1', refs: [{ mi: 1, p: 1 }, { mi: 1, p: 2 }] })], mats)
    expect(specs[0]?.part_index).toBe(7)
  })

  it('带页旋转（页码用源 PDF 绝对页号，且只含段内页）', () => {
    const { specs } = draftExportSpecs(
      [seg({ id: 's1', refs: [{ mi: 0, p: 2 }, { mi: 0, p: 3 }] })],
      mats,
      { '0:2': 90, '0:3': 90, '0:5': 180 },
    )
    expect(specs[0]?.rotations).toBe('2:90,3:90')
  })

  it('没有旋转时不带该字段（请求体与改动前一致）', () => {
    const { specs } = draftExportSpecs([seg({ id: 's1' })], mats, {})
    expect(specs[0]).not.toHaveProperty('rotations')
  })

  it('有 Markdown 才带上（人工切的段没有正文重建）', () => {
    const { specs } = draftExportSpecs(
      [seg({ id: 's1', md: '# 正文' }), seg({ id: 's2', md: '   ' })],
      mats,
    )
    expect(specs[0]?.md).toBe('# 正文')
    expect(specs[1]).not.toHaveProperty('md')
  })

  it('跨源段跳过并计数：一个页区间表达不了它，硬塞会静默丢证据', () => {
    const { specs, crossSource } = draftExportSpecs(
      [
        seg({ id: 'ok' }),
        seg({ id: 'cross', refs: [{ mi: 0, p: 5 }, { mi: 1, p: 1 }] }),
        seg({ id: 'empty', refs: [] }),
      ],
      mats,
    )
    expect(specs).toHaveLength(1)
    expect(crossSource).toBe(2)
  })

  it('素材不在了（删过附件）也算导不出来，不猜 partIndex', () => {
    const { specs, crossSource } = draftExportSpecs([seg({ id: 's1', refs: [{ mi: 9, p: 1 }] })], mats)
    expect(specs).toHaveLength(0)
    expect(crossSource).toBe(1)
  })
})
