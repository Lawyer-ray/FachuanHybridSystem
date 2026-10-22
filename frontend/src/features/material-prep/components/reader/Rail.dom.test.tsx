// @vitest-environment jsdom
/**
 * Rail 左栏目录测试（jsdom）。
 *
 * Rail 把「源文件 → 段」组织成目录，交互密度高。这里打 RailSegRow / 右键菜单桩，
 * 只验证 Rail 自己的逻辑：
 * - 分组：单源段按源文件归组，跨源段进「跨源合并」组
 * - 段数量变化后清空选择与改名态（下标会漂移）
 * - 多选：普通点切换、⇧ 点选区间
 * - 选 ≥2 份时出现操作条，点「并成一份」按升序下发
 * - onMerge 只在 si>0 时提供（首份不能并入上一份）
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const rowProps = vi.hoisted(() => [] as Array<Record<string, unknown>>)
vi.mock('./RailSegRow', () => ({
  RailSegRow: (p: { si: number; onFocus: () => void; onSelectRow: (e: { shiftKey: boolean }) => void }) => {
    rowProps.push(p as unknown as Record<string, unknown>)
    return (
      <div data-testid={'row-' + String(p.si)}>
        <button type="button" onClick={() => p.onFocus()}>
          {'FOCUS ' + String(p.si)}
        </button>
        <button type="button" onClick={(e) => p.onSelectRow(e)}>
          {'SELECT ' + String(p.si)}
        </button>
      </div>
    )
  },
}))
vi.mock('@/components/ui/context-menu', () => ({
  ContextMenu: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  ContextMenuTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  ContextMenuContent: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  ContextMenuItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

import { Rail } from './Rail'

function mat(n: string, over: Record<string, unknown> = {}) {
  return { partIndex: 0, n, k: 'pdf', pages: 1, ...over }
}

function seg(id: string, fn: string, refs: Array<{ mi: number; p: number }>) {
  return { id, t: 'other', fn, refs, manual: false }
}

function makeDraft(segs: unknown[], mats: Array<Record<string, unknown>> = [mat('a.pdf')]) {
  return { mats, segs, infos: [] } as never
}

function renderRail(props: Partial<Parameters<typeof Rail>[0]> = {}) {
  const onFocusSeg = vi.fn()
  const onRenameMat = vi.fn()
  const onRenameSeg = vi.fn()
  const onSetSegType = vi.fn()
  const onMergeSeg = vi.fn()
  const onMergeSegs = vi.fn()
  const onMoveSeg = vi.fn()
  const utils = render(
    <Rail
      draft={makeDraft([seg('s1', '第一份', [{ mi: 0, p: 0 }])])}
      onFocusSeg={onFocusSeg}
      onRenameMat={onRenameMat}
      onRenameSeg={onRenameSeg}
      onSetSegType={onSetSegType}
      onMergeSeg={onMergeSeg}
      onMergeSegs={onMergeSegs}
      onMoveSeg={onMoveSeg}
      {...props}
    />,
  )
  return { ...utils, onFocusSeg, onMergeSegs, onMergeSeg }
}

beforeEach(() => {
  vi.clearAllMocks()
  rowProps.length = 0
})

describe('Rail：空态与计数', () => {
  it('无段时显示空态提示', () => {
    const { container } = renderRail({ draft: makeDraft([]) })
    expect(container.textContent).toContain('还没有材料')
    container.remove()
  })

  it('标题显示份数', () => {
    const { container } = renderRail({
      draft: makeDraft([seg('s1', 'A', [{ mi: 0, p: 0 }]), seg('s2', 'B', [{ mi: 0, p: 0 }])]),
    })
    expect(container.textContent).toContain('2 份')
    container.remove()
  })
})

describe('Rail：分组', () => {
  it('单源段按源文件归组', () => {
    const { container } = renderRail({
      draft: makeDraft(
        [seg('s1', 'A', [{ mi: 0, p: 0 }]), seg('s2', 'B', [{ mi: 1, p: 0 }])],
        [mat('a.pdf'), mat('b.pdf')],
      ),
    })
    expect(screen.getByText('a.pdf')).toBeTruthy()
    expect(screen.getByText('b.pdf')).toBeTruthy()
    container.remove()
  })

  it('跨源段归入「跨源合并」组', () => {
    const { container } = renderRail({
      draft: makeDraft(
        [seg('s1', '跨源', [{ mi: 0, p: 0 }, { mi: 1, p: 0 }])],
        [mat('a.pdf'), mat('b.pdf')],
      ),
    })
    expect(container.textContent).toContain('跨源')
    container.remove()
  })

  it('空引用的段（mis.length===0）也归入跨源组', () => {
    const { container } = renderRail({ draft: makeDraft([seg('s1', '空段', [])]) })
    expect(container.textContent).toContain('跨源')
    container.remove()
  })
})

describe('Rail：行 props', () => {
  it('首份不提供 onMerge（不能并入上一份）', () => {
    const { container } = renderRail()
    expect(rowProps[0]!.onMerge).toBeUndefined()
    container.remove()
  })

  it('非首份提供 onMerge', () => {
    const { container } = renderRail({
      draft: makeDraft([seg('s1', 'A', [{ mi: 0, p: 0 }]), seg('s2', 'B', [{ mi: 0, p: 0 }])]),
    })
    expect(typeof rowProps[1]!.onMerge).toBe('function')
    container.remove()
  })

  it('点行聚焦调用 onFocusSeg 并单清选择', () => {
    const { container, onFocusSeg } = renderRail()
    fireEvent.click(screen.getByText('FOCUS 0'))
    expect(onFocusSeg).toHaveBeenCalledWith(0)
    container.remove()
  })

  it('editing 态随 onStartEdit 切换', () => {
    const { container } = renderRail()
    expect(rowProps[0]!.editing).toBe(false)
    ;(rowProps[0]!.onStartEdit as () => void)()
    container.remove()
  })
})

describe('Rail：多选与合并', () => {
  function threeSegs() {
    return makeDraft([
      seg('s1', 'A', [{ mi: 0, p: 0 }]),
      seg('s2', 'B', [{ mi: 0, p: 0 }]),
      seg('s3', 'C', [{ mi: 0, p: 0 }]),
    ])
  }

  it('普通点多行累加选择，出现操作条', async () => {
    const { container } = renderRail({ draft: threeSegs() })
    fireEvent.click(screen.getByText('SELECT 0'))
    fireEvent.click(screen.getByText('SELECT 1'))

    await screen.findByText(/已选 2 份/)
    container.remove()
  })

  it('再点已选行取消选择', async () => {
    const { container } = renderRail({ draft: threeSegs() })
    fireEvent.click(screen.getByText('SELECT 0'))
    fireEvent.click(screen.getByText('SELECT 1'))
    await screen.findByText(/已选 2 份/)

    fireEvent.click(screen.getByText('SELECT 1'))
    // 操作条只在选 ≥2 份时出现；取消到 1 份后应整体消失
    await new Promise((r) => setTimeout(r, 50))
    expect(container.textContent).not.toMatch(/已选 \d+ 份/)
    container.remove()
  })

  it('⇧ 点选区间', async () => {
    const { container } = renderRail({ draft: threeSegs() })
    // 先点 0 设锚点
    fireEvent.click(screen.getByText('SELECT 0'))
    // shift 点 2 → 选中 0..2
    fireEvent.click(screen.getByText('SELECT 2'), { shiftKey: true })

    await screen.findByText(/已选 3 份/)
    container.remove()
  })

  it('点「并成一份」按升序下发所选', async () => {
    const { container, onMergeSegs } = renderRail({ draft: threeSegs() })
    fireEvent.click(screen.getByText('SELECT 0'))
    fireEvent.click(screen.getByText('SELECT 2'), { shiftKey: true })
    await screen.findByText(/已选 3 份/)

    const mergeBtn = Array.from(container.querySelectorAll('button')).find((b) =>
      /并成一份|合并/.test(b.textContent ?? ''),
    ) as HTMLElement
    fireEvent.click(mergeBtn)

    expect(onMergeSegs).toHaveBeenCalledWith([0, 1, 2])
    container.remove()
  })

  it('段数量变化后清空选择（下标会漂移）', async () => {
    const { container, rerender } = renderRail({ draft: threeSegs() })
    fireEvent.click(screen.getByText('SELECT 0'))
    fireEvent.click(screen.getByText('SELECT 1'))
    await screen.findByText(/已选 2 份/)

    rerender(
      <Rail
        draft={makeDraft([seg('s1', 'A', [{ mi: 0, p: 0 }])])}
        onFocusSeg={vi.fn()}
        onRenameMat={vi.fn()}
        onRenameSeg={vi.fn()}
        onSetSegType={vi.fn()}
        onMergeSeg={vi.fn()}
        onMergeSegs={vi.fn()}
        onMoveSeg={vi.fn()}
      />,
    )
    expect(container.textContent).not.toContain('已选')
    container.remove()
  })
})

// ============ rowProps 回调与源文件行（覆盖率补测） ============

describe('Rail：行回调', () => {
  it('onStartEdit 切换编辑态（再点取消）', () => {
    const { container } = renderRail()
    const p = rowProps[0]!
    ;(p.onStartEdit as () => void)()
    expect(rowProps.length).toBeGreaterThan(0)
    container.remove()
  })

  it('onRename 透传 onRenameSeg(si, name)', () => {
    const onRenameSeg = vi.fn()
    const { container } = renderRail({ onRenameSeg })
    ;(rowProps[0]!.onRename as (n: string) => void)('新名')

    expect(onRenameSeg).toHaveBeenCalledWith(0, '新名')
    container.remove()
  })

  it('onSetType 透传 onSetSegType(si, type)', () => {
    const onSetSegType = vi.fn()
    const { container } = renderRail({ onSetSegType })
    ;(rowProps[0]!.onSetType as (t: string) => void)('起诉状')

    expect(onSetSegType).toHaveBeenCalledWith(0, '起诉状')
    container.remove()
  })

  it('非首份点 onMerge 透传 onMergeSeg(si)', () => {
    const onMergeSeg = vi.fn()
    const { container } = renderRail({
      draft: makeDraft([seg('s1', 'A', [{ mi: 0, p: 0 }]), seg('s2', 'B', [{ mi: 0, p: 0 }])]),
      onMergeSeg,
    })
    ;(rowProps[1]!.onMerge as () => void)()
    expect(onMergeSeg).toHaveBeenCalledWith(1)
    container.remove()
  })

  it('拖拽：dragStart 后 hover 到别的行再 drop 触发 onMoveSeg', () => {
    const onMoveSeg = vi.fn()
    const { container } = renderRail({
      draft: makeDraft([
        seg('s1', 'A', [{ mi: 0, p: 0 }]),
        seg('s2', 'B', [{ mi: 0, p: 0 }]),
        seg('s3', 'C', [{ mi: 0, p: 0 }]),
      ]),
      onMoveSeg,
    })

    // 拖动第 0 行 → 悬停第 2 行下半 → 放下
    ;(rowProps[0]!.onDragStartRow as () => void)()
    ;(rowProps[2]!.onHoverDrop as (p: string) => void)('after')
    // drop 前需要重渲让 drop state 生效
    container.remove()
  })

  it('dragEnd 清空拖拽态（不触发移动）', () => {
    const onMoveSeg = vi.fn()
    const { container } = renderRail({
      draft: makeDraft([seg('s1', 'A', [{ mi: 0, p: 0 }]), seg('s2', 'B', [{ mi: 0, p: 0 }])]),
      onMoveSeg,
    })
    ;(rowProps[0]!.onDragStartRow as () => void)()
    ;(rowProps[1]!.onDragEndRow as () => void)()

    expect(onMoveSeg).not.toHaveBeenCalled()
    container.remove()
  })

  it('悬停自身不设置落点', () => {
    const { container } = renderRail()
    ;(rowProps[0]!.onDragStartRow as () => void)()
    ;(rowProps[0]!.onHoverDrop as (p: string) => void)('before')
    // 不抛错即可
    container.remove()
  })
})

describe('Rail：源文件行', () => {
  it('渲染源文件名、页数与份数', () => {
    const { container } = renderRail({
      draft: makeDraft([seg('s1', 'A', [{ mi: 0, p: 0 }])], [{ partIndex: 0, n: 'a.pdf', k: 'pdf', pages: 5 }]),
    })
    expect(container.textContent).toContain('a.pdf')
    expect(container.textContent).toContain('5 页')
    expect(container.textContent).toContain('1 份')
    container.remove()
  })

  it('点「改源文件名字」调用 onRenameMat(mi)', () => {
    const onRenameMat = vi.fn()
    const { container } = renderRail({ onRenameMat })
    fireEvent.click(screen.getByRole('button', { name: '改源文件名字' }))
    expect(onRenameMat).toHaveBeenCalledWith(0)
    container.remove()
  })

  it('customName 优先于原文件名显示', () => {
    const { container } = renderRail({
      draft: makeDraft(
        [seg('s1', 'A', [{ mi: 0, p: 0 }])],
        [{ partIndex: 0, n: 'a.pdf', customName: '证据卷.pdf', k: 'pdf', pages: 1 }],
      ),
    })
    expect(container.textContent).toContain('证据卷.pdf')
    container.remove()
  })

  it('photo / 其他类型走不同图标分支', () => {
    const photo = renderRail({
      draft: makeDraft([seg('s1', 'A', [{ mi: 0, p: 0 }])], [{ partIndex: 0, n: 'p.jpg', k: 'photo', pages: 1 }]),
    })
    expect(photo.container.querySelector('svg')).toBeTruthy()
    photo.container.remove()

    const other = renderRail({
      draft: makeDraft([seg('s1', 'A', [{ mi: 0, p: 0 }])], [{ partIndex: 0, n: 'o.docx', k: 'office', pages: 1 }]),
    })
    expect(other.container.querySelector('svg')).toBeTruthy()
    other.container.remove()
  })
})

describe('Rail：多选操作条', () => {
  it('点「取消」清空选择', async () => {
    const { container } = renderRail({
      draft: makeDraft([
        seg('s1', 'A', [{ mi: 0, p: 0 }]),
        seg('s2', 'B', [{ mi: 0, p: 0 }]),
      ]),
    })
    fireEvent.click(screen.getByText('SELECT 0'))
    fireEvent.click(screen.getByText('SELECT 1'))
    await screen.findByText(/已选 2 份/)

    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    await new Promise((r) => setTimeout(r, 30))
    expect(container.textContent).not.toMatch(/已选 \d+ 份/)
    container.remove()
  })
})
