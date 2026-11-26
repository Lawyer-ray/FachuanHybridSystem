// @vitest-environment jsdom
/**
 * RailSegRow 测试（jsdom）。
 *
 * 左栏一行的交互密度最高：
 * - 点击分派：普通点跳转；⌘/Ctrl/⇧ 点走多选；编辑中不响应
 * - 键盘：Enter/空格跳转、F2 进改名
 * - 双击进改名；改名 Enter 提交、Escape 取消、失焦提交；空名不提交
 * - 拖拽：dragstart 带上 si、dragover 按上下半给 before/after、drop/dragend 回调
 * - 视觉：未分类琥珀色、低置信度琥珀三角标、插入线位置、图形页灰图标标记
 * - 名字尾部（-P20.pdf 这类区分信息）固定保留，头部才参与截断
 * - 单段下载收在右键菜单里：行内不占宽度，但没有后端产物的行不给假入口
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

  /**
   * 「复核」两字常驻是左栏最贵的一笔开销：40 份材料里三十多行挂着它，每行固定
   * 吃掉 22px，等于从段名里直接拿走两个字。同一件事用 12px 的琥珀三角说即可，
   * 置信度和「该核对什么」放 tooltip。这里同时锁住两件事：标记在、文字不在。
   */
  it('低置信度用琥珀三角标，不再占「复核」两字的宽度', () => {
    const { container, unmount } = renderRow({ seg: seg({ reviewFlag: 'low_confidence', confidence: 0.42 }) })
    const mark = container.querySelector('[data-review-mark]') as HTMLElement
    expect(mark).toBeTruthy()
    expect(mark.getAttribute('title')).toContain('42%')
    expect(container.textContent).not.toContain('复核')
    unmount()
  })

  it('没有低置信度标记的行不出三角标', () => {
    const { container, unmount } = renderRow()
    expect(container.querySelector('[data-review-mark]')).toBeNull()
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

  it('覆盖图形页时挂灰图标标记，tooltip 给出页数', () => {
    const { container, unmount } = renderRow({ graphicPages: [147, 148] })
    const mark = container.querySelector('[data-graphic-mark]') as HTMLElement
    expect(mark).toBeTruthy()
    expect(mark.getAttribute('title')).toContain('含 2 页疑似图纸')
    // 不上彩色：与「删掉彩色圆点」的决定保持一致，只用灰色
    expect(mark.className).toContain('text-zinc-400')
    expect(mark.className).not.toContain('amber')
    unmount()
  })

  it('没有图形页时不挂标记（旧任务无 page_quality 也不报错）', () => {
    const { container, unmount } = renderRow()
    expect(container.querySelector('[data-graphic-mark]')).toBeNull()
    unmount()
  })

  it('改名字时不出图形页标记（不让图标挤在输入框旁）', () => {
    const { container, unmount } = renderRow({ graphicPages: [147], editing: true })
    expect(container.querySelector('[data-graphic-mark]')).toBeNull()
    unmount()
  })

  it('含证件页且字段缺失时，tooltip 点名缺了什么', () => {
    const { container, unmount } = renderRow({
      docHintPages: [{ page: 23, doc: 'id_card', missing: ['姓名', '身份证号'] }],
    })
    const mark = container.querySelector('[data-doc-mark]') as HTMLElement
    expect(mark).toBeTruthy()
    expect(mark.getAttribute('title')).toBe('含身份证页，姓名 / 身份证号未读出，请核对原图')
    // 不上彩色：与「删掉彩色圆点」的决定保持一致，只用灰色
    expect(mark.className).toContain('text-zinc-400')
    expect(mark.className).not.toContain('amber')
    unmount()
  })

  it('多种证件页时 tooltip 列出类型名并去重', () => {
    const { container, unmount } = renderRow({
      docHintPages: [
        { page: 23, doc: 'id_card', missing: ['姓名'] },
        { page: 24, doc: 'id_card', missing: [] },
        { page: 144, doc: 'property_cert', missing: ['权证号'] },
      ],
    })
    const mark = container.querySelector('[data-doc-mark]') as HTMLElement
    // 三种写法去重成两类；缺失字段跨页合并去重
    expect(mark.getAttribute('title')).toBe('含身份证 / 不动产权证页，姓名 / 权证号未读出，请核对原图')
    unmount()
  })

  /**
   * 关键回归：字段都在时**不能**提示「未读出」。
   *
   * 实测 p30 结婚证姓名两个人都读出来了（missing 为空数组），旧文案仍写
   * 「关键字段可能未读出」——律师翻原图发现字段好好的，以后就不信这个提示了。
   */
  it('证件页字段都在时，tooltip 不谎报「未读出」', () => {
    const { container, unmount } = renderRow({
      docHintPages: [{ page: 30, doc: 'marriage', missing: [] }],
    })
    const mark = container.querySelector('[data-doc-mark]') as HTMLElement
    expect(mark.getAttribute('title')).toBe('含结婚证页，建议核对原图')
    expect(mark.getAttribute('title')).not.toContain('未读出')
    unmount()
  })

  it('证件页与图形页同时存在时只显示证件图标（不两种并列）', () => {
    const { container, unmount } = renderRow({ docHintPages: [{ page: 23, doc: 'id_card', missing: [] }], graphicPages: [147] })
    expect(container.querySelector('[data-doc-mark]')).toBeTruthy()
    expect(container.querySelector('[data-graphic-mark]')).toBeNull()
    unmount()
  })

  it('没有证件页时不挂证件标记（旧任务无 doc_hints 也不报错）', () => {
    const { container, unmount } = renderRow({ docHintPages: [] })
    expect(container.querySelector('[data-doc-mark]')).toBeNull()
    unmount()
  })

  it('改名字时不出证件图标（不让图标挤在输入框旁）', () => {
    const { container, unmount } = renderRow({ docHintPages: [{ page: 23, doc: 'id_card', missing: ['姓名'] }], editing: true })
    expect(container.querySelector('[data-doc-mark]')).toBeNull()
    unmount()
  })

  /**
   * 两份「授权委托书」常常只差页号，区分信息全在尾部。以前是 `midEllipsis` 按
   * 字数挖中间、再交给 CSS 截尾部——字数上限远大于左栏宽度，CSS 把尾巴连同
   * 省略号一起裁掉，中部省略等于没生效。现在尾部是 `flex-none` 的独立节点，
   * 头部（flex-1 + truncate）怎么截都碰不到它。
   */
  it('长名字：头部参与截断，尾部区分信息固定保留', () => {
    const longName = '1-授权委托书某甲某乙某丙某丁V1-P20.pdf'
    const { container, unmount } = renderRow({ seg: seg({ fn: longName }) })
    const head = container.querySelector('[data-seg-name] > span:first-child') as HTMLElement
    const tail = container.querySelector('[data-seg-name-tail]') as HTMLElement
    expect(head.className).toContain('truncate')
    expect(tail.textContent).toBe('-P20.pdf')
    // 拆完不丢字：头 + 尾 = 原名
    expect(`${head.textContent ?? ''}${tail.textContent ?? ''}`).toBe(longName)
    unmount()
  })

  it('短名字不拆分（整段放得下，不必多一层 DOM）', () => {
    const { container, unmount } = renderRow({ seg: seg({ fn: '起诉状.pdf' }) })
    expect(container.textContent).toContain('起诉状.pdf')
    expect(container.querySelector('[data-seg-name-tail]')).toBeNull()
    unmount()
  })

  /**
   * 单段下载从行尾常驻搬进右键菜单：行内不再出现 PDF / MD 两个按钮，
   * 但「只要这一段、只要 PDF」仍然可达，且两个入口会各自回调对应类型。
   */
  it('行内不再出现 PDF / MD 常驻按钮', () => {
    const download = {
      checked: false,
      busyKind: null,
      disabled: false,
      onToggle: vi.fn(),
      onDownload: vi.fn(),
    }
    const { row, unmount } = renderRow({ download: download as never })
    expect(within(row).queryByRole('button', { name: 'PDF' })).toBeNull()
    expect(within(row).queryByRole('button', { name: 'MD' })).toBeNull()
    unmount()
  })

  it('右键菜单的「下载 PDF / 下载 Markdown」各自回调对应类型', () => {
    const download = {
      checked: false,
      busyKind: null,
      disabled: false,
      onToggle: vi.fn(),
      onDownload: vi.fn(),
    }
    const { container, unmount } = renderRow({ download: download as never })
    const menu = within(container).getByTestId('menu')
    fireEvent.click(within(menu).getByText('下载 PDF'))
    fireEvent.click(within(menu).getByText('下载 Markdown'))
    expect(download.onDownload.mock.calls).toEqual([['pdf'], ['md']])
    unmount()
  })

  it('没有后端产物的行不给下载入口（点了一定 404）', () => {
    const { container, unmount } = renderRow()
    const menu = within(container).getByTestId('menu')
    expect(menu.textContent).not.toContain('下载')
    unmount()
  })

  it('选中态带 data-selected', () => {
    const { row, unmount } = renderRow({ selected: true })
    expect(row.getAttribute('data-selected')).toBe('true')
    unmount()
  })
})

