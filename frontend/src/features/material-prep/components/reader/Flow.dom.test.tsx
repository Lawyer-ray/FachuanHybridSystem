// @vitest-environment jsdom
/**
 * Flow 画布渲染测试（jsdom）。
 *
 * Flow 把草稿分段渲染成页卡网格。这里打下 PageCell / SegmentHeader 桩，
 * 只验证 Flow 自己的逻辑：
 * - 分段标题与页卡数量、页卡 props 的外键（mi/p/是否选中/是否多源隐藏文件名）
 * - 来源绿框按 "mi:p" 预算到对应页卡（infos.srcRef 有 rect 才生效）
 * - 单源包隐藏文件名（hideMatName）
 * - 右键菜单：右键未选中页=单删，右键选中页=整选区删
 * - 取字态把 pickPage / onOcrBox 透给页卡，非取字态不透
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// 布局数学用真实实现，保证 cols/页宽口径与生产一致
vi.mock('@/hooks/use-element-width', () => ({
  useElementWidth: () => [vi.fn(), 900, document.createElement('div')],
}))
vi.mock('../../draft', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../draft')>()
  return actual
})

const cellProps = vi.hoisted(() => [] as Array<Record<string, unknown>>)
const openMenuListeners = vi.hoisted(() => [] as Array<(e: unknown, mi: number, p: number) => void>)
vi.mock('./PageCell', () => ({
  PageCell: (p: { mi: number; p: number; onContextMenu?: (e: unknown, mi: number, p: number) => void }) => {
    cellProps.push(p as unknown as Record<string, unknown>)
    // 转发右键：菜单的内容（标题 / 删除范围）只在 Flow 里算，桩必须把事件递回去
    if (p.onContextMenu) openMenuListeners.push(p.onContextMenu)
    return (
      <div
        data-testid={'cell-' + String(p.mi) + '-' + String(p.p)}
        onContextMenu={(e) => p.onContextMenu?.(e, p.mi, p.p)}
      >
        {'CELL ' + String(p.mi) + ':' + String(p.p)}
      </div>
    )
  },
}))
vi.mock('./SegmentHeader', () => ({
  SegmentHeader: ({ seg, si, onRename, onMerge }: { seg: { fn: string }; si: number; onRename: (n: string) => void; onMerge: () => void }) => (
    <div>
      {`SEG_HEADER ${si} ${seg.fn}`}
      <button type="button" onClick={() => onRename('新段名')}>改段名</button>
      <button type="button" onClick={() => onMerge()}>并入上一份</button>
    </div>
  ),
}))
vi.mock('./PageContextMenu', () => ({
  PageContextMenu: ({ title, count, onDelete }: { title: string; count: number; onDelete: () => void }) => (
    <div>
      {`CTX_MENU ${title} count=${count}`}
      <button type="button" onClick={onDelete}>删除</button>
    </div>
  ),
}))

import { Flow } from './Flow'

function mat(n: string, pages: number) {
  return { partIndex: 0, n, k: 'pdf', pages }
}

function seg(id: string, fn: string, refs: Array<{ mi: number; p: number }>) {
  return { id, t: 'other', fn, refs, manual: false }
}

function makeDraft(over: Record<string, unknown> = {}) {
  return {
    mats: [mat('a.pdf', 2)],
    segs: [seg('s1', '第一份', [{ mi: 0, p: 0 }, { mi: 0, p: 1 }])],
    infos: [],
    ...over,
  } as never
}

function renderFlow(props: Partial<Parameters<typeof Flow>[0]> = {}) {
  const onRequestDelete = vi.fn()
  const onToggleSel = vi.fn()
  const onOcrBox = vi.fn()
  const utils = render(
    <Flow
      draft={makeDraft()}
      messageId={5}
      pickInfo={-1}
      focusedSeg={0}
      zoom={1}
      cols={1}
      selMode={false}
      selPages={[]}
      ocrPending={null}
      onOp={{ pickPage: vi.fn(), setValue: vi.fn() } as never}
      onToggleSel={onToggleSel}
      onOcrBox={onOcrBox}
      onRequestDelete={onRequestDelete}
      {...props}
    />,
  )
  return { ...utils, onRequestDelete, onToggleSel, onOcrBox }
}

beforeEach(() => {
  vi.clearAllMocks()
  cellProps.length = 0
  openMenuListeners.length = 0
})

describe('Flow：分段与页卡', () => {
  it('渲染分段标题与页卡', () => {
    const { container } = renderFlow()
    expect(screen.getByText('SEG_HEADER 0 第一份')).toBeTruthy()
    expect(screen.getByTestId('cell-0-0')).toBeTruthy()
    expect(screen.getByTestId('cell-0-1')).toBeTruthy()
    container.remove()
  })

  it('多分段按顺序渲染各自标题', () => {
    const draft = makeDraft({
      mats: [mat('a.pdf', 3)],
      segs: [
        seg('s1', '第一份', [{ mi: 0, p: 0 }]),
        seg('s2', '第二份', [{ mi: 0, p: 1 }, { mi: 0, p: 2 }]),
      ],
    })
    const { container } = renderFlow({ draft })
    expect(screen.getByText('SEG_HEADER 0 第一份')).toBeTruthy()
    expect(screen.getByText('SEG_HEADER 1 第二份')).toBeTruthy()
    expect(container.querySelectorAll('[data-testid^="cell-"]')).toHaveLength(3)
    container.remove()
  })

  it('messageId 透传给每个页卡', () => {
    const { container } = renderFlow({ messageId: 42 })
    expect(cellProps.every((p) => p.messageId === 42)).toBe(true)
    container.remove()
  })

  it('单源包隐藏文件名', () => {
    const { container } = renderFlow()
    expect(cellProps.every((p) => p.hideMatName === true)).toBe(true)
    container.remove()
  })

  it('多源包不隐藏文件名', () => {
    const draft = makeDraft({
      mats: [mat('a.pdf', 1), mat('b.pdf', 1)],
      segs: [seg('s1', '第一份', [{ mi: 0, p: 0 }, { mi: 1, p: 0 }])],
    })
    const { container } = renderFlow({ draft })
    expect(cellProps.every((p) => p.hideMatName === false)).toBe(true)
    container.remove()
  })
})

describe('Flow：选中态', () => {
  it('选中页标记 selected=true', () => {
    const { container } = renderFlow({ selMode: true, selPages: [{ mi: 0, p: 1 }] })
    const sel = cellProps.filter((p) => p.selected === true)
    expect(sel).toHaveLength(1)
    expect(sel[0]!.p).toBe(1)
    container.remove()
  })

  it('非选页模式时无页被标记选中', () => {
    const { container } = renderFlow({ selPages: [] })
    expect(cellProps.every((p) => p.selected === false)).toBe(true)
    container.remove()
  })

  it('selMode 透传给页卡', () => {
    const { container } = renderFlow({ selMode: true })
    expect(cellProps.every((p) => p.selModeActive === true)).toBe(true)
    container.remove()
  })
})

describe('Flow：取字态', () => {
  it('取字态把 pickPage 与 onOcrBox 透给页卡', () => {
    const onOcrBox = vi.fn()
    const { container } = renderFlow({ pickInfo: 0, onOcrBox })
    expect(cellProps.every((p) => typeof p.onPickPage === 'function')).toBe(true)
    expect(cellProps.every((p) => p.onOcrBox === onOcrBox)).toBe(true)
    expect(cellProps.every((p) => p.pickActive === true)).toBe(true)
    container.remove()
  })

  it('非取字态不透 pickPage（避免误触）', () => {
    const { container } = renderFlow({ pickInfo: -1 })
    expect(cellProps.every((p) => p.onPickPage === undefined)).toBe(true)
    expect(cellProps.every((p) => p.pickActive === false)).toBe(true)
    container.remove()
  })

  it('ocrPending 只透给命中那一页', () => {
    const rect = { x: 1, y: 2, w: 3, h: 4 }
    const { container } = renderFlow({ ocrPending: { mi: 0, p: 1, rect, text: '', loading: false } })
    const hit = cellProps.find((p) => p.p === 1 && p.mi === 0)
    const miss = cellProps.find((p) => p.p === 0 && p.mi === 0)
    expect(hit!.ocrRect).toEqual(rect)
    expect(miss!.ocrRect).toBeNull()
    container.remove()
  })
})

describe('Flow：来源标记', () => {
  it('infos.srcRef 有 rect 时把标记预算到对应页', () => {
    const rect = { x: 10, y: 20, w: 30, h: 40 }
    const draft = makeDraft({
      infos: [{ k: '标的额', v: '100', srcRef: { mi: 0, p: 1, rect } }],
    })
    const { container } = renderFlow({ draft })

    const page1 = cellProps.find((p) => p.mi === 0 && p.p === 1)
    const page0 = cellProps.find((p) => p.mi === 0 && p.p === 0)
    expect(page1!.marks).toHaveLength(1)
    expect((page1!.marks as Array<{ label: string }>)[0]!.label).toBe('标的额')
    expect(page0!.marks).toBeUndefined()
    container.remove()
  })

  it('srcRef 缺 rect 时不产生标记', () => {
    const draft = makeDraft({ infos: [{ k: '标的额', v: '100', srcRef: { mi: 0, p: 1 } }] })
    const { container } = renderFlow({ draft })
    expect(cellProps.every((p) => p.marks === undefined)).toBe(true)
    container.remove()
  })

  it('同一页多个字段的标记都保留（顺序按 infos）', () => {
    const rect = { x: 1, y: 1, w: 2, h: 2 }
    const draft = makeDraft({
      infos: [
        { k: '标的额', v: '1', srcRef: { mi: 0, p: 0, rect } },
        { k: '委托人', v: '张三', srcRef: { mi: 0, p: 0, rect } },
      ],
    })
    const { container } = renderFlow({ draft })
    const page0 = cellProps.find((p) => p.mi === 0 && p.p === 0)
    expect((page0!.marks as Array<{ label: string }>).map((m) => m.label)).toEqual(['标的额', '委托人'])
    container.remove()
  })
})

// ============ 切分按钮 / 多列 / 段开始条 / 右键菜单（覆盖率补测） ============

function renderFlowWithOp(over: Record<string, unknown> = {}) {
  const onRequestDelete = vi.fn()
  const splitSeg = vi.fn()
  const renameSeg = vi.fn()
  const mergeSeg = vi.fn()
  const utils = render(
    <Flow
      draft={makeDraft()}
      messageId={5}
      pickInfo={-1}
      focusedSeg={0}
      zoom={1}
      cols={1}
      selMode={false}
      selPages={[]}
      ocrPending={null}
      onOp={{ pickPage: vi.fn(), setValue: vi.fn(), splitSeg, renameSeg, mergeSeg } as never}
      onToggleSel={vi.fn()}
      onOcrBox={vi.fn()}
      onRequestDelete={onRequestDelete}
      {...over}
    />,
  )
  return { ...utils, onRequestDelete, splitSeg, renameSeg, mergeSeg }
}

describe('Flow：切分按钮', () => {
  it('单列多页时从第 2 页起出现「在此切开」按钮', () => {
    const { container } = renderFlowWithOp()
    const btns = Array.from(container.querySelectorAll('button')).filter(
      (b) => b.getAttribute('aria-label') === '在此切开',
    )
    // 2 页 → 第一页后有一个切分点
    expect(btns).toHaveLength(1)
    container.remove()
  })

  it('点切分按钮调用 splitSeg(si, ri)', () => {
    const { container, splitSeg } = renderFlowWithOp()
    const btn = Array.from(container.querySelectorAll('button')).find(
      (b) => b.getAttribute('aria-label') === '在此切开',
    ) as HTMLElement
    fireEvent.click(btn)
    expect(splitSeg).toHaveBeenCalledWith(0, 0)
    container.remove()
  })

  it('多列布局：每页（含第一页）都有页前切分按钮', () => {
    const { container } = renderFlowWithOp({ cols: 2 })
    const before = Array.from(container.querySelectorAll('button')).filter(
      (b) => b.getAttribute('aria-label') === '在此页前切开',
    )
    // 2 页、多列 → 第 2 页前一个
    expect(before.length).toBeGreaterThanOrEqual(1)
    container.remove()
  })

  it('多列页前切分按钮调用 splitSeg(si, ri-1)', () => {
    const { container, splitSeg } = renderFlowWithOp({ cols: 2 })
    const btn = Array.from(container.querySelectorAll('button')).find(
      (b) => b.getAttribute('aria-label') === '在此页前切开',
    ) as HTMLElement
    fireEvent.click(btn)
    expect(splitSeg).toHaveBeenCalledWith(0, 0)
    container.remove()
  })
})

describe('Flow：段开始条', () => {
  it('多源包显示「段开始 · 源文件名」', () => {
    const draft = makeDraft({
      mats: [mat('a.pdf', 1), mat('b.pdf', 1)],
      segs: [seg('s1', '第一份', [{ mi: 0, p: 0 }, { mi: 1, p: 0 }])],
    })
    const { container } = renderFlowWithOp({ draft })
    expect(container.textContent).toContain('段开始')
    expect(container.textContent).toContain('a.pdf')
    container.remove()
  })

  it('单源包不显示段开始条', () => {
    const { container } = renderFlowWithOp()
    expect(container.textContent).not.toContain('段开始')
    container.remove()
  })

  it('段开始条优先显示 customName', () => {
    const draft = makeDraft({
      mats: [{ partIndex: 0, n: 'a.pdf', customName: '证据卷.pdf', k: 'pdf', pages: 1 }, mat('b.pdf', 1)],
      segs: [seg('s1', '第一份', [{ mi: 0, p: 0 }, { mi: 1, p: 0 }])],
    })
    const { container } = renderFlowWithOp({ draft })
    expect(container.textContent).toContain('证据卷.pdf')
    container.remove()
  })
})

describe('Flow：段末尾切分', () => {
  it('段末尾有「在此切开」按钮并调用 splitSeg', () => {
    const { container, splitSeg } = renderFlowWithOp()
    const all = Array.from(container.querySelectorAll('button')).filter(
      (b) => b.getAttribute('aria-label') === '在此切开',
    )
    // 至少有一个（段末尾那个）
    expect(all.length).toBeGreaterThanOrEqual(1)
    fireEvent.click(all[all.length - 1]!)
    expect(splitSeg).toHaveBeenCalled()
    container.remove()
  })
})

// ============ 识别定位框 / 双框对照 / 脏引用（覆盖率补测） ============

function block(page: number, text: string, over: Record<string, unknown> = {}) {
  return { page, type: 'text', text, rect: { x: 0, y: 0, w: 1, h: 0.1, approx: false, precision: 'exact', ...over } }
}

describe('Flow：识别定位框（hits）', () => {
  /**
   * `seg.blocks[].page` 是**文档内绝对页号**，而段 refs 只覆盖自己那几页。
   * 按段起始页偏移后落不进 refs 的块必须丢掉：画出去就会出现在邻段页卡上，
   * 律师点开一段却在别的段看到高亮框，会以为分段错了。
   */
  it('块按段起始页偏移归位，段外的页不产生框', () => {
    const draft = makeDraft({
      mats: [mat('a.pdf', 5)],
      segs: [
        {
          id: 's1',
          t: 'other',
          fn: '第二段',
          refs: [{ mi: 0, p: 2 }, { mi: 0, p: 3 }],
          manual: false,
          blocks: [block(3, '本段第 2 页的块'), block(9, '越界块')],
        },
      ],
    })
    const { container } = renderFlow({ draft })

    const inRange = cellProps.find((p) => p.mi === 0 && p.p === 3)
    const outOfRange = cellProps.find((p) => p.mi === 0 && p.p === 2)
    expect((inRange!.hits as Array<{ label: string }>).map((h) => h.label)).toEqual(['本段第 2 页的块'])
    expect(outOfRange!.hits).toBeUndefined()
    container.remove()
  })

  it('旧草稿缺 precision 时退化成看 approx（不给假精度）', () => {
    const draft = makeDraft({
      mats: [mat('a.pdf', 2)],
      segs: [
        {
          id: 's1',
          t: 'other',
          fn: '第一份',
          refs: [{ mi: 0, p: 0 }, { mi: 0, p: 1 }],
          manual: false,
          blocks: [block(0, '整页近似', { approx: true, precision: undefined })],
        },
      ],
    })
    const { container } = renderFlow({ draft })
    const hits = cellProps.find((p) => p.mi === 0 && p.p === 0)!.hits as Array<{ precision: string }>
    expect(hits[0]!.precision).toBe('page')
    container.remove()
  })

  it('同一页多个块的 key 不撞（高亮靠 key 定位，撞了会同时亮两处）', () => {
    const draft = makeDraft({
      mats: [mat('a.pdf', 2)],
      segs: [
        {
          id: 's1',
          t: 'other',
          fn: '第一份',
          refs: [{ mi: 0, p: 0 }, { mi: 0, p: 1 }],
          manual: false,
          blocks: [block(0, 'A'), block(0, 'B')],
        },
      ],
    })
    const { container } = renderFlow({ draft })
    const hits = cellProps.find((p) => p.mi === 0 && p.p === 0)!.hits as Array<{ key: string }>
    expect(new Set(hits.map((h) => h.key)).size).toBe(2)
    container.remove()
  })
})

