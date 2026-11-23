// @vitest-environment jsdom
/**
 * components/shared/DetailDrawer 单测（jsdom）。
 *
 * 锁住模态行为（审计 P20-100 的缺口：只实现了 ESC，没有 Tab 圈定、没有焦点归还）：
 * 1. open=false 时什么都不渲染（不留下吃指针事件的空壳层）；
 * 2. ESC 只触发**一次** onClose —— 本组件曾自绘一份 window keydown 监听，
 *    接上 useFocusTrap 后若那份没删，一次 ESC 会跑两次回调；
 * 3. Tab / Shift+Tab 在抽屉内首尾循环，焦点不跑到背后页面；
 * 4. 关闭后焦点回到打开前的元素（键盘用户不用从头 Tab）；
 * 5. 层级 z-[110]：高于 copilot dock（z-[100]）、低于菜单/弹窗（z-[120]/[130]），
 *    见组件文件头的阶梯快照（P20-102）；
 * 6. 抽屉里的行内编辑自己处理 Esc（重命名输入框）时，内层处理器先跑、抽屉照旧关；
 *    内层 `preventDefault()` 就只取消编辑不关抽屉（Esc 不能像 Tab 那样走 capture）。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { DetailDrawer } from './DetailDrawer'

function setup(props: Partial<Parameters<typeof DetailDrawer>[0]> = {}) {
  const onClose = vi.fn()
  const utils = render(
    <DetailDrawer open title="材料详情" subtitle="第 3 页" onClose={onClose} {...props}>
      <button type="button">动作一</button>
      <button type="button">动作二</button>
    </DetailDrawer>,
  )
  return { ...utils, onClose }
}

describe('DetailDrawer · 模态行为', () => {
  it('open=false 不渲染任何东西', () => {
    const { container } = setup({ open: false })
    expect(container.firstChild).toBeNull()
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('ESC 触发 onClose，且只触发一次（没有和自绘监听双重触发）', () => {
    const { onClose } = setup()
    // 从抽屉内部按下 Esc：capture 阶段在 window 上兜住。若自绘的 bubble 监听
    // 还在，两个监听都会收到这一次按键，onClose 就会是 2 次。
    fireEvent.keyDown(screen.getByRole('dialog', { name: '材料详情' }), { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('Tab 在抽屉内首尾循环，Shift+Tab 反向', () => {
    setup()
    const dialog = screen.getByRole('dialog')
    const focusables = Array.from(dialog.querySelectorAll<HTMLElement>('button:not([disabled])'))
    const first = focusables[0]!
    const last = focusables[focusables.length - 1]!
    expect(first).toBe(screen.getByRole('button', { name: '关闭' }))
    expect(last.textContent).toBe('动作二')

    last.focus()
    fireEvent.keyDown(window, { key: 'Tab' })
    expect(document.activeElement).toBe(first)

    first.focus()
    fireEvent.keyDown(window, { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(last)
  })

  it('内层输入框自己处理 Esc 时先跑内层，抽屉 onClose 仍调一次', () => {
    const onClose = vi.fn()
    const onInnerEscape = vi.fn()
    render(
      <DetailDrawer open onClose={onClose} title="重命名">
        <input
          aria-label="交付物名称"
          defaultValue="草稿"
          onKeyDown={(e) => {
            if (e.key === 'Escape') onInnerEscape()
          }}
        />
      </DetailDrawer>,
    )

    fireEvent.keyDown(screen.getByLabelText('交付物名称'), { key: 'Escape' })

    expect(onInnerEscape).toHaveBeenCalledTimes(1)
    expect(onClose).toHaveBeenCalledTimes(1)
    // 先取消行内编辑、再关抽屉（Esc 挂在 bubble 相才有的顺序）
    expect(onInnerEscape.mock.invocationCallOrder[0]!).toBeLessThan(onClose.mock.invocationCallOrder[0]!)
  })

  it('内层 preventDefault() 后只取消编辑，不关抽屉', () => {
    const onClose = vi.fn()
    const onInnerEscape = vi.fn()
    render(
      <DetailDrawer open onClose={onClose} title="重命名">
        <input
          aria-label="交付物名称"
          onKeyDown={(e) => {
            if (e.key === 'Escape') {
              e.preventDefault()
              onInnerEscape()
            }
          }}
        />
      </DetailDrawer>,
    )

    fireEvent.keyDown(screen.getByLabelText('交付物名称'), { key: 'Escape' })

    expect(onInnerEscape).toHaveBeenCalledTimes(1)
    expect(onClose).not.toHaveBeenCalled()
  })

  it('关闭后焦点回到打开前的元素', () => {
    const onClose = vi.fn()
    const tree = (open: boolean) => (
      <>
        <button type="button">打开详情</button>
        <DetailDrawer open={open} onClose={onClose} title="材料详情">
          内容
        </DetailDrawer>
      </>
    )
    const { rerender } = render(tree(false))
    const trigger = screen.getByRole('button', { name: '打开详情' })
    trigger.focus()

    rerender(tree(true))
    expect(screen.getByRole('dialog')).toBeTruthy()
    rerender(tree(false))

    expect(document.activeElement).toBe(trigger)
  })

  it('层级取阶梯里的 z-[110]：高于 dock、低于菜单与弹窗基线', () => {
    const { container } = setup()
    const layer = container.firstChild as HTMLElement
    expect(layer.className).toContain('z-[110]')
    expect(layer.className).not.toContain('z-[80]')
  })
})
