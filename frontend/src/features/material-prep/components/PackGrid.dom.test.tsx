// @vitest-environment jsdom
/**
 * PackGrid 测试（jsdom）。
 *
 * 材料包网格的分支集中在四处：
 * - packs 映射 + 离场方向类（left/right）
 * - todo 页签的虚线新建槽（空态与非空态两套文案）
 * - 非 todo 页签的空态提示（已归案 / 归档 两种文案）
 * - 右键菜单三项（打开 / 重命名 / 删除）
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/format', () => ({ friendlyTime: () => '10-20' }))
vi.mock('@/components/ui/context-menu', () => ({
  ContextMenu: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  ContextMenuTrigger: ({ children, className }: { children: React.ReactNode; className?: string }) => (
    <div className={className}>{children}</div>
  ),
  ContextMenuContent: ({ children }: { children: React.ReactNode }) => <div data-testid="menu">{children}</div>,
  ContextMenuItem: ({
    children,
    onSelect,
  }: {
    children: React.ReactNode
    onSelect?: () => void
  }) => (
    <button type="button" onClick={onSelect}>
      {children}
    </button>
  ),
  ContextMenuSeparator: () => <hr />,
}))

import { PackGrid } from './PackGrid'
import type { InboxMessage, PackStatus } from '../types'

function pack(id: number, over: Partial<InboxMessage> = {}): InboxMessage {
  return {
    id,
    subject: `材料包 ${id}`,
    status: 'todo',
    segs: 2,
    named: 1,
    mats: 1,
    pages: 3,
    types: [],
    source_name: '收件箱',
    received_at: '2026-10-20T10:00:00',
    ...over,
  } as InboxMessage
}

function ref<T>() {
  return { current: null } as React.RefObject<T | null>
}

type GridProps = React.ComponentProps<typeof PackGrid>

function renderGrid(over: Partial<GridProps> = {}) {
  const cbs = {
    onOpen: vi.fn(),
    onReject: vi.fn(),
    onAccept: vi.fn(),
    onRename: vi.fn(),
    onDelete: vi.fn(),
    onPickFiles: vi.fn(),
  }
  const props: GridProps = {
    gridRef: ref<HTMLDivElement>(),
    wrapRef: ref<HTMLDivElement>(),
    ringRef: ref<HTMLDivElement>(),
    packs: [pack(1)],
    tab: 'todo' as PackStatus,
    leaving: {},
    ...cbs,
    ...over,
  }
  const utils = render(<PackGrid {...props} />)
  return Object.assign(utils, { cbs, props })
}

describe('PackGrid：卡片与离场', () => {
  it('渲染每张卡并带 data-pack-idx', () => {
    const { container, unmount } = renderGrid({ packs: [pack(1), pack(2)] })
    expect(container.querySelectorAll('[data-pack-idx]')).toHaveLength(2)
    unmount()
  })

  it('离场方向为 right / left 时对应类名', () => {
    const right = renderGrid({ packs: [pack(1)], leaving: { 1: 'right' } })
    expect(right.container.querySelector('.leave-right')).toBeTruthy()
    right.unmount()

    const left = renderGrid({ packs: [pack(2)], leaving: { 2: 'left' } })
    expect(left.container.querySelector('.leave-left')).toBeTruthy()
    left.unmount()
  })

  it('无离场时不带离场类', () => {
    const { container, unmount } = renderGrid({ packs: [pack(1)] })
    expect(container.querySelector('.leave-right')).toBeNull()
    expect(container.querySelector('.leave-left')).toBeNull()
    unmount()
  })

  it('finished 判定：segs>0 且 named===segs', () => {
    // 已归类状态下「归案」按钮可用
    const { container, unmount } = renderGrid({ packs: [pack(1, { segs: 2, named: 2 })] })
    const accept = Array.from(container.querySelectorAll('button')).find((b) =>
      /归案/.test(b.textContent ?? ''),
    ) as HTMLButtonElement
    expect(accept.disabled).toBe(false)
    unmount()
  })
})

describe('PackGrid：右键菜单', () => {
  it('菜单三项都在', () => {
    const { unmount } = renderGrid()
    const menu = screen.getByTestId('menu')
    expect(within(menu).getByText(/打开材料包/)).toBeTruthy()
    expect(within(menu).getByText(/重命名材料包/)).toBeTruthy()
    expect(within(menu).getByText(/删除材料包/)).toBeTruthy()
    unmount()
  })

  it('点「打开材料包」按 index 回调', () => {
    const { cbs, unmount } = renderGrid({ packs: [pack(1), pack(2)] })
    const menus = screen.getAllByTestId('menu')
    fireEvent.click(within(menus[1]!).getByText(/打开材料包/))
    expect(cbs.onOpen).toHaveBeenCalledWith(1)
    unmount()
  })

  it('点「重命名材料包」带 pack 回调', () => {
    const { cbs, unmount } = renderGrid()
    fireEvent.click(within(screen.getByTestId('menu')).getByText(/重命名材料包/))
    expect(cbs.onRename).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }))
    unmount()
  })

  it('点「删除材料包」带 pack 回调', () => {
    const { cbs, unmount } = renderGrid()
    fireEvent.click(within(screen.getByTestId('menu')).getByText(/删除材料包/))
    expect(cbs.onDelete).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }))
    unmount()
  })
})

describe('PackGrid：todo 虚线槽', () => {
  it('todo 页签有包时显示「拖入材料，或点这里选文件」并回调', () => {
    const { cbs, unmount } = renderGrid({ tab: 'todo', packs: [pack(1)] })
    const slot = screen.getByRole('button', { name: /拖入材料，或点这里选文件/ })
    fireEvent.click(slot)
    expect(cbs.onPickFiles).toHaveBeenCalled()
    unmount()
  })

  it('todo 页签无包时显示「全部处理完了」文案', () => {
    const { unmount } = renderGrid({ tab: 'todo', packs: [] })
    expect(screen.getByRole('button', { name: /全部处理完了/ })).toBeTruthy()
    unmount()
  })

  it('非 todo 页签不渲染虚线槽', () => {
    const { unmount } = renderGrid({ tab: 'done', packs: [pack(1)] })
    expect(screen.queryByRole('button', { name: /拖入材料|全部处理完了/ })).toBeNull()
    unmount()
  })
})

describe('PackGrid：非 todo 空态', () => {
  it('done 页签空态文案为「已归案」', () => {
    const { unmount } = renderGrid({ tab: 'done', packs: [] })
    expect(document.body.textContent).toContain('已归案')
    unmount()
  })

  it('filed 页签空态文案为「归档」', () => {
    const { unmount } = renderGrid({ tab: 'filed', packs: [] })
    expect(document.body.textContent).toContain('归档')
    unmount()
  })

  it('非 todo 且非空时不显示空态', () => {
    const { unmount } = renderGrid({ tab: 'done', packs: [pack(1)] })
    expect(document.body.textContent).not.toContain('这里还没有')
    unmount()
  })
})