describe('Flow：双框对照（engineFocus）', () => {
  const disagreement = {
    page_no: 0,
    kind: 'char' as const,
    severity: 'high' as const,
    variants: [
      { engine: 'mineru' as const, text: '谭某某' },
      { engine: 'paddleocr_vl' as const, text: '谭某' },
    ],
    context: '借款人：谭某某',
    anchor_hit: true,
    similarity: 0.6,
    blocks: [
      { engine: 'mineru' as const, page_no: 0, text: '谭某某', rect: { x: 0, y: 0, w: 1, h: 0.1 }, block_type: 'text', approx: false },
    ],
  }

  /**
   * 只画一边就没有「对照」可言，但**一个框都没有的引擎也要保留分组**：
   * 渲染层会说明「这个引擎没拿到坐标」，律师才知道差异在哪一边，不会以为两框完全重叠。
   */
  it('两个引擎都保留分组，没框的那个是空数组', () => {
    const { container } = renderFlow({ engineFocus: disagreement })
    const page0 = cellProps.find((p) => p.mi === 0 && p.p === 0)
    const groups = page0!.engineBoxes as Array<{ variant: { engine: string }; blocks: unknown[] }>
    expect(groups.map((g) => g.variant.engine)).toEqual(['mineru', 'paddleocr_vl'])
    expect(groups[0]!.blocks).toHaveLength(1)
    expect(groups[1]!.blocks).toHaveLength(0)
    container.remove()
  })

  it('没有分歧可看时不画任何双框（常态页面不该有额外描边）', () => {
    const { container } = renderFlow({ engineFocus: null })
    expect(cellProps.every((p) => p.engineBoxes === null)).toBe(true)
    container.remove()
  })

  it('分歧页不在本段 refs 范围内时不画框（否则会画到邻段页卡上）', () => {
    const { container } = renderFlow({ engineFocus: { ...disagreement, page_no: 40 } })
    expect(cellProps.every((p) => p.engineBoxes === null)).toBe(true)
    container.remove()
  })
})

