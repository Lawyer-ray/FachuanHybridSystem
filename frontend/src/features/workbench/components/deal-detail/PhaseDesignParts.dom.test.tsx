// @vitest-environment jsdom
/**
 * PhaseDesignParts：阶段设计器的表单小件（无独立行为，锁的是几处易回归的交互契约）。
 *
 * - TextInput 是受控的：每次输入都把**新值**交出去（而不是事件对象）
 * - IconBtn 的可发现性：title 与 aria-label 同时给出，且 disabled 真的拦住 onClick
 * - SmallDash / IconBtn 都有 type="button"（否则嵌进表单会提交）
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { Field, IconBtn, SmallDash, TextInput } from './PhaseDesignParts'

describe('Field：标签 + 说明 + 内容', () => {
  it('渲染标签与说明，children 在下方', () => {
    const { container } = render(
      <Field label="阶段名" note="必填">
        <span>内容</span>
      </Field>,
    )
    expect(container.textContent).toContain('阶段名')
    expect(container.textContent).toContain('必填')
    expect(container.textContent).toContain('内容')
  })

  it('无 note 时标签里不渲染说明节点', () => {
    const { container } = render(
      <Field label="阶段名">
        <span>内容</span>
      </Field>,
    )
    // children 的 <span> 之外，标签自身不再额外插一个说明 <span>
    const label = container.firstElementChild!.firstElementChild as HTMLElement
    expect(label.tagName).toBe('SPAN')
    expect(label.querySelectorAll('span')).toHaveLength(0)
  })
})

describe('TextInput：受控输入', () => {
  it('输入时把字符串值交给 onChange（不是事件对象）', () => {
    const onChange = vi.fn()
    render(<TextInput value="" placeholder="写阶段名" onChange={onChange} />)
    fireEvent.change(screen.getByPlaceholderText('写阶段名'), { target: { value: '尽职调查' } })
    expect(onChange).toHaveBeenCalledWith('尽职调查')
  })

  it('value 由外部控制（受控组件）', () => {
    render(<TextInput value="已有值" placeholder="p" onChange={vi.fn()} />)
    expect((screen.getByPlaceholderText('p') as HTMLInputElement).value).toBe('已有值')
  })
})

describe('IconBtn：小方钮', () => {
  it('title 与 aria-label 同源，便于读屏与悬停提示', () => {
    render(
      <IconBtn label="上移" onClick={vi.fn()}>
        ↑
      </IconBtn>,
    )
    const btn = screen.getByRole('button', { name: '上移' })
    expect(btn.getAttribute('title')).toBe('上移')
    expect(btn.getAttribute('type')).toBe('button')
  })

  it('点击触发 onClick', () => {
    const onClick = vi.fn()
    render(
      <IconBtn label="删除" danger onClick={onClick}>
        ×
      </IconBtn>,
    )
    fireEvent.click(screen.getByRole('button', { name: '删除' }))
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('disabled 时点击不触发（且标了 disabled 属性）', () => {
    const onClick = vi.fn()
    render(
      <IconBtn label="上移" disabled onClick={onClick}>
        ↑
      </IconBtn>,
    )
    const btn = screen.getByRole('button', { name: '上移' }) as HTMLButtonElement
    expect(btn.disabled).toBe(true)
    fireEvent.click(btn)
    expect(onClick).not.toHaveBeenCalled()
  })

  it('danger 与普通态用不同配色（删除不跟普通动作长一样）', () => {
    const { container: plain } = render(
      <IconBtn label="上移" onClick={vi.fn()}>
        ↑
      </IconBtn>,
    )
    const plainCls = (plain.firstElementChild as HTMLElement).className

    const { container: danger } = render(
      <IconBtn label="删除" danger onClick={vi.fn()}>
        ×
      </IconBtn>,
    )
    const dangerCls = (danger.firstElementChild as HTMLElement).className
    expect(dangerCls).not.toBe(plainCls)
    expect(dangerCls).toContain('status-red')
  })
})

describe('SmallDash：虚线小按钮', () => {
  it('点击触发 onClick，且不提交表单', () => {
    const onClick = vi.fn()
    render(<SmallDash onClick={onClick}>＋ 添加子阶段</SmallDash>)
    const btn = screen.getByRole('button', { name: '＋ 添加子阶段' })
    expect(btn.getAttribute('type')).toBe('button')
    fireEvent.click(btn)
    expect(onClick).toHaveBeenCalledTimes(1)
  })
})
