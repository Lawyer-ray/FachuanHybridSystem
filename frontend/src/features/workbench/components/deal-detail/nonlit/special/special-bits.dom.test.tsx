// @vitest-environment jsdom
/**
 * special-bits：关厂清盘工作台共用小件（抽屉四个页签 + 各卡片共用）。
 *
 * 契约：
 * - TonePill 的五个语气各自一套配色（高/中/低风险的区分全靠它）
 * - Inset 默认不画边框（卡内条目用底色分区），`framed` 时才画
 * - MiniButton 的 danger 与普通态不同色，且都有 type="button"
 * - SpecialDrawer 的内容宽度是 560（520 时交付物版本表要横向滚）
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { BlockHead, EmptyHint, Inset, MiniButton, SpecialDrawer, TonePill } from './special-bits'

describe('TonePill', () => {
  it('默认 neutral 用次级底色', () => {
    const { container } = render(<TonePill>在办</TonePill>)
    const cls = (container.firstElementChild as HTMLElement).className
    expect(cls).toContain('bg-secondary')
  })

  it('每个语气一套配色，五种互不相同', () => {
    const tones = ['neutral', 'green', 'red', 'yellow', 'blue'] as const
    const classes = tones.map((tone) => {
      const { container, unmount } = render(<TonePill tone={tone}>{tone}</TonePill>)
      const cls = (container.firstElementChild as HTMLElement).className
      unmount()
      return cls
    })
    expect(new Set(classes).size).toBe(tones.length)
    expect(classes[2]).toContain('status-red')
    expect(classes[1]).toContain('status-green')
  })
})

describe('Inset', () => {
  it('默认不画边框（卡内条目只用底色分区）', () => {
    const { container } = render(<Inset>内容</Inset>)
    const cls = (container.firstElementChild as HTMLElement).className
    expect(cls).toContain('bg-secondary/35')
    expect(cls).not.toContain('border ')
  })

  it('framed 时画细边框 + 白底', () => {
    const { container } = render(<Inset framed>内容</Inset>)
    const cls = (container.firstElementChild as HTMLElement).className
    expect(cls).toContain('border-light')
    expect(cls).toContain('bg-background')
  })

  it('className 透传（调用方补间距）', () => {
    const { container } = render(<Inset className="mt-3">内容</Inset>)
    expect((container.firstElementChild as HTMLElement).className).toContain('mt-3')
  })
})

describe('BlockHead', () => {
  it('标题必渲染，hint 与 action 可选', () => {
    const { container, unmount } = render(<BlockHead title="交付物" />)
    expect(container.textContent).toBe('交付物')
    unmount()

    render(<BlockHead title="交付物" hint="3 份" action={<button type="button">＋</button>} />)
    expect(screen.getByText('交付物')).toBeTruthy()
    expect(screen.getByText('3 份')).toBeTruthy()
    expect(screen.getByRole('button', { name: '＋' })).toBeTruthy()
  })
})

describe('EmptyHint', () => {
  it('渲染虚线的空态文案', () => {
    render(<EmptyHint>还没有交付物</EmptyHint>)
    expect(screen.getByText('还没有交付物')).toBeTruthy()
  })
})

describe('MiniButton', () => {
  it('点击触发 onClick，type=button（不提交外层表单）', () => {
    const onClick = vi.fn()
    render(<MiniButton onClick={onClick}>＋ 加交付物</MiniButton>)
    const btn = screen.getByRole('button', { name: '＋ 加交付物' })
    expect(btn.getAttribute('type')).toBe('button')
    fireEvent.click(btn)
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('title 参与悬停提示但不必等于文字', () => {
    render(
      <MiniButton onClick={vi.fn()} title="删除该交付物">
        删除
      </MiniButton>,
    )
    expect(screen.getByRole('button', { name: '删除' }).getAttribute('title')).toBe('删除该交付物')
  })

  it('danger 与 plain 配色不同', () => {
    const { container: plain } = render(<MiniButton onClick={vi.fn()}>a</MiniButton>)
    const plainCls = (plain.firstElementChild as HTMLElement).className
    const { container: danger } = render(
      <MiniButton onClick={vi.fn()} tone="danger">
        a
      </MiniButton>,
    )
    const dangerCls = (danger.firstElementChild as HTMLElement).className
    expect(dangerCls).not.toBe(plainCls)
    expect(dangerCls).toContain('status-red')
  })
})

describe('SpecialDrawer', () => {
  it('open=false 时不渲染任何内容', () => {
    render(
      <SpecialDrawer open={false} onClose={vi.fn()} title="阶段详情">
        <span>内容</span>
      </SpecialDrawer>,
    )
    expect(screen.queryByText('内容')).toBeNull()
  })

  it('open 时渲染标题、副标题、徽标与 footer', () => {
    render(
      <SpecialDrawer
        open
        onClose={vi.fn()}
        title="阶段详情"
        subtitle="第 2 阶段"
        badge={<span>进行中</span>}
        footer={<button type="button">保存</button>}
      >
        <span>内容</span>
      </SpecialDrawer>,
    )
    const dialog = screen.getByRole('dialog')
    expect(dialog.getAttribute('aria-label')).toBe('阶段详情')
    expect(screen.getByText('第 2 阶段')).toBeTruthy()
    expect(screen.getByText('进行中')).toBeTruthy()
    expect(screen.getByRole('button', { name: '保存' })).toBeTruthy()
  })

  it('内容宽度 560（交付物版本表在 520 下会横向滚）', () => {
    render(
      <SpecialDrawer open onClose={vi.fn()} title="阶段详情">
        <span>内容</span>
      </SpecialDrawer>,
    )
    expect((screen.getByRole('dialog') as HTMLElement).style.width).toBe('560px')
  })

  it('ESC 关闭', () => {
    const onClose = vi.fn()
    render(
      <SpecialDrawer open onClose={onClose} title="阶段详情">
        <span>内容</span>
      </SpecialDrawer>,
    )
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
