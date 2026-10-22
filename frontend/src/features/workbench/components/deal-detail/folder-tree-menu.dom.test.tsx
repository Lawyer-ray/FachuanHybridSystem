// @vitest-environment jsdom
/**
 * TreeContextMenu 测试（jsdom）。
 *
 * 本文件同时是 2026-10 审查 W-P1-4 的回归：右键菜单此前无焦点管理，
 * 键盘用户（Shift+F10 唤起）无法操作菜单项。现在要求：
 * - 挂载后焦点进入首个 menuitem
 * - ↑↓ 循环、Home/End 跳首尾
 * - Esc 关闭
 * - 菜单定位夹在视口内
 */
import { fireEvent, render, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { TreeContextMenu } from './folder-tree-menu'

function renderMenu(x = 100, y = 100) {
  const onClose = vi.fn()
  const onClickA = vi.fn()
  const onClickB = vi.fn()
  const utils = render(
    <TreeContextMenu
      x={x}
      y={y}
      items={[
        { label: '重命名', onClick: onClickA },
        { label: '删除', danger: true, onClick: onClickB },
      ]}
      onClose={onClose}
    />,
  )
  return { ...utils, onClose, onClickA, onClickB }
}

describe('TreeContextMenu', () => {
  it('渲染全部菜单项，danger 项带 destructive 文案色', () => {
    const { unmount } = renderMenu()
    const items = document.querySelectorAll('[role="menuitem"]')
    expect(items).toHaveLength(2)
    expect(items[0]!.textContent).toBe('重命名')
    expect(items[1]!.className).toContain('text-destructive')
    unmount()
  })

  it('挂载后焦点自动进入首个菜单项（键盘可操作）', async () => {
    const { unmount } = renderMenu()
    await waitFor(() => {
      const first = document.querySelector('[role="menuitem"]') as HTMLElement
      expect(document.activeElement).toBe(first)
    })
    unmount()
  })

  it('ArrowDown 移到下一项，末尾循环回首项', async () => {
    const { unmount } = renderMenu()
    await waitFor(() =>
      expect(document.activeElement).toBe(document.querySelector('[role="menuitem"]')),
    )
    const items = document.querySelectorAll<HTMLElement>('[role="menuitem"]')

    fireEvent.keyDown(document, { key: 'ArrowDown' })
    expect(document.activeElement).toBe(items[1])

    fireEvent.keyDown(document, { key: 'ArrowDown' })
    expect(document.activeElement).toBe(items[0])
    unmount()
  })

  it('ArrowUp 从首项回到末项', async () => {
    const { unmount } = renderMenu()
    await waitFor(() =>
      expect(document.activeElement).toBe(document.querySelector('[role="menuitem"]')),
    )
    const items = document.querySelectorAll<HTMLElement>('[role="menuitem"]')

    fireEvent.keyDown(document, { key: 'ArrowUp' })
    expect(document.activeElement).toBe(items[1])
    unmount()
  })

  it('Home / End 跳到首尾', async () => {
    const { unmount } = renderMenu()
    await waitFor(() =>
      expect(document.activeElement).toBe(document.querySelector('[role="menuitem"]')),
    )
    const items = document.querySelectorAll<HTMLElement>('[role="menuitem"]')

    fireEvent.keyDown(document, { key: 'End' })
    expect(document.activeElement).toBe(items[1])

    fireEvent.keyDown(document, { key: 'Home' })
    expect(document.activeElement).toBe(items[0])
    unmount()
  })

  it('Esc 关闭菜单', async () => {
    const { onClose, unmount } = renderMenu()
    await waitFor(() => expect(document.querySelector('[role="menuitem"]')).toBeTruthy())
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
    unmount()
  })

  it('点菜单项触发其回调', async () => {
    const { onClickA, onClickB, unmount } = renderMenu()
    await waitFor(() => expect(document.querySelector('[role="menuitem"]')).toBeTruthy())

    const items = document.querySelectorAll<HTMLElement>('[role="menuitem"]')
    fireEvent.click(items[0]!)
    expect(onClickA).toHaveBeenCalledTimes(1)

    fireEvent.click(items[1]!)
    expect(onClickB).toHaveBeenCalledTimes(1)
    unmount()
  })

  it('菜单在右侧超出视口时被夹住（不溢出屏幕）', async () => {
    // 视口宽 1024，x 给到 1020 → left 必须小于 x
    const { unmount } = renderMenu(1020, 100)
    const menu = document.querySelector('[role="menu"]') as HTMLElement
    const left = Number.parseFloat(menu.style.left)
    expect(left).toBeLessThanOrEqual(window.innerWidth - 180)
    unmount()
  })

  it('延后一拍才绑定外部点击关闭（创建菜单的同一事件不会立刻关闭它）', async () => {
    const { onClose, unmount } = renderMenu()
    // 挂载同一个 tick 内的 click 不应关闭
    fireEvent.click(document)
    expect(onClose).not.toHaveBeenCalled()

    // 等一拍后再点才关闭
    await new Promise((r) => setTimeout(r, 10))
    fireEvent.click(document)
    expect(onClose).toHaveBeenCalled()
    unmount()
  })
})
