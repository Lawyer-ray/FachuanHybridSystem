// @vitest-environment jsdom
/**
 * PackCard 测试（jsdom）。
 *
 * 材料包卡片：
 * - 状态徽章三态（未打开 / 已归类 / N 份未归类）
 * - 标题回退（无 subject 用「材料包 id」）、页数/文件数统计
 * - 纸堆缩略（mats<=0 显占位、>3 显 +N）
 * - 归案按钮只在 finished 时可用
 * - 整卡点击层按 index 打开、不接/归案回调带 pack
 * - 已归案印章、离场动画类
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/format', () => ({ friendlyTime: () => '10-20' }))

import { PackCard } from './PackCard'
import type { InboxMessage } from '../types'

function pack(over: Partial<InboxMessage> = {}): InboxMessage {
  return {
    id: 7,
    subject: '张三材料包',
    status: 'todo',
    segs: 3,
    named: 1,
    mats: 2,
    pages: 12,
    types: ['起诉状'],
    source_name: '收件箱',
    received_at: '2026-10-20T10:00:00',
    ...over,
  } as InboxMessage
}

function renderCard(props: Partial<Parameters<typeof PackCard>[0]> = {}) {
  const cbs = { onOpen: vi.fn(), onReject: vi.fn(), onAccept: vi.fn() }
  const utils = render(
    <PackCard pack={pack()} index={2} finished={false} {...cbs} {...props} />,
  )
  return { ...utils, cbs }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('PackCard：状态徽章', () => {
  it('segs=0 显示「未打开」', () => {
    const { container } = renderCard({ pack: pack({ segs: 0, named: 0 }) })
    expect(container.textContent).toContain('未打开')
    container.remove()
  })

  it('全部归类（finished）显示「已归类」', () => {
    const { container } = renderCard({ finished: true, pack: pack({ segs: 3, named: 3 }) })
    expect(container.textContent).toContain('已归类')
    container.remove()
  })

  it('部分归类显示「N 份未归类」', () => {
    const { container } = renderCard({ pack: pack({ segs: 3, named: 1 }) })
    expect(container.textContent).toContain('2 份未归类')
    container.remove()
  })
})

describe('PackCard：标题与统计', () => {
  it('有 subject 时显示标题', () => {
    const { container } = renderCard()
    expect(within(container).getByText('张三材料包')).toBeTruthy()
    container.remove()
  })

  it('无 subject 时回落「材料包 id」', () => {
    const { container } = renderCard({ pack: pack({ subject: '' }) })
    expect(container.textContent).toContain('材料包 7')
    container.remove()
  })

  it('有页数时显示页数', () => {
    const { container } = renderCard({ pack: pack({ pages: 12, mats: 2 }) })
    expect(container.textContent).toContain('12 页')
    container.remove()
  })

  it('无页数但有文件数时显示文件数', () => {
    const { container } = renderCard({ pack: pack({ pages: 0, mats: 2 }) })
    expect(container.textContent).toContain('2 个文件')
    container.remove()
  })

  it('来源名回退「收件箱」', () => {
    const { container } = renderCard({ pack: pack({ source_name: '' }) })
    expect(container.textContent).toContain('收件箱')
    container.remove()
  })
})

describe('PackCard：事实链', () => {
  it('未拆分时提示「还没拆这份材料包」', () => {
    const { container } = renderCard({ pack: pack({ segs: 0 }) })
    expect(container.textContent).toContain('还没拆这份材料包')
    container.remove()
  })

  it('已拆分但无类型时提示「N 份材料待归类」', () => {
    const { container } = renderCard({ pack: pack({ segs: 3, named: 0, types: [] }) })
    expect(container.textContent).toContain('3 份材料待归类')
    container.remove()
  })

  it('有类型时逐个展示并补未归类计数', () => {
    const { container } = renderCard({ pack: pack({ segs: 3, named: 1, types: ['起诉状'] }) })
    expect(container.textContent).toContain('起诉状')
    expect(container.textContent).toContain('+2 份未归类')
    container.remove()
  })
})

describe('PackCard：纸堆缩略', () => {
  it('mats<=0 显示占位图标', () => {
    const { container } = renderCard({ pack: pack({ mats: 0 }) })
    // 占位是单个 div + FileText 图标，没有 docPage 纸堆
    expect(container.querySelectorAll('.w-\\[82px\\]').length).toBeLessThanOrEqual(1)
    container.remove()
  })

  it('mats>3 时显示 +N 角标', () => {
    const { container } = renderCard({ pack: pack({ mats: 7 }) })
    expect(container.textContent).toContain('+4')
    container.remove()
  })

  it('mats<=3 时无 +N 角标（只看纸堆旁的角标，排除「+N 份未归类」文案）', () => {
    const { container } = renderCard({ pack: pack({ mats: 2 }) })
    // 角标是紧跟纸堆的 span，形如 "+4"；未归类文案是 "+2 份未归类"
    const badges = Array.from(container.querySelectorAll('span')).filter((el) =>
      /^\+\d+$/.test((el.textContent ?? '').trim()),
    )
    expect(badges).toHaveLength(0)
    container.remove()
  })
})

describe('PackCard：交互', () => {
  it('点整卡按 index 打开', () => {
    const { cbs, unmount } = renderCard({ index: 5 })
    fireEvent.click(screen.getByRole('button', { name: /打开材料包/ }))
    expect(cbs.onOpen).toHaveBeenCalledWith(5)
    unmount()
  })

  it('点「不接」回调带 pack', () => {
    const { cbs, unmount } = renderCard()
    fireEvent.click(screen.getByRole('button', { name: '不接' }))
    expect(cbs.onReject).toHaveBeenCalledWith(expect.objectContaining({ id: 7 }))
    unmount()
  })

  it('未完成归类时「归案」禁用', () => {
    const { cbs, unmount } = renderCard({ finished: false })
    const btn = screen.getByRole('button', { name: '归案' }) as HTMLButtonElement
    expect(btn.disabled).toBe(true)
    fireEvent.click(btn)
    expect(cbs.onAccept).not.toHaveBeenCalled()
    unmount()
  })

  it('已归类时「归案」可用并回调', () => {
    const { cbs, unmount } = renderCard({ finished: true, pack: pack({ segs: 3, named: 3 }) })
    const btn = screen.getByRole('button', { name: '归案' }) as HTMLButtonElement
    expect(btn.disabled).toBe(false)
    fireEvent.click(btn)
    expect(cbs.onAccept).toHaveBeenCalledWith(expect.objectContaining({ id: 7 }))
    unmount()
  })
})

describe('PackCard：印章与离场', () => {
  it('status=done 显示「已归案」印章', () => {
    const { container } = renderCard({ pack: pack({ status: 'done' }) })
    expect(container.textContent).toContain('已归案')
    container.remove()
  })

  it('离场方向对应动画类', () => {
    const right = renderCard({ leaving: 'right' })
    expect(right.container.querySelector('.leave-right')).toBeTruthy()
    right.unmount()

    const left = renderCard({ leaving: 'left' })
    expect(left.container.querySelector('.leave-left')).toBeTruthy()
    left.unmount()
  })

  it('无离场时不带动画类', () => {
    const { container } = renderCard({ leaving: null })
    expect(container.querySelector('.leave-right')).toBeNull()
    expect(container.querySelector('.leave-left')).toBeNull()
    container.remove()
  })
})
