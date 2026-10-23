// @vitest-environment jsdom
/**
 * MetaPanel 测试（jsdom）。
 *
 * 材料信息便签面板。核心分支：
 * - 空态只显示「便签，不是表单」；有字段后让位
 * - 字段类型派发：select（有 opts）/ textarea（ta）/ PartyPicker（当事人三类）/ 普通 input
 * - 删除两段确认：有值先 arm、再点才删；空值直接删；blur 取消 arm
 * - 标来源按钮的 pressed 态与切换
 * - 「记一项」展开字段库、已用字段不重复出现、用完提示
 */
import { fireEvent, render, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../constants', () => ({
  FIELD_LIB: [
    { k: '委托人', ph: '姓名或单位' },
    { k: '对方当事人', ph: '对方' },
    { k: '标的额', ph: '金额' },
  ],
}))
vi.mock('./PartyPicker', () => ({
  PartyPicker: ({ value, placeholder }: { value: string; placeholder?: string }) => (
    <div>
      PARTY_PICKER:{value}:{placeholder}
    </div>
  ),
}))

import { MetaPanel } from './MetaPanel'

function wrap(children: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

function draft(infos: unknown[]) {
  return { mats: [], segs: [], infos } as never
}

function ops() {
  return {
    setValue: vi.fn(),
    removeInfo: vi.fn(),
    addInfo: vi.fn(),
  }
}

function renderPanel(infos: unknown[], extra: { pickInfo?: number; o?: ReturnType<typeof ops> } = {}) {
  const o = extra.o ?? ops()
  const onSetPickInfo = vi.fn()
  const utils = render(
    wrap(
      <MetaPanel
        draft={draft(infos)}
        pickInfo={extra.pickInfo ?? -1}
        onSetPickInfo={onSetPickInfo}
        ops={o as never}
      />,
    ),
  )
  return { ...utils, o, onSetPickInfo }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('MetaPanel：空态与字段渲染', () => {
  it('无字段时显示便签说明', () => {
    const { container } = renderPanel([])
    expect(container.textContent).toContain('便签，不是表单')
    container.remove()
  })

  it('有字段后不再显示便签说明', () => {
    const { container } = renderPanel([{ k: '标的额', v: '100' }])
    expect(container.textContent).not.toContain('便签，不是表单')
    container.remove()
  })

  it('渲染字段名与值', () => {
    const { container } = renderPanel([{ k: '标的额', v: '100000' }])
    expect(within(container).getByText('标的额')).toBeTruthy()
    // 普通字段的值绑在 input.value 上，不在 textContent 里
    expect((container.querySelector('input') as HTMLInputElement).value).toBe('100000')
    container.remove()
  })

  it('带 src 时显示来源', () => {
    const { container } = renderPanel([{ k: '标的额', v: '1', src: 'P3' }])
    expect(container.textContent).toContain('来源 P3')
    container.remove()
  })
})

describe('MetaPanel：字段类型派发', () => {
  it('有 opts 的字段渲染为 select', () => {
    const { container } = renderPanel([{ k: '类型', v: '', opts: ['民事', '刑事'] }])
    expect(container.querySelector('select')).toBeTruthy()
    container.remove()
  })

  it('ta 标记的字段渲染为 textarea', () => {
    const { container } = renderPanel([{ k: '备注', v: '', ta: true }])
    expect(container.querySelector('textarea')).toBeTruthy()
    container.remove()
  })

  it('委托人渲染为 PartyPicker（我方）', () => {
    const { container } = renderPanel([{ k: '委托人', v: '张三' }])
    expect(container.textContent).toContain('PARTY_PICKER:张三')
    container.remove()
  })

  it('对方当事人渲染为 PartyPicker（非我方）', () => {
    const { container } = renderPanel([{ k: '对方当事人', v: '李四' }])
    expect(container.textContent).toContain('PARTY_PICKER:李四')
    container.remove()
  })

  it('普通字段渲染为 input，输入调用 setValue', () => {
    const o = ops()
    const { container } = renderPanel([{ k: '标的额', v: '' }], { o })
    const input = container.querySelector('input') as HTMLInputElement
    fireEvent.change(input, { target: { value: '200' } })
    expect(o.setValue).toHaveBeenCalledWith(0, '200')
    container.remove()
  })

  it('placeholder 合并 ph 与 hint', () => {
    const { container } = renderPanel([{ k: '标的额', v: '', ph: '金额', hint: '含税' }])
    const input = container.querySelector('input') as HTMLInputElement
    expect(input.placeholder).toBe('金额，含税')
    container.remove()
  })
})

describe('MetaPanel：标来源', () => {
  it('未取字时按钮为「标来源」，点击开启', () => {
    const { container, onSetPickInfo } = renderPanel([{ k: '标的额', v: '' }])
    const btn = within(container).getByRole('button', { name: '标来源' })
    fireEvent.click(btn)
    expect(onSetPickInfo).toHaveBeenCalledWith(0)
    container.remove()
  })

  it('取字中时按钮为「取消标来源」且 aria-pressed', () => {
    const { container, onSetPickInfo } = renderPanel([{ k: '标的额', v: '' }], { pickInfo: 0 })
    const btn = within(container).getByRole('button', { name: '取消标来源' })
    expect(btn.getAttribute('aria-pressed')).toBe('true')
    fireEvent.click(btn)
    expect(onSetPickInfo).toHaveBeenCalledWith(-1)
    container.remove()
  })
})

describe('MetaPanel：删除两段确认', () => {
  it('有值的字段第一次点击只 arm，不删除', () => {
    const o = ops()
    const { container } = renderPanel([{ k: '标的额', v: '100' }], { o })
    const del = within(container).getByRole('button', { name: '删除这个字段' })

    fireEvent.click(del)
    expect(o.removeInfo).not.toHaveBeenCalled()
    container.remove()
  })

  it('有值的字段第二次点击才真正删除', () => {
    const o = ops()
    const { container } = renderPanel([{ k: '标的额', v: '100' }], { o })
    const del = within(container).getByRole('button', { name: '删除这个字段' })

    fireEvent.click(del)
    fireEvent.click(del)
    expect(o.removeInfo).toHaveBeenCalledWith(0)
    container.remove()
  })

  it('空值字段直接删除（无需确认）', () => {
    const o = ops()
    const { container } = renderPanel([{ k: '标的额', v: '' }], { o })
    fireEvent.click(within(container).getByRole('button', { name: '删除这个字段' }))
    expect(o.removeInfo).toHaveBeenCalledWith(0)
    container.remove()
  })

  it('blur 取消已 arm 的状态', () => {
    const o = ops()
    const { container } = renderPanel([{ k: '标的额', v: '100' }], { o })
    const del = within(container).getByRole('button', { name: '删除这个字段' })

    fireEvent.click(del) // arm
    fireEvent.blur(del) // 取消
    fireEvent.click(del) // 重新 arm（若上一步没取消，这次就会删）
    expect(o.removeInfo).not.toHaveBeenCalled()
    container.remove()
  })
})

describe('MetaPanel：记一项字段库', () => {
  it('点「记一项」展开字段库', () => {
    const { container } = renderPanel([])
    fireEvent.click(within(container).getByText('记一项'))
    expect(within(container).getByText('委托人')).toBeTruthy()
    container.remove()
  })

  it('已用字段不出现在字段库里', () => {
    const { container } = renderPanel([{ k: '委托人', v: '张三' }])
    fireEvent.click(within(container).getByText('记一项'))
    // 「委托人」作为已用字段只出现在字段卡里，字段库按钮里不应再有
    const libButtons = Array.from(container.querySelectorAll('button')).filter((b) =>
      ['委托人', '对方当事人', '标的额'].includes(b.textContent ?? ''),
    )
    expect(libButtons.map((b) => b.textContent)).toEqual(['对方当事人', '标的额'])
    container.remove()
  })

  it('点字段库项调用 addInfo 并收起', () => {
    const o = ops()
    const { container } = renderPanel([], { o })
    fireEvent.click(within(container).getByText('记一项'))
    fireEvent.click(within(container).getByText('标的额'))

    expect(o.addInfo).toHaveBeenCalledWith(expect.objectContaining({ k: '标的额' }))
    // 收起后字段库按钮消失
    expect(container.textContent).not.toContain('对方当事人')
    container.remove()
  })

  it('字段库用完时提示', () => {
    const { container } = renderPanel([
      { k: '委托人', v: '' },
      { k: '对方当事人', v: '' },
      { k: '标的额', v: '' },
    ])
    fireEvent.click(within(container).getByText('记一项'))
    expect(container.textContent).toContain('字段库已用完')
    container.remove()
  })
})
