// @vitest-environment jsdom
/**
 * crossborder-ui.TonePill：跨境审查子域自带语气的胶囊。
 *
 * 自己带一份而不是复用 deal-detail/ui.tsx 的 Pill，是因为那一份不带 tone 且禁止
 * 修改，而这一屏要表达「高/中/低风险」「对方接受/还价/拒绝」——语气必须能区分开。
 */
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { TonePill } from './crossborder-ui'

function clsOf(tone?: 'neutral' | 'green' | 'red' | 'yellow' | 'blue') {
  const { container, unmount } = render(
    tone ? <TonePill tone={tone}>标签</TonePill> : <TonePill>标签</TonePill>,
  )
  const cls = (container.firstElementChild as HTMLElement).className
  unmount()
  return cls
}

describe('TonePill', () => {
  it('默认 neutral', () => {
    expect(clsOf()).toBe(clsOf('neutral'))
  })

  it('五种语气配色互不相同', () => {
    const tones = ['neutral', 'green', 'red', 'yellow', 'blue'] as const
    const classes = tones.map((t) => clsOf(t))
    expect(new Set(classes).size).toBe(tones.length)
  })

  it('red 表示高风险、green 表示低风险/可接受', () => {
    expect(clsOf('red')).toContain('status-red')
    expect(clsOf('green')).toContain('status-green')
    expect(clsOf('yellow')).toContain('status-yellow')
  })
})
