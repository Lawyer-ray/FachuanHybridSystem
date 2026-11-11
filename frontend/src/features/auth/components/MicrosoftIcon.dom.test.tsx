// @vitest-environment jsdom
/**
 * MicrosoftIcon 测试（jsdom）。
 *
 * 内联 SVG 而不是外链图片：登录页不能因为外链加载失败而丢掉品牌标。
 * 因此这里断言「四色几何确实内联在 DOM 里」且对读屏器隐藏（纯装饰）。
 */
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { MicrosoftIcon } from './MicrosoftIcon'

describe('MicrosoftIcon', () => {
  it('默认 18×18，四色路径内联存在', () => {
    const { container } = render(<MicrosoftIcon />)
    const svg = container.querySelector('svg') as SVGSVGElement
    expect(svg.getAttribute('width')).toBe('18')
    expect(svg.getAttribute('height')).toBe('18')

    const fills = Array.from(svg.querySelectorAll('path')).map((p) => p.getAttribute('fill'))
    expect(fills).toEqual(['#F25022', '#7FBA00', '#00A4EF', '#FFB900'])
  })

  it('size 可覆盖尺寸', () => {
    const { container } = render(<MicrosoftIcon size={24} />)
    const svg = container.querySelector('svg') as SVGSVGElement
    expect(svg.getAttribute('width')).toBe('24')
    expect(svg.getAttribute('height')).toBe('24')
  })

  it('纯装饰：对读屏器与键盘焦点都隐藏', () => {
    const { container } = render(<MicrosoftIcon />)
    const svg = container.querySelector('svg') as SVGSVGElement
    expect(svg.getAttribute('aria-hidden')).toBe('true')
    expect(svg.getAttribute('focusable')).toBe('false')
  })
})
