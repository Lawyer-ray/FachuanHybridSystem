// @vitest-environment jsdom
/**
 * RailSegRow 测试（jsdom）。
 *
 * 左栏一行的交互密度最高：
 * - 点击分派：普通点跳转；⌘/Ctrl/⇧ 点走多选；编辑中不响应
 * - 键盘：Enter/空格跳转、F2 进改名
 * - 双击进改名；改名 Enter 提交、Escape 取消、失焦提交；空名不提交
 * - 拖拽：dragstart 带上 si、dragover 按上下半给 before/after、drop/dragend 回调
 * - 视觉：未分类琥珀色、低置信度「复核」标、插入线位置
 * - 名字中部省略（尾部区分信息不能被截掉）
 */
import { createEvent, fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/components/ui/context-menu', () => ({
  ContextMenu: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  ContextMenuTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  ContextMenuContent: ({ children }: { children: React.ReactNode }) => <div data-testid="menu">{children}</div>,
  ContextMenuItem: ({ children, onSelect }: { children: React.ReactNode; onSelect?: () => void }) => (
    <button type="button" onClick={onSelect}>
      {children}
    </button>
  ),
  ContextMenuRadioGroup: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  ContextMenuRadioItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ContextMenuSeparator: () => <hr />,
  ContextMenuSub: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  ContextMenuSubContent: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  ContextMenuSubTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))
vi.mock('../../constants', () => ({ SEGMENT_TYPES: ['起诉状', '证据'] }))
vi.mock('../../draft', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../draft')>()
  return { ...actual, segRangeText: () => 'P1-P2' }
})

import { RailSegRow } from './RailSegRow'

function seg(over: Record<string, unknown> = {}) {
  return {
    id: 's1',
    t: '起诉状',
    fn: '起诉状.pdf',
    refs: [
      { mi: 0, p: 1 },
      { mi: 0, p: 2 },
    ],
    manual: false,
    ...over,
  } as never
}

