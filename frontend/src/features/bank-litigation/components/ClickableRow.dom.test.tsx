// @vitest-environment jsdom
/**
 * `ClickableRow` 的键盘事件隔离（P02-100）。
 *
 * 行的 `onKeyDown` 挂在 `<li>` 上，行内控件的 keydown 会冒泡上来。修复前它不看事件源：
 * 在行内 `<button>` / `<select>` 上按 Enter/Space，先被 `preventDefault()` 掐掉原生激活，
 * 再顺手跑一遍整行的 `onClick`（跳到详情/抽屉）。下面几条锁住两件事：
 * · 内层控件上的 Enter/Space 只属于那个控件——行不响应、也不取消它的默认行为；
 * · 行本体聚焦后 Enter/Space 照旧能打开整行（`nestedControl` 两种角色都通）。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ClickableRow } from './ClickableRow'

/**
 * 按真实调用点（`GapNoticeList` 的勾选框 / `ContractTermsCard` 的模板下拉）的样子搭：
 * 行内控件的 `stopPropagation` 只为鼠标点击，键盘路径交给 `ClickableRow` 放行。
 */
function setup({ nestedControl }: { nestedControl?: boolean } = {}) {
  const onRowClick = vi.fn()
  const onToggle = vi.fn()
  const onTemplateChange = vi.fn()
  const { container } = render(
    <ul>
      <ClickableRow nestedControl={nestedControl} onClick={onRowClick} className="flex">
        <button
          type="button"
          aria-label="勾选 银行流水"
          onClick={(e) => {
            e.stopPropagation()
            onToggle()
          }}
        >
          勾选
        </button>
        <select
          aria-label="模板"
          value="v3.2"
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => onTemplateChange(e.target.value)}
        >
          <option value="v3.2">模板 v3.2</option>
          <option value="v2.8">模板 v2.8</option>
        </select>
        <span>行文字</span>
      </ClickableRow>
    </ul>,
  )
  return { onRowClick, onToggle, onTemplateChange, row: () => container.querySelector('li') as HTMLLIElement }
}

/** 手动派发 keydown：`fireEvent` 拿不到事件对象，这里要断言 `defaultPrevented` */
function keyDown(el: Element, key: string) {
  const e = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true })
  el.dispatchEvent(e)
  return e
}

describe('ClickableRow：行内控件的键盘事件不上冒到行', () => {
  it('行内 button 上按 Enter：只走 button，行不开、原生激活不被取消', () => {
    const { onRowClick, onToggle } = setup({ nestedControl: true })
    const button = screen.getByRole('button', { name: '勾选 银行流水' })

    const e = keyDown(button, 'Enter')

    expect(onRowClick).not.toHaveBeenCalled()
    // 没被 preventDefault 掐掉，浏览器才肯替 Enter 发这次 click
    expect(e.defaultPrevented).toBe(false)

    fireEvent.click(button)
    expect(onToggle).toHaveBeenCalledTimes(1)
    expect(onRowClick).not.toHaveBeenCalled()
  })

  it('行内 select 上按 Space / Enter：行不响应，下拉的原生行为不被取消', () => {
    const { onRowClick } = setup({ nestedControl: true })
    const select = screen.getByRole('combobox', { name: '模板' })

    for (const key of [' ', 'Enter']) {
      expect(keyDown(select, key).defaultPrevented).toBe(false)
    }
    expect(onRowClick).not.toHaveBeenCalled()
  })

  it('行本体聚焦后 Enter / Space 都开整行，Space 的默认滚动被拦掉', () => {
    const { onRowClick, row } = setup({ nestedControl: true })
    row().focus()
    expect(document.activeElement).toBe(row())

    for (const key of ['Enter', ' ']) {
      expect(keyDown(row(), key).defaultPrevented).toBe(true)
    }
    expect(onRowClick).toHaveBeenCalledTimes(2)
  })

  it.each([
    { nestedControl: false, role: 'button' },
    { nestedControl: true, role: 'listitem' },
  ])('nestedControl=$nestedControl 的行仍能用 Tab + Enter 打开（role=$role）', ({ nestedControl, role }) => {
    const { onRowClick, row } = setup({ nestedControl })
    expect(row().getAttribute('role') ?? 'listitem').toBe(role)
    expect(row().tabIndex).toBe(0)

    row().focus()
    keyDown(row(), 'Enter')

    expect(onRowClick).toHaveBeenCalledTimes(1)
  })

  it('行本体上的非触发键（方向键等）原样放行', () => {
    const { onRowClick, row } = setup()

    expect(keyDown(row(), 'ArrowRight').defaultPrevented).toBe(false)
    expect(onRowClick).not.toHaveBeenCalled()
  })
})