describe('RailSegRow：右键菜单', () => {
  it('菜单含重命名，且不再有「选类型」', () => {
    const { container, cbs, unmount } = renderRow()
    const menu = within(container).getByTestId('menu')
    fireEvent.click(within(menu).getByText('重命名'))
    expect(cbs.onStartEdit).toHaveBeenCalled()
    // 类型功能已移除：重命名是唯一归类入口
    expect(menu.textContent).not.toContain('选类型')
    unmount()
  })
})

/**
 * 徽标**互斥单选**：232px 的栏里放不下 4 个图标（段名会先被挤死），所以只渲染一个，
 * 按严重度排：ocrFailed > degenerate > columnAnomaly > doc > graphic。
 *
 * 理由：正文整页没有 > 正文不可信（云端退化、换本地 OCR）> 数字可能挂错表头 >
 * 字段没读出 > 内容不完整。这里把整条阶梯逐级钉住，改顺序必须同时改这组用例。
 */
describe('RailSegRow：质量标记的优先级阶梯', () => {
  const docHints = [{ page: 23, doc: 'id_card', missing: ['姓名'] }]

  function marks(container: HTMLElement) {
    return {
      ocr: container.querySelector('[data-ocr-failed-mark]'),
      degenerate: container.querySelector('[data-degenerate-mark]'),
      column: container.querySelector('[data-column-anomaly-mark]'),
      doc: container.querySelector('[data-doc-mark]'),
      graphic: container.querySelector('[data-graphic-mark]'),
    }
  }

  it('取字失败与退化同时存在 → 显示取字失败（正文整页没有，比换了识别路径更严重）', () => {
    const { container, unmount } = renderRow({ ocrFailedPages: [3], degeneratePages: [12] })
    const m = marks(container)
    expect(m.ocr).toBeTruthy()
    expect(m.degenerate).toBeNull()
    unmount()
  })

  it('退化优先于列数突变、证件、图纸', () => {
    const { container, unmount } = renderRow({
      degeneratePages: [12],
      columnAnomalyPages: [7],
      docHintPages: docHints,
      graphicPages: [147],
    })
    const m = marks(container)
    expect(m.degenerate).toBeTruthy()
    expect(m.column).toBeNull()
    expect(m.doc).toBeNull()
    expect(m.graphic).toBeNull()
    unmount()
  })

  it('列数突变优先于证件、图纸', () => {
    const { container, unmount } = renderRow({
      columnAnomalyPages: [7],
      docHintPages: docHints,
      graphicPages: [147],
    })
    const m = marks(container)
    expect(m.column).toBeTruthy()
    expect(m.doc).toBeNull()
    expect(m.graphic).toBeNull()
    unmount()
  })

  it('退化 / 列数突变都用灰图标（事实陈述，不上琥珀），tooltip 给出页号与后果', () => {
    const first = renderRow({ degeneratePages: [12, 34] })
    const degenerate = first.container.querySelector('[data-degenerate-mark]') as HTMLElement
    expect(degenerate.className).toContain('text-zinc-400')
    expect(degenerate.className).not.toContain('amber')
    expect(degenerate.getAttribute('title')).toBe(
      '含 2 页云端取字判为退化（P12、P34），已改用本地识别兜底 · 建议核对原页',
    )
    first.unmount()

    const second = renderRow({ columnAnomalyPages: [7] })
    const column = second.container.querySelector('[data-column-anomaly-mark]') as HTMLElement
    expect(column.className).toContain('text-zinc-400')
    expect(column.className).not.toContain('amber')
    expect(column.getAttribute('title')).toBe(
      '含 1 页表格列数与上一页不同（P7），数字可能挂错表头 · 请核对数字表头',
    )
    second.unmount()
  })

  it('旧任务（两个新信号都缺省）不出现任何新标记', () => {
    const { container, unmount } = renderRow()
    expect(container.querySelector('[data-degenerate-mark]')).toBeNull()
    expect(container.querySelector('[data-column-anomaly-mark]')).toBeNull()
    unmount()
  })

  it('改名字时也不出新标记（不让图标挤在输入框旁）', () => {
    const { container, unmount } = renderRow({ degeneratePages: [12], columnAnomalyPages: [7], editing: true })
    expect(container.querySelector('[data-degenerate-mark]')).toBeNull()
    expect(container.querySelector('[data-column-anomaly-mark]')).toBeNull()
    unmount()
  })
})
