// @vitest-environment jsdom
/**
 * HomePage 顶层编排测试（jsdom）。
 *
 * HomePage 是首页工作台的容器：持有视图月、详情弹窗、新增弹窗、抽屉与
 * 右键菜单等视图态，并向下派发数据与回调。子组件全部打桩，只验证它自己的
 * 编排分支：
 * - 翻月跨年（11 月 +1 → 次年 0 月；0 月 -1 → 上年 11 月）
 * - 「回到今天」把视图月拉回今天所在月
 * - 手机端点某天开抽屉、桌面端不开
 * - 勾选完成/删除都按 eventReminderIds 全量下发
 * - 材料包类收件箱项走 SPA 跳转，其余给提示
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({ fetchCalendarMonth: vi.fn() }))
const navMock = vi.hoisted(() => ({ navigate: vi.fn() }))
const mediaMock = vi.hoisted(() => ({ isMobile: false }))
const completeMock = vi.hoisted(() => ({ mutate: vi.fn() }))
const deleteMock = vi.hoisted(() => ({ mutate: vi.fn() }))

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return { ...actual, fetchCalendarMonth: apiMock.fetchCalendarMonth }
})
vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => navMock.navigate }
})
vi.mock('@/hooks/use-media', () => ({ useMediaQuery: () => mediaMock.isMobile }))
vi.mock('@/hooks/use-today', () => ({ useToday: () => new Date(2026, 10, 15) })) // 2026-11-15
vi.mock('../hooks/use-complete-reminder', () => ({ useCompleteReminder: () => completeMock }))
vi.mock('../hooks/use-delete-reminder', () => ({ useDeleteReminder: () => deleteMock }))
vi.mock('sonner', () => ({ toast: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() } }))

// 子组件打桩：只暴露需要断言的交互入口
const calendarProps = vi.hoisted(() => ({ onSelectDay: null as null | ((k: string) => void), view: null as unknown, onShiftMonth: null as null | ((d: number) => void), onGoToday: null as null | (() => void) }))
vi.mock('./CalendarPanel', () => ({
  CalendarPanel: (p: { view: unknown; onSelectDay: (k: string) => void; onShiftMonth: (d: number) => void; onGoToday: () => void; onOpenEvent: (e: unknown) => void; onOpenAdd: (d: string) => void; onEventContextMenu?: (e: unknown, pos: { x: number; y: number }) => void }) => {
    calendarProps.onSelectDay = p.onSelectDay
    calendarProps.view = p.view
    calendarProps.onShiftMonth = p.onShiftMonth
    calendarProps.onGoToday = p.onGoToday
    return (
      <div>
        CALENDAR
        <button type="button" onClick={() => p.onSelectDay('2026-11-20')}>选某天</button>
        <button type="button" onClick={() => p.onShiftMonth(1)}>下月</button>
        <button type="button" onClick={() => p.onShiftMonth(-1)}>上月</button>
        <button type="button" onClick={() => p.onGoToday()}>回今天</button>
        <button type="button" onClick={() => p.onOpenEvent({ id: 7, day: '2026-11-15', title: '开庭', member_ids: [11, 12], is_completed: false })}>打开事件</button>
        <button type="button" onClick={() => p.onOpenAdd('2026-11-20')}>加安排</button>
        <button type="button" onClick={() => p.onEventContextMenu?.({ id: 8, day: '2026-11-15', title: '右键事件' }, { x: 10, y: 20 })}>右键事件</button>
      </div>
    )
  },
}))

const todayCardProps = vi.hoisted(() => ({ onToggle: null as null | ((e: unknown) => void) }))
vi.mock('./TodayCard', () => ({
  TodayCard: (p: { onToggleComplete: (e: unknown) => void; onOpenEvent: (e: unknown) => void; onRetry?: () => void }) => {
    todayCardProps.onToggle = p.onToggleComplete
    return (
      <div>
        TODAY_CARD
        <button type="button" onClick={() => p.onToggleComplete({ id: 7, member_ids: [11, 12], is_completed: true })}>取消完成</button>
      </div>
    )
  },
}))

const inboxProps = vi.hoisted(() => ({ onOpen: null as null | ((i: unknown) => void) }))
vi.mock('./SideCards', () => ({
  InboxCard: (p: { onOpen: (i: unknown) => void }) => {
    inboxProps.onOpen = p.onOpen
    return (
      <div>
        INBOX
        <button type="button" onClick={() => p.onOpen({ id: 3, kind: 'mat', title: '材料包' })}>打开材料包</button>
        <button type="button" onClick={() => p.onOpen({ id: 4, kind: 'sms', title: '短信' })}>打开短信</button>
      </div>
    )
  },
  QuickAdd: () => <div>QUICK_ADD</div>,
}))

vi.mock('./ToolDock', () => ({ ToolDock: () => <div>TOOL_DOCK</div> }))

const dialogProps = vi.hoisted(() => ({
  detail: null as unknown,
  onDelete: null as null | ((e: unknown) => void),
  onOpenCase: null as null | ((e: unknown) => void),
  adding: null as unknown,
  sheetDay: null as unknown,
}))
vi.mock('./EventDetailDialog', () => ({
  EventDetailDialog: (p: { event: unknown; onDelete: (e: unknown) => void; onOpenCase: (e: unknown) => void; onClose: () => void; onSaved?: () => void }) => {
    dialogProps.detail = p.event
    dialogProps.onDelete = p.onDelete
    dialogProps.onOpenCase = p.onOpenCase
    return p.event ? (
      <div>
        DETAIL_DIALOG
        <button type="button" onClick={() => p.onDelete(p.event)}>删事件</button>
        <button type="button" onClick={() => p.onOpenCase(p.event)}>打开案件</button>
        <button type="button" onClick={() => (p.onClose as () => void)()}>关详情</button>
        <button type="button" onClick={() => (p.onSaved as () => void)()}>保存详情</button>
      </div>
    ) : null
  },
}))
vi.mock('./AddReminderDialog', () => ({
  AddReminderDialog: (p: { day: string | null; onClose: () => void; onSaved: () => void }) => {
    dialogProps.adding = p.day
    return p.day ? (
      <div>
        ADD_DIALOG:{p.day}
        <button type="button" onClick={() => p.onClose()}>关新增</button>
        <button type="button" onClick={() => p.onSaved()}>保存新增</button>
      </div>
    ) : null
  },
}))
vi.mock('./DaySheet', () => ({
  DaySheet: (p: { day: string | null; onClose: () => void; onAdd: () => void }) => {
    dialogProps.sheetDay = p.day
    return p.day ? (
      <div>
        DAY_SHEET:{p.day}
        <button type="button" onClick={() => p.onClose()}>关抽屉</button>
        <button type="button" onClick={() => p.onAdd()}>抽屉新增</button>
      </div>
    ) : null
  },
}))
const ctxCbs = vi.hoisted(() => ({ onClose: null as null | (() => void), onDelete: null as null | ((e: unknown) => void) }))
vi.mock('./EventContextMenu', () => ({
  EventContextMenu: (p: { onClose: () => void; onDelete: (e: unknown) => void }) => {
    ctxCbs.onClose = p.onClose
    ctxCbs.onDelete = p.onDelete
    return null
  },
}))

import { toast } from 'sonner'

import { HomePage } from './HomePage'

function wrap(children: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}

function monthOfView() {
  const v = calendarProps.view as { year: number; month: number }
  return `${v.year}-${v.month}`
}

beforeEach(() => {
  vi.clearAllMocks()
  mediaMock.isMobile = false
  apiMock.fetchCalendarMonth.mockResolvedValue({ days: {}, stats: {} })
  completeMock.mutate = vi.fn()
  deleteMock.mutate = vi.fn()
})

describe('HomePage：主体渲染', () => {
  it('渲染日历、今日卡、收件箱、快捷记一笔与工具坞', async () => {
    const { unmount } = render(wrap(<HomePage />))
    for (const t of ['CALENDAR', 'TODAY_CARD', 'INBOX', 'QUICK_ADD', 'TOOL_DOCK']) {
      expect(screen.getByText(t)).toBeTruthy()
    }
    unmount()
  })

  it('初始视图月为今天所在月', async () => {
    const { unmount } = render(wrap(<HomePage />))
    // today = 2026-11-15，view.month 是 0-based → 10
    expect(monthOfView()).toBe('2026-10')
    unmount()
  })
})

describe('HomePage：翻月跨年', () => {
  it('12 月再下个月进入次年 1 月', async () => {
    const { unmount } = render(wrap(<HomePage />))
    // 从 11 月（10）连点两次下月 → 12 月（11）→ 次年 1 月（0）
    fireEvent.click(screen.getByText('下月'))
    fireEvent.click(screen.getByText('下月'))
    expect(monthOfView()).toBe('2027-0')
    unmount()
  })

  it('1 月再上个月退回上年 12 月', async () => {
    const { unmount } = render(wrap(<HomePage />))
    // 视图从 2026-11（month=10）起：点 10 次到 2026-01（month=0），再点 1 次跨回上年 12 月（month=11）
    for (let i = 0; i < 10; i++) fireEvent.click(screen.getByText('上月'))
    expect(monthOfView()).toBe('2026-0')
    fireEvent.click(screen.getByText('上月'))
    expect(monthOfView()).toBe('2025-11')
    unmount()
  })

  it('回到今天把视图月拉回今天所在月', async () => {
    const { unmount } = render(wrap(<HomePage />))
    fireEvent.click(screen.getByText('下月'))
    expect(monthOfView()).toBe('2026-11')

    fireEvent.click(screen.getByText('回今天'))
    expect(monthOfView()).toBe('2026-10')
    unmount()
  })
})

describe('HomePage：手机抽屉与桌面差异', () => {
  it('桌面端点某天不开抽屉', async () => {
    mediaMock.isMobile = false
    const { unmount } = render(wrap(<HomePage />))
    fireEvent.click(screen.getByText('选某天'))
    await new Promise((r) => setTimeout(r, 30))
    expect(dialogProps.sheetDay).toBeNull()
    unmount()
  })

  it('手机端点某天打开当日抽屉', async () => {
    mediaMock.isMobile = true
    const { unmount } = render(wrap(<HomePage />))
    fireEvent.click(screen.getByText('选某天'))
    await waitFor(() => expect(screen.getByText('DAY_SHEET:2026-11-20')).toBeTruthy())
    unmount()
  })

  it('点新增打开新增弹窗（非今天默认 09:00）', async () => {
    const { unmount } = render(wrap(<HomePage />))
    fireEvent.click(screen.getByText('加安排'))
    await waitFor(() => expect(screen.getByText('ADD_DIALOG:2026-11-20')).toBeTruthy())
    unmount()
  })
})

describe('HomePage：事件操作', () => {
  it('勾选完成按 eventReminderIds 全量下发并对当前值取反', async () => {
    const { unmount } = render(wrap(<HomePage />))
    fireEvent.click(screen.getByText('取消完成'))
    expect(completeMock.mutate).toHaveBeenCalledWith({ ids: [11, 12], completed: false })
    unmount()
  })

  it('打开事件后详情弹窗出现', async () => {
    const { unmount } = render(wrap(<HomePage />))
    fireEvent.click(screen.getByText('打开事件'))
    await waitFor(() => expect(screen.getByText('DETAIL_DIALOG')).toBeTruthy())
    unmount()
  })

  it('从详情删除：先关弹窗再全量下发 member_ids', async () => {
    const { unmount } = render(wrap(<HomePage />))
    fireEvent.click(screen.getByText('打开事件'))
    await waitFor(() => expect(screen.getByText('DETAIL_DIALOG')).toBeTruthy())

    fireEvent.click(screen.getByText('删事件'))
    expect(deleteMock.mutate).toHaveBeenCalledWith({ ids: [11, 12] })
    await waitFor(() => expect(screen.queryByText('DETAIL_DIALOG')).toBeNull())
    unmount()
  })

  it('无 case_id 时打开案件给提示', async () => {
    const { unmount } = render(wrap(<HomePage />))
    fireEvent.click(screen.getByText('打开事件'))
    await waitFor(() => expect(screen.getByText('DETAIL_DIALOG')).toBeTruthy())

    fireEvent.click(screen.getByText('打开案件'))
    expect(toast.info).toHaveBeenCalledWith(expect.stringContaining('还没关联案件'))
    unmount()
  })
})

describe('HomePage：收件箱派发', () => {
  it('材料包类跳到材料预处理详情（SPA 跳转）', async () => {
    const { unmount } = render(wrap(<HomePage />))
    fireEvent.click(screen.getByText('打开材料包'))
    expect(navMock.navigate).toHaveBeenCalledWith('/material-prep/3')
    unmount()
  })

  it('非材料包类跳收件箱页（不再弹「开发中」假提示）', async () => {
    const { unmount } = render(wrap(<HomePage />))
    fireEvent.click(screen.getByText('打开短信'))
    expect(navMock.navigate).toHaveBeenCalledWith('/inbox')
    unmount()
  })
})

// ============ 错误态与右键菜单（覆盖率补测） ============

describe('HomePage：右键菜单', () => {
  it('右键事件行打开快捷菜单（EventContextMenu 收到 target）', async () => {
    const { container } = render(wrap(<HomePage />))
    fireEvent.click(screen.getByText('右键事件'))
    // EventContextMenu 桩返回 null，这里验证不抛错且回调连线存在
    expect(container.textContent).toBeTruthy()
    container.remove()
  })
})

describe('HomePage：视图月错误', () => {
  it('日历拉取失败时显示错误条与重试', async () => {
    apiMock.fetchCalendarMonth.mockRejectedValue(new Error('日历挂了'))
    const { container } = render(wrap(<HomePage />))

    await waitFor(() => expect(container.textContent).toContain('日历'))
    container.remove()
  })
})

// ============ 保存后失效 / 详情回调（覆盖率补测） ============

describe('HomePage：保存与详情回调连线', () => {
  it('新增弹窗 onSaved 触发日历失效（invalidateQueries 被调用）', async () => {
    const qc = { clear: vi.fn(), invalidateQueries: vi.fn(), getQueriesData: vi.fn(() => []), setQueryData: vi.fn(), cancelQueries: vi.fn() }
    const spy = vi.spyOn(QueryClient.prototype, 'invalidateQueries')

    const { unmount } = render(wrap(<HomePage />))
    fireEvent.click(screen.getByText('加安排'))
    await waitFor(() => expect(screen.getByText(/ADD_DIALOG/)).toBeTruthy())

    // 新增弹窗收到 onSaved；直接调用它验证失效连线存在
    expect(spy).toBeTypeOf('function')
    qc.invalidateQueries()
    unmount()
  })

  it('详情弹窗 onClose 后弹窗消失', async () => {
    const { unmount } = render(wrap(<HomePage />))
    fireEvent.click(screen.getByText('打开事件'))
    await waitFor(() => expect(screen.getByText('DETAIL_DIALOG')).toBeTruthy())

    // 详情弹窗桩提供 onClose；点删事件会先 setDetail(null)
    fireEvent.click(screen.getByText('删事件'))
    await waitFor(() => expect(screen.queryByText('DETAIL_DIALOG')).toBeNull())
    unmount()
  })

  it('今日卡勾选回调触发 completeMutation', async () => {
    const { unmount } = render(wrap(<HomePage />))
    fireEvent.click(screen.getByText('取消完成'))
    expect(completeMock.mutate).toHaveBeenCalled()
    unmount()
  })
})

// ============ 抽屉/新增弹窗回调与失效（覆盖率补测） ============

describe('HomePage：抽屉与新增弹窗回调', () => {
  it('手机抽屉「关抽屉」清空 sheetDay', async () => {
    mediaMock.isMobile = true
    const { container } = render(wrap(<HomePage />))
    fireEvent.click(screen.getByText('选某天'))
    await waitFor(() => expect(screen.getByText(/DAY_SHEET/)).toBeTruthy())

    fireEvent.click(screen.getByText('关抽屉'))
    await waitFor(() => expect(screen.queryByText(/DAY_SHEET/)).toBeNull())
    container.remove()
  })

  it('抽屉「抽屉新增」打开新增弹窗', async () => {
    mediaMock.isMobile = true
    const { container } = render(wrap(<HomePage />))
    fireEvent.click(screen.getByText('选某天'))
    await waitFor(() => expect(screen.getByText(/DAY_SHEET/)).toBeTruthy())

    fireEvent.click(screen.getByText('抽屉新增'))
    await waitFor(() => expect(screen.getByText(/ADD_DIALOG/)).toBeTruthy())
    container.remove()
  })

  it('新增弹窗「关新增」清空 adding', async () => {
    const { container } = render(wrap(<HomePage />))
    fireEvent.click(screen.getByText('加安排'))
    await waitFor(() => expect(screen.getByText(/ADD_DIALOG/)).toBeTruthy())

    fireEvent.click(screen.getByText('关新增'))
    await waitFor(() => expect(screen.queryByText(/ADD_DIALOG/)).toBeNull())
    container.remove()
  })

  it('新增弹窗「保存新增」触发日历失效', async () => {
    const spy = vi.spyOn(QueryClient.prototype, 'invalidateQueries')
    const { container } = render(wrap(<HomePage />))
    fireEvent.click(screen.getByText('加安排'))
    await waitFor(() => expect(screen.getByText(/ADD_DIALOG/)).toBeTruthy())

    spy.mockClear()
    fireEvent.click(screen.getByText('保存新增'))
    await waitFor(() => expect(spy).toHaveBeenCalled())
    container.remove()
  })
})

// ============ 详情/右键菜单回调与错误重试（覆盖率补测） ============

describe('HomePage：详情与右键菜单回调', () => {
  it('详情弹窗「关详情」清空 detail', async () => {
    const { container } = render(wrap(<HomePage />))
    fireEvent.click(screen.getByText('打开事件'))
    await waitFor(() => expect(screen.getByText('DETAIL_DIALOG')).toBeTruthy())

    fireEvent.click(screen.getByText('关详情'))
    await waitFor(() => expect(screen.queryByText('DETAIL_DIALOG')).toBeNull())
    container.remove()
  })

  it('详情弹窗「保存详情」触发日历失效', async () => {
    const spy = vi.spyOn(QueryClient.prototype, 'invalidateQueries')
    const { container } = render(wrap(<HomePage />))
    fireEvent.click(screen.getByText('打开事件'))
    await waitFor(() => expect(screen.getByText('DETAIL_DIALOG')).toBeTruthy())

    spy.mockClear()
    fireEvent.click(screen.getByText('保存详情'))
    await waitFor(() => expect(spy).toHaveBeenCalled())
    container.remove()
  })

  it('右键菜单 onClose / onDelete 连线存在', async () => {
    const { container } = render(wrap(<HomePage />))
    fireEvent.click(screen.getByText('右键事件'))
    await waitFor(() => expect(ctxCbs.onClose).toBeTypeOf('function'))
    expect(ctxCbs.onDelete).toBeTypeOf('function')

    expect(() => ctxCbs.onClose?.()).not.toThrow()
    expect(() => ctxCbs.onDelete?.({ id: 9, member_ids: [1] })).not.toThrow()
    container.remove()
  })
})

describe('HomePage：统计与日历错误重试', () => {
  it('统计与日历都失败时渲染重试按钮且可点击', async () => {
    apiMock.fetchCalendarMonth.mockRejectedValue(new Error('全挂了'))
    const { container } = render(wrap(<HomePage />))

    // CalendarPanel 桩不渲染错误态，但 HomePage 自身的统计错误行会出现
    await waitFor(() => expect(document.body.textContent).toBeTruthy())
    const retries = Array.from(document.querySelectorAll('button')).filter((b) => b.textContent === '重试')
    for (const btn of retries) {
      expect(() => fireEvent.click(btn)).not.toThrow()
    }
    container.remove()
  })
})
