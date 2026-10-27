// @vitest-environment jsdom
/**
 * components/shared/status-badge（状态色单一来源）单测（jsdom）。
 *
 * 锁住的是「tone → 三件套」这张表：调用方后续全部改走 StatusBadge，
 * 一旦某个 tone 的 border/bg/text 被改错（或误改成硬编码 hex），这里直接红。
 * 同时确认颜色走 --status-* 变量别名（bg-status-green-bg 等），暗色主题才能跟着切。
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { BADGE_TONE_CLS, StatusBadge, type Tone } from './status-badge'

const TONES: Tone[] = ['green', 'yellow', 'red', 'blue', 'purple', 'neutral']

describe('BADGE_TONE_CLS', () => {
  it('每个 tone 都有 border / bg / text 三件套', () => {
    for (const tone of TONES) {
      const cls = BADGE_TONE_CLS[tone]
      expect(cls).toMatch(/\bborder-/)
      expect(cls).toMatch(/\bbg-/)
      expect(cls).toMatch(/\btext-/)
    }
  })

  it('状态色取 --status-* 变量别名，不硬编码 hex', () => {
    for (const tone of ['green', 'yellow', 'red', 'blue', 'purple'] as Tone[]) {
      expect(BADGE_TONE_CLS[tone]).toContain(`status-${tone}`)
      expect(BADGE_TONE_CLS[tone]).not.toMatch(/#[0-9a-f]{3,8}/i)
      expect(BADGE_TONE_CLS[tone]).not.toMatch(/\brgb/)
    }
  })
})

describe('StatusBadge', () => {
  it('默认 sm 尺寸并挂上对应 tone 的样式', () => {
    render(<StatusBadge tone="green">已完成</StatusBadge>)
    const el = screen.getByText('已完成')
    expect(el.tagName).toBe('SPAN')
    expect(el.className).toContain('text-[11px]')
    expect(el.className).toContain('bg-status-green-bg')
  })

  it('xs 尺寸更小，且 className 可叠加覆写', () => {
    render(
      <StatusBadge tone="red" size="xs" className="ml-1">
        失败
      </StatusBadge>,
    )
    const el = screen.getByText('失败')
    expect(el.className).toContain('text-[10px]')
    expect(el.className).toContain('text-status-red')
    expect(el.className).toContain('ml-1')
  })

  it('neutral 走灰阶而非状态色（已取消 / 无状态这类中性语义）', () => {
    render(<StatusBadge tone="neutral">已取消</StatusBadge>)
    const el = screen.getByText('已取消')
    expect(el.className).toContain('text-muted-foreground')
    expect(el.className).not.toContain('status-')
  })

  it('title 透传，供列表里长状态收窄后悬停看全称', () => {
    render(
      <StatusBadge tone="blue" title="正在转换文档">
        转换中
      </StatusBadge>,
    )
    expect(screen.getByText('转换中').getAttribute('title')).toBe('正在转换文档')
  })
})