describe('Flow：脏引用兜底', () => {
  /**
   * 草稿是后端不透明 JSON，历史草稿里可能有指向已删素材的 ref。
   * `mats[ref.mi]` 为 undefined 时必须跳过而不是崩——一段脏数据不该让整个阅读器白屏。
   */
  it('ref 指向不存在的素材时跳过该页、其余照常渲染', () => {
    const draft = makeDraft({
      mats: [mat('a.pdf', 2)],
      segs: [seg('s1', '第一份', [{ mi: 0, p: 0 }, { mi: 9, p: 0 }])],
    })
    const { container } = renderFlow({ draft })
    expect(screen.getByTestId('cell-0-0')).toBeTruthy()
    expect(screen.queryByTestId('cell-9-0')).toBeNull()
    // 多列分支同一套守卫
    container.remove()
    const multi = renderFlow({ draft, cols: 2 })
    expect(multi.container.querySelector('[data-testid="cell-9-0"]')).toBeNull()
    multi.container.remove()
  })

  it('段 refs 为空时不显示段开始条（没有“从哪份材料开始”可说）', () => {
    const draft = makeDraft({
      mats: [mat('a.pdf', 1), mat('b.pdf', 1)],
      segs: [seg('s1', '空段', [])],
    })
    const { container } = renderFlow({ draft })
    expect(screen.getByText('SEG_HEADER 0 空段')).toBeTruthy()
    expect(container.textContent).not.toContain('段开始')
    container.remove()
  })
})

