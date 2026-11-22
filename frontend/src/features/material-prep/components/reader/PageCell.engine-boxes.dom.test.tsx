// @vitest-environment jsdom
/**
 * 双框对照渲染单测（契约【视觉规则】）。
 *
 * 真实痛点：分歧是「两个引擎指的不是同一处」。只画一边的框，律师看到的还是一个框，
 * 无从判断差异在哪。所以必须两框同画，且**严格分色分线型**：
 *  - 主引擎 MinerU = 实线 `#16a34a`（绿）
 *  - 副引擎 VL = 虚线 `#f59e0b`（琥珀），`5 3`
 *  - 半透明填充，两框重叠时都看得见
 *  - `approx`（整页近似框）描边更淡，不给假精度
 *
 * 页体渲染分支 mock 成空组件：这里只测覆盖层本身。
 */
import { render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('./PdfPageView', () => ({ PdfPageView: () => null }))
vi.mock('./PhotoPageView', () => ({ PhotoPageView: () => null }))

import { PageCell } from './PageCell'
import type { EngineBoxGroup } from './EngineBoxOverlay'
import type { BundleMat } from '../../types'

const mat: BundleMat = { partIndex: 0, n: '证据.docx', k: 'office', pages: 3 }

function group(
  engine: 'mineru' | 'paddleocr_vl',
  text: string,
  rect = { x: 0.1, y: 0.2, w: 0.3, h: 0.05 },
  approx = false,
): EngineBoxGroup {
  return {
    variant: { engine, text },
    blocks: [{ engine, page_no: 2, text, rect, block_type: 'text', approx }],
  }
}

function svgOf(container: HTMLElement): SVGSVGElement {
  const svg = container.querySelector('svg[data-engine-box-overlay]')
  if (!svg) throw new Error('没有渲染双框覆盖层')
  return svg as unknown as SVGSVGElement
}

function rectsOf(container: HTMLElement, engine: string): Element[] {
  return Array.from(container.querySelectorAll(`[data-engine-box="${engine}"] rect`))
}

describe('PageCell 双引擎对照框', () => {
  it('不传 engineBoxes 时不渲染覆盖层（单引擎路径零开销）', () => {
    const { container } = render(<PageCell messageId={1} mi={0} p={2} mat={mat} />)
    expect(container.querySelector('svg[data-engine-box-overlay]')).toBeNull()
  })

  it('MinerU 实线绿、VL 虚线琥珀（5 3）', () => {
    const { container } = render(
      <PageCell messageId={1} mi={0} p={2} mat={mat} engineBoxes={[group('mineru', '张三丰'), group('paddleocr_vl', '张四丰')]} />,
    )
    const [primary] = rectsOf(container, 'mineru')
    const [secondary] = rectsOf(container, 'paddleocr_vl')
    expect(primary!.getAttribute('stroke')).toBe('#16a34a')
    expect(primary!.getAttribute('stroke-dasharray')).toBeNull()
    expect(secondary!.getAttribute('stroke')).toBe('#f59e0b')
    expect(secondary!.getAttribute('stroke-dasharray')).toBe('5 3')
  })

  it('半透明填充：两框重叠时都可见', () => {
    const { container } = render(
      <PageCell messageId={1} mi={0} p={2} mat={mat} engineBoxes={[group('mineru', 'a'), group('paddleocr_vl', 'b')]} />,
    )
    for (const el of [...rectsOf(container, 'mineru'), ...rectsOf(container, 'paddleocr_vl')]) {
      expect(el.getAttribute('fill-opacity')).toBe('0.12')
    }
  })

  it('归一化坐标按 viewBox 换算（与 hits 的百分比口径同源）', () => {
    const { container } = render(
      <PageCell
        messageId={1}
        mi={0}
        p={2}
        mat={mat}
        engineBoxes={[group('mineru', 'a', { x: 0.1, y: 0.2, w: 0.3, h: 0.05 })]}
      />,
    )
    const [r] = rectsOf(container, 'mineru')
    expect(r!.getAttribute('x')).toBe('100')
    expect(r!.getAttribute('y')).toBe('200')
    expect(r!.getAttribute('width')).toBe('300')
    expect(r!.getAttribute('height')).toBe('50')
    // viewBox 拉满容器，于是 x*100% 与 x*VIEWBOX 是同一个点
    expect(svgOf(container).getAttribute('preserveAspectRatio')).toBe('none')
  })

  it('approx 的框描边更淡（坐标不可信，不给假精度）', () => {
    const { container } = render(
      <PageCell messageId={1} mi={0} p={2} mat={mat} engineBoxes={[group('mineru', 'a', { x: 0.1, y: 0.1, w: 0.2, h: 0.2 }, true)]} />,
    )
    const [r] = rectsOf(container, 'mineru')
    expect(Number(r!.getAttribute('stroke-opacity'))).toBeLessThan(1)
    // 框旁小字也标出「坐标不可信」
    expect(container.textContent).toContain('≈')
  })

  it('框旁标注引擎短名与文本', () => {
    const { container } = render(
      <PageCell messageId={1} mi={0} p={2} mat={mat} engineBoxes={[group('mineru', '张三丰'), group('paddleocr_vl', '张四丰')]} />,
    )
    const text = container.textContent ?? ''
    expect(text).toContain('MinerU 张三丰')
    expect(text).toContain('VL 张四丰')
  })

  it('某引擎没有框时只画另一个（不伪造重合）', () => {
    const { container } = render(
      <PageCell messageId={1} mi={0} p={2} mat={mat} engineBoxes={[group('mineru', 'a'), { variant: { engine: 'paddleocr_vl', text: 'b' }, blocks: [] }]} />,
    )
    expect(rectsOf(container, 'mineru')).toHaveLength(1)
    expect(rectsOf(container, 'paddleocr_vl')).toHaveLength(0)
  })
})
