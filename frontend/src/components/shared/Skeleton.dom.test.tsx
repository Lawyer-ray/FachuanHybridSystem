// @vitest-environment jsdom
/**
 * components/shared/Skeleton（骨架屏原语）单测（jsdom）。
 *
 * 这里锁的是「换掉 LoadingBlock 之后不能丢掉的三件事」：
 * 1. 灰块纯装饰：`aria-hidden`，不进无障碍树（读屏不该念一堆空 div）；
 * 2. 播报区：`role=status` + `aria-live=polite` + `aria-busy`，文案在 `sr-only` 里
 *    —— 旧实现 LoadingBlock 本来就会念「正在加载…」，换骨架不能倒退成静默；
 * 3. 延迟 + 卸载：`delayMs` 内**什么都不渲染**（首屏快请求不闪一帧），
 *    卸载时 clearTimeout（不留野定时器）。
 */
import { act, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { Skeleton, SkeletonStatus } from './Skeleton'

afterEach(() => {
  vi.useRealTimers()
})

describe('Skeleton', () => {
  it('纯装饰：aria-hidden 且不产生任何文本，className 与默认样式拼接', () => {
    const { container } = render(<Skeleton className="h-4 w-1/2" />)
    const block = container.firstElementChild as HTMLElement
    expect(block.getAttribute('aria-hidden')).toBe('true')
    expect(block.getAttribute('data-slot')).toBe('skeleton')
    // 默认三件套：脉冲 + 灰块 + reduced-motion 下不脉冲
    expect(block.className).toContain('animate-pulse')
    expect(block.className).toContain('bg-accent')
    expect(block.className).toContain('motion-reduce:animate-none')
    // 调用方的尺寸类必须能覆盖默认值（twMerge 生效）
    expect(block.className).toContain('h-4')
    expect(container.textContent).toBe('')
  })
})

describe('SkeletonStatus', () => {
  it('挂出后是礼貌播报区，文案落在 sr-only 里（读屏能念、视觉不占位）', () => {
    render(
      <SkeletonStatus text="正在加载项目数据…" delayMs={0}>
        <Skeleton className="h-8" />
      </SkeletonStatus>,
    )
    const status = screen.getByRole('status')
    expect(status.getAttribute('aria-live')).toBe('polite')
    expect(status.getAttribute('aria-busy')).toBe('true')
    const srOnly = status.querySelector('.sr-only')
    expect(srOnly?.textContent).toBe('正在加载项目数据…')
    // 播报区整体文本 = 文案（灰块自身没有文本）
    expect(status.textContent).toBe('正在加载项目数据…')
    expect(status.querySelector('[data-slot="skeleton"]')).toBeTruthy()
  })

  it('delayMs 内不渲染（防首屏闪一帧），到点才出现', () => {
    vi.useFakeTimers()
    render(
      <SkeletonStatus text="正在加载收件箱…" delayMs={300}>
        <Skeleton className="h-8" />
      </SkeletonStatus>,
    )
    expect(screen.queryByRole('status')).toBeNull()
    expect(document.querySelector('[data-slot="skeleton"]')).toBeNull()

    act(() => {
      vi.advanceTimersByTime(299)
    })
    expect(screen.queryByRole('status')).toBeNull()

    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.getByRole('status')).toBeTruthy()
    expect(screen.getByText('正在加载收件箱…')).toBeTruthy()
  })

  it('卸载时 clearTimeout：不对已卸载的组件 setState', () => {
    vi.useFakeTimers()
    const clearSpy = vi.spyOn(window, 'clearTimeout')
    const { unmount } = render(
      <SkeletonStatus text="正在加载" delayMs={300}>
        <Skeleton className="h-8" />
      </SkeletonStatus>,
    )
    unmount()
    expect(clearSpy).toHaveBeenCalled()
    // 推到原定时间点：既不该冒出播报区，也不该有 act 警告
    act(() => {
      vi.advanceTimersByTime(1000)
    })
    expect(screen.queryByRole('status')).toBeNull()
    clearSpy.mockRestore()
  })
})