// ============ 右键菜单与段头回调（覆盖率补测） ============

describe('Flow：右键菜单与段头回调', () => {
  it('右键未选中页 → 菜单标题带文件名与页码，删除范围只有这一页', () => {
    const { container, onRequestDelete } = renderFlowWithOp()
    fireEvent.contextMenu(screen.getByTestId('cell-0-1'))

    expect(screen.getByText('CTX_MENU a.pdf · 第 1 页 count=1')).toBeTruthy()
    fireEvent.click(screen.getByText('删除'))
    // 右键单页就是单删：把整卷误删是这类菜单最容易出的错
    expect(onRequestDelete).toHaveBeenCalledWith([{ mi: 0, p: 1 }])
    container.remove()
  })

  it('右键落在选区内 → 菜单显示选中页数，删除范围是整个选区', () => {
    const selPages = [
      { mi: 0, p: 0 },
      { mi: 0, p: 1 },
    ]
    const { container, onRequestDelete } = renderFlowWithOp({ selMode: true, selPages })
    fireEvent.contextMenu(screen.getByTestId('cell-0-1'))

    expect(screen.getByText('CTX_MENU a.pdf · 第 1 页 count=2')).toBeTruthy()
    fireEvent.click(screen.getByText('删除'))
    expect(onRequestDelete).toHaveBeenCalledWith(selPages)
    container.remove()
  })

  it('菜单标题优先用律师改过的 customName', () => {
    const draft = makeDraft({
      mats: [{ partIndex: 0, n: 'a.pdf', customName: '证据卷.pdf', k: 'pdf', pages: 2 }],
    })
    const { container } = renderFlowWithOp({ draft })
    fireEvent.contextMenu(screen.getByTestId('cell-0-0'))
    expect(screen.getByText('CTX_MENU 证据卷.pdf · 第 0 页 count=1')).toBeTruthy()
    container.remove()
  })

  it('段头「改段名」调用 renameSeg(si, name)', () => {
    const { container, renameSeg } = renderFlowWithOp()
    fireEvent.click(screen.getByText('改段名'))
    expect(renameSeg).toHaveBeenCalledWith(0, '新段名')
    container.remove()
  })

  it('段头「并入上一份」调用 mergeSeg(si)', () => {
    const { container, mergeSeg } = renderFlowWithOp()
    fireEvent.click(screen.getByText('并入上一份'))
    expect(mergeSeg).toHaveBeenCalledWith(0)
    container.remove()
  })
})
