import { describe, expect, it } from 'vitest'

import { PDF_RENDER_MAX_WIDTH, PDF_RENDER_WIDTH, pdfRenderWidthFor } from './pdf'

describe('pdfRenderWidthFor（DPR 感知的渲染宽度）', () => {
  it('CSS 宽 × DPR：Retina 单列 900 → 1800', () => {
    expect(pdfRenderWidthFor(900, 2)).toBe(1800)
  })

  it('DPR=1 时保持基础宽度', () => {
    expect(pdfRenderWidthFor(900, 1)).toBe(900)
  })

  it('DPR 封顶 2：3x 屏不翻倍（960×3 → 1920 上限内）', () => {
    expect(pdfRenderWidthFor(960, 3)).toBe(1920)
  })

  it('下限保底 PDF_RENDER_WIDTH：窄列多列布局也有基础清晰度', () => {
    expect(pdfRenderWidthFor(320, 2)).toBe(PDF_RENDER_WIDTH)
    expect(pdfRenderWidthFor(140, 1)).toBe(PDF_RENDER_WIDTH)
  })

  it('上限封顶：超宽页（zoom 大）不超 PDF_RENDER_MAX_WIDTH', () => {
    expect(pdfRenderWidthFor(2000, 2)).toBe(PDF_RENDER_MAX_WIDTH)
  })
})
