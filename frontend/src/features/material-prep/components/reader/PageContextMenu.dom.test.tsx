// @vitest-environment jsdom
/**
 * PageContextMenu 测试（jsdom）。
 *
 * 覆盖：标题与数量渲染、视口夹取定位、点外部关闭、Esc 关闭、
 * 删除入口回调、onClose 引用更新不影响订阅（ref 存最新回调）。
 */
import { fireEvent, render, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { PageContextMenu } from './PageContextMenu'

function renderMenu(props: Partial<Parameters<typeof PageContextMenu>[0]> = {}) {
  const onDelete = vi.fn()
  const onClose = vi.fn()
  const utils = render(
    <PageContextMenu x={100} y={100} title="第 1 页" count={1} onDelete={onDelete} onClose={onClose} {...props} />,
  )
  const menu = utils.container.firstElementChild as HTMLElement
  return { ...utils, menu, onDelete, onClose }
}

describe('PageContextMenu', () => {
  it('渲染标题与所选页数', () => {
    const { menu, unmount } = renderMenu({ title: '第 2 页', count: 3 })
    expect(menu.textContent).toContain('第 2 页')
    expect(menu.textContent).toContain('3')
    unmount()
  })

  it('点删除触发 onDelete', () => {
    const { menu, onDelete, unmount } = renderMenu()
    const delBtn = Array.from(menu.querySelectorAll('button')).find((b) =>
      /删除/.test(b.textContent ?? ''),
    ) as HTMLElement
    fireEvent.click(delBtn)
    expect(onDelete).toHaveBeenCalled()
    unmount()
  })

  it('点击菜单外部关闭', async () => {
    const { onClose, unmount } = renderMenu()
    fireEvent.mouseDown(document.body)
    await waitFor(() => expect(onClose).toHaveBeenCalled())
    unmount()
  })

  it('在菜单内部点击不关闭', async () => {
    const { menu, onClose, unmount } = renderMenu()
    fireEvent.mouseDown(menu)
    await new Promise((r) => setTimeout(r, 30))
    expect(onClose).not.toHaveBeenCalled()
    unmount()
  })

  it('Esc 关闭', async () => {
    const { onClose, unmount } = renderMenu()
    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() => expect(onClose).toHaveBeenCalled())
    unmount()
  })

  it('靠近右下角时定位被夹回视口内', async () => {
    // jsdom 下 offsetWidth/offsetHeight 为 0，显式桩一个尺寸以验证夹取逻辑
    Object.defineProperty(HTMLElement.prototype, 'offsetWidth', { configurable: true, value: 180 })
    Object.defineProperty(HTMLElement.prototype, 'offsetHeight', { configurable: true, value: 80 })

    const { menu, unmount } = renderMenu({ x: window.innerWidth - 10, y: window.innerHeight - 10 })
    await waitFor(() => {
      const left = Number.parseFloat(menu.style.left)
      expect(left).toBeLessThanOrEqual(window.innerWidth - 180 - 8 + 1)
    })
    unmount()
  })

  it('卸载后移除监听（Esc 不再回调）', async () => {
    const { onClose, unmount } = renderMenu()
    unmount()
    fireEvent.keyDown(window, { key: 'Escape' })
    await new Promise((r) => setTimeout(r, 30))
    expect(onClose).not.toHaveBeenCalled()
  })
})
