/**
 * 收尾文案的「页级失败」语义。
 *
 * 只测一件事：**某一页没取到字时，收尾提示必须升级成 warning**。
 *
 * 为什么要单独立一条：`warned` 原来只由 `failedTotal`（整份任务失败数）决定，
 * 而页级失败时任务状态是成功的、分段也是成功的——正文里只是少了几页，
 * 律师看到的是一条绿色「已完成」。2026-11-25 一份真实卷宗里，某一页整案的核心
 * 事实（标的金额 + 生效刑事判决编号）就是这么静默消失的。
 */
import { describe, expect, it } from 'vitest'

import { summarizeAutoSplitResults } from './auto-split-apply'
import type { AutoSplitResult } from './auto-split-tracks'

function result(overrides: Partial<AutoSplitResult> = {}): AutoSplitResult {
  return {
    mi: 0,
    jobId: 'job-1',
    segments: [],
    segmentBackend: 'llm',
    pageQuality: null,
    // 退化页 / 列数突变页：旧任务同样没有这两个键（null = 整块不渲染、收尾提示不加字）
    pageAnomaly: null,
    inconsistencies: [],
    engineDisagreements: [],
    // 旧任务没有裁定总账：null = 整条提示不渲染（与引入前逐位一致）
    judgeState: null,
    ...overrides,
  }
}

const base = {
  pdfFailed: 0,
  photoTexts: [],
  officeTexts: [],
  photoFailed: 0,
  officeFailed: 0,
  detected: { our: '', their: '' },
}

describe('summarizeAutoSplitResults：页级取字失败要升级成 warning', () => {
  it('全绿时不给 warning', () => {
    const out = summarizeAutoSplitResults({ ...base, results: [result()] })
    expect(out.warned).toBe(false)
    expect(out.message).not.toContain('未取到任何文字')
  })

  it('有页没取到字 → warned，且文案点名「正文里没有这几页」', () => {
    const out = summarizeAutoSplitResults({
      ...base,
      results: [result({ pageQuality: { ocr_failed_pages: [12] } })],
    })
    expect(out.warned).toBe(true)
    expect(out.message).toContain('1 页未取到任何文字')
    expect(out.message).toContain('请核对原图补录')
  })

  it('多份材料跨任务累加页数', () => {
    const out = summarizeAutoSplitResults({
      ...base,
      results: [
        result({ pageQuality: { ocr_failed_pages: [12, 34] } }),
        result({ mi: 1, jobId: 'job-2', pageQuality: { ocr_failed_pages: [5] } }),
      ],
    })
    expect(out.message).toContain('3 页未取到任何文字')
  })

  it('空白页不算取字失败（blank_pages 不触发告警）', () => {
    const out = summarizeAutoSplitResults({
      ...base,
      results: [result({ pageQuality: { blank_pages: [7, 8] } })],
    })
    expect(out.warned).toBe(false)
    expect(out.message).not.toContain('未取到任何文字')
  })
})

describe('summarizeAutoSplitResults：分歧裁定的门禁结果必须说出来', () => {
  /**
   * 这条链以前断在最后一环：后端 v27.25.4 就把 `enabled` / `requested` /
   * `reason` 写进了 summary，前端一个都没读 → 律师看到「开关勾着、分歧全进人工」，
   * 界面不解释原因，只能归因成「坏了」。这里锁住三件事。
   */

  it('没生效 → 收尾提示说清是哪一项配置没配', () => {
    const out = summarizeAutoSplitResults({
      ...base,
      results: [
        result({
          judgeState: { requested: true, enabled: false, reason: 'missing_key', annotated: 0, accepted: 0, human: 0 },
        }),
      ],
    })
    expect(out.message).toContain('分歧自动裁定未生效')
    expect(out.message).toContain('OCR_JUDGE_API_KEY')
  })

  it('没生效**不升级**成 warning（不是失败；染黄会让页级取字失败那条真警告贬值）', () => {
    const out = summarizeAutoSplitResults({
      ...base,
      results: [
        result({
          judgeState: { requested: true, enabled: false, reason: 'gate_off', annotated: 0, accepted: 0, human: 0 },
        }),
      ],
    })
    expect(out.warned).toBe(false)
  })

  it('生效且裁过 → 报条数', () => {
    const out = summarizeAutoSplitResults({
      ...base,
      results: [
        result({
          judgeState: { requested: true, enabled: true, reason: 'enabled', annotated: 5, accepted: 2, human: 3 },
        }),
      ],
    })
    expect(out.message).toContain('已自动裁定 2 条分歧')
  })

  it('旧任务（judgeState 为 null）→ 一个字都不加（与引入前逐位一致）', () => {
    const out = summarizeAutoSplitResults({ ...base, results: [result()] })
    expect(out.message).not.toContain('裁定')
  })

  it('用户自己关的 → 不提示也不报「未生效」', () => {
    const out = summarizeAutoSplitResults({
      ...base,
      results: [
        result({
          judgeState: {
            requested: false,
            enabled: false,
            reason: 'not_requested',
            annotated: 0,
            accepted: 0,
            human: 0,
          },
        }),
      ],
    })
    expect(out.message).not.toContain('裁定')
  })
})

describe('summarizeAutoSplitResults：退化页 / 列数突变页要说出来但**不升级**警告', () => {
  /**
   * 这两类都是「任务成功、正文也有，但机器读出来的那一页本身可疑」：
   * 退化页已由本地 OCR 兜底，列数突变只影响数字表头的对位——都不是失败。
   * 染黄会稀释「页级未取到任何文字」那条真警告，所以 warned 必须保持 false。
   */

  it('有退化页 → 点名页数且说清已换识别路径，不升级 warned', () => {
    const out = summarizeAutoSplitResults({
      ...base,
      results: [result({ pageAnomaly: { degenerate_pages: [12, 34] } })],
    })
    expect(out.message).toContain('2 页云端取字判为退化，已换识别路径重取，请核对原页')
    expect(out.warned).toBe(false)
  })

  it('有列数突变 → 点名页数并指向数字表头，不升级 warned', () => {
    const out = summarizeAutoSplitResults({
      ...base,
      results: [
        result({
          pageAnomaly: { column_anomalies: [{ page_no: 7, prev_page_no: 6, cols: 5, prev_cols: 4 }] },
        }),
      ],
    })
    expect(out.message).toContain('1 页表格列数与邻页不同，数字表头请核对')
    expect(out.warned).toBe(false)
  })

  it('两类都有：先退化后列数，且多份材料跨任务累加', () => {
    const out = summarizeAutoSplitResults({
      ...base,
      results: [
        result({
          pageAnomaly: {
            degenerate_pages: [12],
            column_anomalies: [{ page_no: 7, prev_page_no: 6, cols: 5, prev_cols: 4 }],
          },
        }),
        result({
          mi: 1,
          jobId: 'job-2',
          pageAnomaly: {
            degenerate_pages: [3, 4],
            column_anomalies: [{ page_no: 20, prev_page_no: 19, cols: 3, prev_cols: 4 }],
          },
        }),
      ],
    })
    expect(out.message).toContain('3 页云端取字判为退化')
    expect(out.message).toContain('2 页表格列数与邻页不同')
    expect(out.message.indexOf('退化')).toBeLessThan(out.message.indexOf('表格列数'))
  })

  it('旧任务（pageAnomaly 为 null）→ 一个字都不加（与引入前逐位一致）', () => {
    const out = summarizeAutoSplitResults({ ...base, results: [result()] })
    expect(out.message).not.toContain('退化')
    expect(out.message).not.toContain('列数')
  })
})
