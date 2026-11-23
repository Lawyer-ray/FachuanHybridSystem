// @vitest-environment jsdom
/**
 * DeskPage：统一工具栏 / 收件箱筛选透传 / 列表卡片切换（jsdom）。
 *
 * 从 DeskPage.dom.test.tsx 按被测单元拆出；共用桩与渲染入口见
 * `desk-page-test-harness.tsx`，用例本身逐字搬迁。
 */
import { act, fireEvent, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import {
  hookMock,
  inboxRow,
  pack,
  renderDesk,
  resetDeskPageMocks,
  setInboxRows,
  setup,
  syncMock,
  ui,
} from './desk-page-test-harness'

beforeEach(resetDeskPageMocks)

// ============ 统一工具栏（方案 B：一个容器 + 一条工具栏） ============

/** 主区域容器：key={stage} 那层，四阶段共用同一个 DESK_SURFACE_CLASS */
/**
 * 取「统一卡片容器」。
 *
 * 它现在是**工具栏 + 主区域共用的同一张卡**（工具栏是表头、主区域是卡身），
 * 不再是 .app-stage-enter 那一层——那层只负责阶段切换的淡入动画。
 * 用 data-testid 而非类名定位：卡片的视觉类名会调整，测的应该是"哪个元素"
 * 而不是"它长什么样"。
 */
function surfaceOf(container: HTMLElement): HTMLElement | null {
  return container.querySelector('[data-testid="desk-surface"]')
}

describe('DeskPage：主区域容器统一', () => {
  it('收件箱与材料包阶段共用同一个描边卡片容器', () => {
    setup([pack(1, 'todo')])
    const inbox = renderDesk('/material-prep')
    const inboxClass = surfaceOf(inbox.container)!.className
    inbox.unmount()

    const todo = renderDesk('/material-prep?stage=todo')
    const todoClass = surfaceOf(todo.container)!.className
    todo.unmount()

    // 切页签时"框"不能跳走：两个阶段的主区域必须是同一个容器样式
    expect(inboxClass).toBe(todoClass)
    expect(todoClass).toContain('rounded-[14px]')
    expect(todoClass).toContain('border')
    expect(todoClass).toContain('overflow-hidden')
  })

  it('页面上只有一张卡片：工具栏与主区域共用同一个容器', () => {
    // 曾经踩过的坑：工具栏和主区域各自套了一层 DESK_SURFACE_CLASS，
    // 页面上出现「两张上下叠放的独立卡片」，比统一之前更分裂。
    // 这里锁住"有且仅有一个描边卡片"，避免同样的错误再犯。
    setup([pack(1, 'todo')])
    const { container, unmount } = renderDesk('/material-prep?stage=todo')

    const cards = container.querySelectorAll('[data-testid="desk-surface"]')
    expect(cards).toHaveLength(1)

    const surface = cards[0]!
    // 工具栏与主区域都必须是这张卡的后代（而不是各自独立成卡）
    expect(surface.contains(container.querySelector('[data-testid="desk-toolbar"]'))).toBe(true)
    expect(surface.contains(container.querySelector('.app-stage-enter'))).toBe(true)
    unmount()
  })
})

describe('DeskPage：工具栏槽位随阶段变化', () => {
  it('收件箱阶段：工具栏在，显示来源药丸 / 未读 / 搜索 / 同步', () => {
    setup([pack(1, 'todo')])
    const { unmount, getByTestId, getByLabelText, getByRole } = renderDesk('/material-prep')

    const bar = getByTestId('desk-toolbar')
    expect(bar.getAttribute('data-stage')).toBe('inbox')
    // 工具栏在页签之下、主区域之外——两个阶段都不消失，才不会「像换了页面」
    expect(bar.closest('.app-stage-enter')).toBeNull()

    expect(getByRole('button', { name: '邮箱' })).toBeTruthy()
    expect(getByRole('button', { name: '法院短信' })).toBeTruthy()
    expect(getByRole('button', { name: /未读/ })).toBeTruthy()
    expect(getByLabelText('搜索收件箱')).toBeTruthy()
    expect(getByRole('button', { name: /同步全部/ })).toBeTruthy()
    // 收件箱是消息流：不提供「列表 / 卡片」切换
    expect(bar.textContent).not.toContain('卡片')
    unmount()
  })

  it('材料包阶段：工具栏在，显示列表/卡片切换，不显示收件箱控件', () => {
    setup([pack(1, 'todo')])
    const { unmount, getByTestId, queryByLabelText, queryByRole } = renderDesk('/material-prep?stage=todo')

    const bar = getByTestId('desk-toolbar')
    expect(bar.getAttribute('data-stage')).toBe('todo')
    expect(bar.textContent).toContain('列表')
    expect(bar.textContent).toContain('卡片')
    expect(queryByLabelText('搜索收件箱')).toBeNull()
    expect(queryByRole('button', { name: /未读/ })).toBeNull()
    expect(queryByRole('button', { name: /同步/ })).toBeNull()
    unmount()
  })

  it('工具栏本身不随阶段重挂（阶段切换时仍是同一条）', async () => {
    setup([pack(1, 'todo')])
    const { unmount, getByText, getByTestId, container } = renderDesk('/material-prep')
    const before = getByTestId('desk-toolbar')

    act(() => {
      getByText('切到待处理').click()
    })
    await waitFor(() => expect(getByTestId('desk-toolbar').getAttribute('data-stage')).toBe('todo'))
    // 同一个 DOM 节点（没有 key={stage} 在它身上）→ 切页签时工具栏不闪
    expect(container.querySelector('[data-testid="desk-toolbar"]')).toBe(before)
    unmount()
  })
})

describe('DeskPage：收件箱筛选上提并透传', () => {
  it('InboxView 收到受控的筛选 props（未读数不归它）', () => {
    setup([pack(1, 'todo')])
    setInboxRows([inboxRow(1, false), inboxRow(2, true), inboxRow(3, false)])
    const { unmount } = renderDesk('/material-prep')

    expect(ui.inbox).toMatchObject({
      source: 'all',
      search: '',
      unreadOnly: false,
    })
    // 未读数不能交给 InboxView：它的 rows 是按 unreadOnly 取的，
    // 打开「只看未读」后行里没有未读记录，在这里算必然恒为 0。
    expect(ui.inbox).not.toHaveProperty('unreadCount')
    expect(typeof (ui.inbox as { onSourceChange: unknown }).onSourceChange).toBe('function')
    unmount()
  })

  it('未读数由 DeskPage 算并显示在工具栏药丸上（与未读开关无关）', () => {
    setup([pack(1, 'todo')])
    setInboxRows([inboxRow(1, false), inboxRow(2, true), inboxRow(3, false)])
    const { unmount, getByRole } = renderDesk('/material-prep')

    // 3 行里 2 条未读 → 工具栏「未读」药丸上要显示 2。
    // 断言渲染结果而非 mock props：数字是给用户看的，直接验它有没有出现。
    const pill = getByRole('button', { name: /未读/ })
    expect(pill.textContent).toContain('2')
    unmount()
  })

  it('点工具栏药丸 / 未读 / 输入搜索：状态提升到 DeskPage 再回传 InboxView', () => {
    setup([pack(1, 'todo')])
    const { unmount, getByRole, getByLabelText } = renderDesk('/material-prep')

    fireEvent.click(getByRole('button', { name: '邮箱' }))
    fireEvent.click(getByRole('button', { name: /未读/ }))
    fireEvent.change(getByLabelText('搜索收件箱'), { target: { value: '执行裁定' } })

    // 筛选值必须落回 DeskPage 再喂给列表主体，否则就是"点了药丸但列表不动"
    expect(ui.inbox).toMatchObject({ source: 'imap', unreadOnly: true, search: '执行裁定' })
    unmount()
  })

  it('未读数取的是当前筛选结果，而不是全库总数', () => {
    setup([pack(1, 'todo')])
    hookMock.useInboxCounts.mockReturnValue(99) // 页签角标：全库条数，与未读无关
    setInboxRows([inboxRow(1, false)]) // 当前筛选下只有 1 条，且未读
    const { unmount, getByRole } = renderDesk('/material-prep')

    expect(getByRole('button', { name: /未读/ }).textContent).toContain('1')
    expect(getByRole('button', { name: /未读/ }).textContent).not.toContain('99')
    unmount()
  })

  it('未读数不受「只看未读」开关影响（取数参数里不带 unreadOnly）', () => {
    setup([pack(1, 'todo')])
    setInboxRows([inboxRow(1, false), inboxRow(2, true)])
    const { unmount, getByRole } = renderDesk('/material-prep')

    // 开关打开前后：都是同一个数字（这里 1 条未读）
    expect(getByRole('button', { name: /未读/ }).textContent).toContain('1')
    fireEvent.click(getByRole('button', { name: /未读/ }))
    expect(getByRole('button', { name: /未读/ }).textContent).toContain('1')

    // 根因断言：取数参数不得带 unreadOnly——带了就会只拿回未读行，数字自我坍缩
    for (const call of hookMock.useInboxList.mock.calls) {
      expect(call[0]).not.toHaveProperty('unreadOnly')
    }
    unmount()
  })

  it('工具栏同步按钮作用在当前档位（同步状态机按档位重建）', () => {
    setup([pack(1, 'todo')])
    const { unmount, getByRole } = renderDesk('/material-prep')
    fireEvent.click(getByRole('button', { name: '邮箱' }))
    expect(syncMock.useSyncSources).toHaveBeenLastCalledWith('imap')
    unmount()
  })
})

describe('DeskPage：列表 / 卡片切换', () => {
  it('材料包阶段默认按 STAGE_DEFAULT_VIEW 传 viewMode（网格 = grid）', () => {
    setup([pack(1, 'todo')])
    const { unmount } = renderDesk('/material-prep?stage=todo')
    expect(ui.grid!.viewMode).toBe('grid')
    unmount()
  })

  it('切换成列表后 PackGrid 收到 list', () => {
    setup([pack(1, 'todo')])
    const { unmount, getByTitle } = renderDesk('/material-prep?stage=todo')

    fireEvent.click(getByTitle('列表'))
    expect(ui.grid!.viewMode).toBe('list')
    unmount()
  })

  /**
   * 刷新 / 直达详情时「先闪一下列表页」的回归测试。
   *
   * 曾经的行为：URL 带 :id 进来，首帧 openId 仍是 null（要等 route-sync 的
   * effect 异步打开），DeskPage 据此把列表完整渲染一遍；紧接着阅读器才盖上来。
   * 用户看到的就是「先出现列表页，然后出现详情页」。
   *
   * 修法：用 URL 里的 :id 判「详情意图」，首帧就不挂载列表。
   */
  it('URL 带 :id 时首帧不渲染列表（避免刷新闪烁）', () => {
    setup([pack(1, 'todo'), pack(2, 'todo')])
    const { queryByText, unmount } = renderDesk('/material-prep/576?stage=todo')

    // 列表网格一个节点都不该出现
    expect(queryByText(/^GRID:/)).toBeNull()
    unmount()
  })

  it('无 :id 时列表照常渲染', () => {
    setup([pack(1, 'todo')])
    const { getByText, unmount } = renderDesk('/material-prep?stage=todo')

    expect(getByText('GRID:1')).toBeTruthy()
    unmount()
  })

  it('切换结果按阶段记住：去别的阶段再切回来仍是上次选的形态', async () => {
    setup([pack(1, 'todo'), pack(2, 'done')])
    const { unmount, getByTitle, getByText } = renderDesk('/material-prep?stage=todo')

    fireEvent.click(getByTitle('列表'))
    expect(ui.grid!.viewMode).toBe('list')

    // 换阶段：已归案仍用缺省（grid）——各阶段互不影响
    act(() => {
      getByText('切到已归案').click()
    })
    await waitFor(() => expect(ui.grid!.packs.map((p) => p.id)).toEqual([2]))
    expect(ui.grid!.viewMode).toBe('grid')

    // 切回待处理：用户的选择还在
    act(() => {
      getByText('切到待处理').click()
    })
    await waitFor(() => expect(ui.grid!.packs.map((p) => p.id)).toEqual([1]))
    expect(ui.grid!.viewMode).toBe('list')
    unmount()
  })
})