function renderRow(props: Partial<Parameters<typeof RailSegRow>[0]> = {}) {
  const cbs = {
    onStartEdit: vi.fn(),
    onFocus: vi.fn(),
    onSelectRow: vi.fn(),
    onRename: vi.fn(),
    onSetType: vi.fn(),
    onDragStartRow: vi.fn(),
    onHoverDrop: vi.fn(),
    onDropRow: vi.fn(),
    onDragEndRow: vi.fn(),
  }
  const utils = render(
    <RailSegRow
      seg={seg()}
      si={0}
      whole={false}
      auto={false}
      classified
      color="#f00"
      editing={false}
      {...cbs}
      {...props}
    />,
  )
  const row = utils.container.querySelector('[draggable]') as HTMLElement
  return { ...utils, row, cbs }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('RailSegRow：点击分派', () => {
  it('普通点击跳转', () => {
    const { row, cbs, unmount } = renderRow()
    fireEvent.click(row)
    expect(cbs.onFocus).toHaveBeenCalled()
    expect(cbs.onSelectRow).not.toHaveBeenCalled()
    unmount()
  })

  it('⌘ 点击走多选', () => {
    const { row, cbs, unmount } = renderRow()
    fireEvent.click(row, { metaKey: true })
    expect(cbs.onSelectRow).toHaveBeenCalled()
    expect(cbs.onFocus).not.toHaveBeenCalled()
    unmount()
  })

  it('⇧ 点击走多选（区间选）', () => {
    const { row, cbs, unmount } = renderRow()
    fireEvent.click(row, { shiftKey: true })
    expect(cbs.onSelectRow).toHaveBeenCalled()
    unmount()
  })

  it('编辑中点击不跳转也不多选', () => {
    const { row, cbs, unmount } = renderRow({ editing: true })
    fireEvent.click(row)
    expect(cbs.onFocus).not.toHaveBeenCalled()
    expect(cbs.onSelectRow).not.toHaveBeenCalled()
    unmount()
  })

  it('双击进改名', () => {
    const { row, cbs, unmount } = renderRow()
    fireEvent.doubleClick(row)
    expect(cbs.onStartEdit).toHaveBeenCalled()
    unmount()
  })
})

describe('RailSegRow：键盘', () => {
  it('Enter 与空格跳转', () => {
    const { row, cbs, unmount } = renderRow()
    fireEvent.keyDown(row, { key: 'Enter' })
    fireEvent.keyDown(row, { key: ' ' })
    expect(cbs.onFocus).toHaveBeenCalledTimes(2)
    unmount()
  })

  it('F2 进改名', () => {
    const { row, cbs, unmount } = renderRow()
    fireEvent.keyDown(row, { key: 'F2' })
    expect(cbs.onStartEdit).toHaveBeenCalled()
    unmount()
  })

  it('编辑中不响应键盘跳转', () => {
    const { row, cbs, unmount } = renderRow({ editing: true })
    fireEvent.keyDown(row, { key: 'Enter' })
    expect(cbs.onFocus).not.toHaveBeenCalled()
    unmount()
  })
})

describe('RailSegRow：行内改名', () => {
  it('Enter 提交新名字', () => {
    const { cbs, unmount } = renderRow({ editing: true })
    const input = screen.getByRole('textbox', { name: '材料名' })
    fireEvent.change(input, { target: { value: '新名字' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(cbs.onRename).toHaveBeenCalledWith('新名字')
    unmount()
  })

  it('空名不提交', () => {
    const { cbs, unmount } = renderRow({ editing: true })
    const input = screen.getByRole('textbox', { name: '材料名' })
    fireEvent.change(input, { target: { value: '   ' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(cbs.onRename).not.toHaveBeenCalled()
    unmount()
  })

  it('Escape 取消改名（调 onStartEdit 切换回去）', () => {
    const { cbs, unmount } = renderRow({ editing: true })
    const input = screen.getByRole('textbox', { name: '材料名' })
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(cbs.onStartEdit).toHaveBeenCalled()
    expect(cbs.onRename).not.toHaveBeenCalled()
    unmount()
  })

  it('失焦提交', () => {
    const { cbs, unmount } = renderRow({ editing: true })
    const input = screen.getByRole('textbox', { name: '材料名' })
    fireEvent.change(input, { target: { value: '失焦名' } })
    fireEvent.blur(input)
    expect(cbs.onRename).toHaveBeenCalledWith('失焦名')
    unmount()
  })
})

describe('RailSegRow：拖拽', () => {
  it('dragstart 带上 si 并回调', () => {
    const { row, cbs, unmount } = renderRow({ si: 3 })
    const dt = { setData: vi.fn(), effectAllowed: '' }
    fireEvent.dragStart(row, { dataTransfer: dt })
    expect(dt.setData).toHaveBeenCalledWith('text/plain', '3')
    expect(cbs.onDragStartRow).toHaveBeenCalled()
    unmount()
  })

  it('dragover 上半 → before，下半 → after', () => {
    const { row, cbs, unmount } = renderRow()
    // jsdom 没有真实布局：直接给实例挂一个固定 rect，再用 createEvent 显式
    // 指定 currentTarget（fireEvent 的 currentTarget 指向事件派发节点，
    // 在原型方法被覆盖时不一定拿到我们想要的元素）
    Object.defineProperty(row, 'getBoundingClientRect', {
      configurable: true,
      value: () => ({
        top: 100,
        height: 40,
        bottom: 140,
        left: 0,
        right: 100,
        width: 100,
        x: 0,
        y: 100,
        toJSON: () => ({}),
      }),
    })

    const fire = (clientY: number) => {
      const e = createEvent.dragOver(row, { dataTransfer: { dropEffect: '' } })
      Object.defineProperty(e, 'clientY', { value: clientY })
      Object.defineProperty(e, 'currentTarget', { value: row })
      fireEvent(row, e)
    }

    fire(110)
    expect(cbs.onHoverDrop).toHaveBeenLastCalledWith('before')

    fire(130)
    expect(cbs.onHoverDrop).toHaveBeenLastCalledWith('after')
    unmount()
  })

  it('drop 与 dragend 各自回调', () => {
    const { row, cbs, unmount } = renderRow()
    fireEvent.drop(row, { dataTransfer: {} })
    fireEvent.dragEnd(row)
    expect(cbs.onDropRow).toHaveBeenCalled()
    expect(cbs.onDragEndRow).toHaveBeenCalled()
    unmount()
  })
})

describe('RailSegRow：视觉态', () => {
  it('未分类时用琥珀色提示', () => {
    const { row, unmount } = renderRow({ classified: false, seg: seg({ t: '' }) })
    expect(row.className).toContain('text-amber')
    unmount()
  })

  it('低置信度显示「复核」标', () => {
    const { container, unmount } = renderRow({ seg: seg({ reviewFlag: 'low_confidence' }) })
    expect(within(container).getByText('复核')).toBeTruthy()
    unmount()
  })

  it('插入线按 dropPos 定位（before 在顶部）', () => {
    const { container, unmount } = renderRow({ dropPos: 'before' })
    const line = container.querySelector('.bg-foreground\\/70') as HTMLElement
    expect(line.className).toContain('-top-')
    unmount()
  })

  it('dropPos=after 时插入线在底部', () => {
    const { container, unmount } = renderRow({ dropPos: 'after' })
    const line = container.querySelector('.bg-foreground\\/70') as HTMLElement
    expect(line.className).toContain('-bottom-')
    unmount()
  })

  it('长名字中部省略，保留尾部区分信息', () => {
    const longName = '1-授权委托书某甲某乙某丙某丁V1-P20.pdf'
    const { container, unmount } = renderRow({ seg: seg({ fn: longName }) })
    const text = container.textContent ?? ''
    expect(text).toContain('…')
    // 尾部区分信息（P20.pdf）必须保留
    expect(text).toContain('P20.pdf')
    unmount()
  })

  it('短名字不省略', () => {
    const { container, unmount } = renderRow({ seg: seg({ fn: '起诉状.pdf' }) })
    expect(container.textContent).toContain('起诉状.pdf')
    expect(container.textContent).not.toContain('…')
    unmount()
  })

  it('选中态带 data-selected', () => {
    const { row, unmount } = renderRow({ selected: true })
    expect(row.getAttribute('data-selected')).toBe('true')
    unmount()
  })
})

describe('RailSegRow：右键菜单', () => {
  it('菜单含重命名与选类型', () => {
    const { container, cbs, unmount } = renderRow()
    const menu = within(container).getByTestId('menu')
    fireEvent.click(within(menu).getByText('重命名'))
    expect(cbs.onStartEdit).toHaveBeenCalled()
    expect(menu.textContent).toContain('选类型')
    unmount()
  })
})
