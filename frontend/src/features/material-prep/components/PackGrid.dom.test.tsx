// @vitest-environment jsdom
/**
 * PackGrid 测试（jsdom）。
 *
 * 材料包主区域的分支集中在五处：
 * - packs 映射 + data-pack-idx（两种呈现都要有，键盘导航依赖它）
 * - 离场方向类（left/right，两种呈现共用同一套动画类）
 * - viewMode='grid'：卡片网格（半径 300px 自适应）
 * - viewMode='list'：紧凑单行列表，操作按钮与右键菜单仍可用
 * - 空态：todo 指向顶部「新建材料包」按钮（不再有网格内虚线槽）；非 todo 保留占位
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
  }
  const props: GridProps = {
    gridRef: ref<HTMLDivElement>(),
    wrapRef: ref<HTMLDivElement>(),
    ringRef: ref<HTMLDivElement>(),
    packs: [pack(1)],
    tab: 'todo' as PackStatus,
    viewMode: 'grid',
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

describe('PackGrid：grid 形态', () => {
  it('容器是 300px 自适应网格，每包渲染为卡片（.mp-packet）', () => {
    const { container, unmount } = renderGrid({ viewMode: 'grid', packs: [pack(1), pack(2)] })
    const grid = container.querySelector('[data-pack-idx]')!.parentElement!
    expect(grid.className).toContain('grid-cols-[repeat(auto-fill,minmax(min(300px,100%),1fr))]')
    expect(container.querySelectorAll('.mp-packet')).toHaveLength(2)
    // 卡片形态保留缩略图带里的「页」信息与进度条，不渲染列表行的紧凑布局
    expect(screen.getAllByText('3 页')).toHaveLength(2)
    unmount()
  })

  it('悬停/操作按钮仍在卡内（不接 + 归案）', () => {
    const { unmount } = renderGrid({ viewMode: 'grid', packs: [pack(1, { segs: 2, named: 2 })] })
    const accept = screen.getByRole('button', { name: '归案' }) as HTMLButtonElement
    expect(accept.disabled).toBe(false)
    expect(screen.getByRole('button', { name: '不接' })).toBeTruthy()
    unmount()
  })
})

describe('PackGrid：list 形态', () => {
  it('每包渲染为一行（不渲染卡片 .mp-packet 缩略带），行高紧凑', () => {
    const { container, unmount } = renderGrid({ viewMode: 'list', packs: [pack(1), pack(2)] })
    const rows = container.querySelectorAll('[data-pack-idx]')
    expect(rows).toHaveLength(2)
    // 行容器是竖向 flex 排列，不再是卡片网格
    const list = rows[0]!.parentElement!
    expect(list.className).toContain('flex-col')
    expect(list.className).not.toContain('grid-cols-')
    const row = rows[0]!.querySelector('article')!
    expect(row.className).toContain('py-2.5')
    expect(row.className).toContain('text-[13px]')
    unmount()
  })

  it('data-pack-idx 按顺序给出，打开层按 index 回调', () => {
    const { container, cbs, unmount } = renderGrid({ viewMode: 'list', packs: [pack(1), pack(2), pack(3)] })
    const idxs = Array.from(container.querySelectorAll('[data-pack-idx]')).map((el) =>
      el.getAttribute('data-pack-idx'),
    )
    expect(idxs).toEqual(['0', '1', '2'])
    fireEvent.click(screen.getByRole('button', { name: '打开材料包：材料包 3' }))
    expect(cbs.onOpen).toHaveBeenCalledWith(2)
    unmount()
  })

  it('行内操作按钮可用（不接 / 归案）', () => {
    const { cbs, unmount } = renderGrid({ viewMode: 'list', packs: [pack(1, { segs: 2, named: 2 })] })
    fireEvent.click(screen.getByRole('button', { name: '不接' }))
    expect(cbs.onReject).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }))
    fireEvent.click(screen.getByRole('button', { name: '归案' }))
    expect(cbs.onAccept).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }))
    unmount()
  })

  it('未完成时行内「归案」禁用', () => {
    const { unmount } = renderGrid({ viewMode: 'list', packs: [pack(1, { segs: 2, named: 1 })] })
    expect((screen.getByRole('button', { name: '归案' }) as HTMLButtonElement).disabled).toBe(true)
    unmount()
  })

  it('右键菜单三项仍挂在每一行上', () => {
    const { cbs, unmount } = renderGrid({ viewMode: 'list', packs: [pack(1), pack(2)] })
    const menus = screen.getAllByTestId('menu')
    expect(menus).toHaveLength(2)
    fireEvent.click(within(menus[1]!).getByText(/重命名材料包/))
    expect(cbs.onRename).toHaveBeenCalledWith(expect.objectContaining({ id: 2 }))
    unmount()
  })

  it('离场动画类同样生效', () => {
    const right = renderGrid({ viewMode: 'list', packs: [pack(1)], leaving: { 1: 'right' } })
    expect(right.container.querySelector('.leave-right')).toBeTruthy()
    right.unmount()

    const left = renderGrid({ viewMode: 'list', packs: [pack(2)], leaving: { 2: 'left' } })
    expect(left.container.querySelector('.leave-left')).toBeTruthy()
    left.unmount()
  })

  it('行内展示状态徽章：未打开 / 未归类份数 / 已归案', () => {
    const opened = renderGrid({ viewMode: 'list', packs: [pack(1, { segs: 0, named: 0, status: 'todo' })] })
    expect(screen.getByText('未打开')).toBeTruthy()
    opened.unmount()

    const partial = renderGrid({ viewMode: 'list', packs: [pack(2, { segs: 3, named: 1 })] })
    expect(screen.getByText('2 份未归类')).toBeTruthy()
    partial.unmount()

    const done = renderGrid({ viewMode: 'list', tab: 'done', packs: [pack(3, { status: 'done', segs: 2, named: 2 })] })
    expect(screen.getByText('已归案')).toBeTruthy()
    done.unmount()
  })
})

describe('PackGrid：空态', () => {
  it('todo 空态指向顶部「新建材料包」按钮，且不再有网格内虚线新建槽', () => {
    const { container, unmount } = renderGrid({ tab: 'todo', packs: [] })
    expect(screen.getByText(/全部处理完了，拖入新材料，或点上方「新建材料包」/)).toBeTruthy()
    // 旧虚线槽是按钮；现在空态里不应再出现任何上传按钮
    expect(screen.queryByRole('button')).toBeNull()
    expect(container.querySelector('.border-dashed')).toBeTruthy()
    unmount()
  })

  it('todo 有包时不再渲染虚线新建槽', () => {
    const { unmount } = renderGrid({ tab: 'todo', packs: [pack(1)] })
    expect(screen.queryByText(/拖入材料，或点这里选文件/)).toBeNull()
    expect(screen.queryByText(/全部处理完了/)).toBeNull()
    unmount()
  })

  it('list 形态的空态不带 col-span-full（不是网格占位格）', () => {
    const { container, unmount } = renderGrid({ viewMode: 'list', tab: 'todo', packs: [] })
    expect(container.querySelector('.col-span-full')).toBeNull()
    unmount()
  })

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
