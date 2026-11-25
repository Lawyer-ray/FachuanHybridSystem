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
    inconsistencies: [],
    engineDisagreements: [],
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
