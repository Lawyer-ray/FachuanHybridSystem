// @vitest-environment jsdom
/**
 * EventDetailDialog 删除 / 编辑入口 dom 测试（jsdom）。
 *
 * 覆盖：can_delete=false 不渲染删除按钮（别人建的日程连入口都没有）；
 * can_delete=true 走**弹窗内原地展开**的确认条（不再叠第二层 AlertDialog）——
 * 取消不下发、确认才 onDelete；合并事件的确认文案提示会一起删掉 N 条同步记录；
 * can_edit 显隐编辑入口，编辑表单回填并经 updateReminder 下发。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'

import { updateReminder } from '../api'
import type { CalendarEvent } from '../api'
import { EventDetailDialog } from './EventDetailDialog'

// 编辑表单走 ../api 的 updateReminder / listReminderTypes，测试里全部拦掉
vi.mock('../api', () => ({
  REMINDER_TYPES_KEY: ['reminder-types'],
  listReminderTypes: vi.fn(async () => [{ value: 'other', label: '其他' }]),
  updateReminder: vi.fn(async () => undefined),
}))

function ev(p: Partial<CalendarEvent> = {}): CalendarEvent {
  return {
    id: 1,
    kind: 'meeting',
    kind_label: '日程',
    title: '与客户会谈',
    content: '与客户会谈',
    day: '2026-10-20',
    time: '09:00',
    time_range: '',
    place: '',
    person: '',
    case_no: '',
    hearing_type: '',
    target_type: '',
    target_name: '',
    case_id: null,
    is_today: false,
    is_overdue: false,
    is_completed: false,
    reminder_type: 'other',
    members: 1,
    member_ids: [1],
    can_delete: false,
    can_edit: false,
    ...p,
  }
}

function renderDialog(event: CalendarEvent) {
  const onDelete = vi.fn()
  const onSaved = vi.fn()
  const onClose = vi.fn()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <EventDetailDialog
        event={event}
        onClose={onClose}
        onSaved={onSaved}
        onOpenCase={vi.fn()}
        onToggleComplete={vi.fn()}
        onDelete={onDelete}
      />
    </QueryClientProvider>,
  )
  return { onDelete, onSaved, onClose }
}

describe('EventDetailDialog 删除入口', () => {
  it('can_delete=false：不渲染删除按钮', () => {
    renderDialog(ev({ can_delete: false }))
    expect(screen.getByText('与客户会谈')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /删除此安排/ })).toBeNull()
  })

  it('can_delete=true：点删除原地展开确认条，取消不下发，确认才调用 onDelete', async () => {
    const { onDelete } = renderDialog(ev({ can_delete: true }))

    fireEvent.click(screen.getByRole('button', { name: /删除此安排/ }))
    expect(await screen.findByText(/删除后不可恢复/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    expect(onDelete).not.toHaveBeenCalled()
    // 取消后确认条收起，可重新发起
    fireEvent.click(screen.getByRole('button', { name: /删除此安排/ }))
    // 确认条内的「删除」按钮：文案精确为「删除」，与入口的「删除此安排」区分
    fireEvent.click(await screen.findByRole('button', { name: '删除' }))
    expect(onDelete).toHaveBeenCalledTimes(1)
    expect(onDelete.mock.calls[0]?.[0]).toMatchObject({ id: 1, member_ids: [1] })
  })

  it('合并事件：确认文案提示会一起删掉全部同步记录', async () => {
    renderDialog(ev({ can_delete: true, members: 3, member_ids: [1, 2, 3] }))
    fireEvent.click(screen.getByRole('button', { name: /删除此安排/ }))
    expect(await screen.findByText(/同一庭审的 3 条同步记录会一起删除/)).toBeTruthy()
  })
})

describe('EventDetailDialog 编辑入口', () => {
  it('can_edit=false：不渲染编辑按钮', () => {
    renderDialog(ev({ can_edit: false }))
    expect(screen.queryByRole('button', { name: /编辑/ })).toBeNull()
  })

  it('can_edit=true：点编辑原地切表单（回填内容），取消回到详情', () => {
    renderDialog(ev({ can_edit: true }))

    fireEvent.click(screen.getByRole('button', { name: '编辑' }))
    const contentInput = screen.getByPlaceholderText(/提交证据目录/) as HTMLInputElement
    expect(contentInput.value).toBe('与客户会谈')

    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    // 回到详情态：编辑按钮还在，表单输入框没了
    expect(screen.getByRole('button', { name: '编辑' })).toBeTruthy()
    expect(screen.queryByPlaceholderText(/提交证据目录/)).toBeNull()
  })

  it('保存：经 updateReminder 下发四项字段，成功后回调 onSaved', async () => {
    const { onSaved } = renderDialog(ev({ can_edit: true, content: '旧内容', day: '2026-10-21', time: '09:00' }))

    fireEvent.click(screen.getByRole('button', { name: '编辑' }))
    const contentInput = screen.getByPlaceholderText(/提交证据目录/) as HTMLInputElement
    fireEvent.change(contentInput, { target: { value: '新内容' } })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))

    await waitFor(() => {
      expect(updateReminder).toHaveBeenCalledTimes(1)
    })
    expect(vi.mocked(updateReminder)).toHaveBeenCalledWith(1, {
      reminder_type: 'other',
      content: '新内容',
      due_at: '2026-10-21T09:00:00',
    })
    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledTimes(1)
    })
  })
})

// ============ 信息行 / 合并提示 / 完成切换（覆盖率补测） ============

function renderDetail(e: CalendarEvent, props: Record<string, unknown> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <EventDetailDialog
        event={e}
        onClose={vi.fn()}
        onToggleComplete={vi.fn()}
        onOpenCase={vi.fn()}
        onDelete={vi.fn()}
        onSaved={vi.fn()}
        {...props}
      />
    </QueryClientProvider>,
  )
}

describe('EventDetailDialog：信息行构建', () => {
  it('时段与开始时间不同才显示「时段」行', () => {
    const { unmount } = renderDetail(ev({ time: '09:00', time_range: '09:00-11:00' }))
    expect(document.body.textContent).toContain('时段')
    expect(document.body.textContent).toContain('09:00-11:00')
    unmount()
  })

  it('时段与开始时间相同时不显示「时段」行', () => {
    const { unmount } = renderDetail(ev({ time: '09:00', time_range: '09:00' }))
    expect(document.body.textContent).not.toContain('时段')
    unmount()
  })

  it('开庭类的地点行标签为「法庭」，其余为「地点」', () => {
    const court = renderDetail(ev({ kind: 'court', place: '第三法庭' }))
    // Dialog 走 portal，内容不在 container 内
    expect(document.body.textContent).toContain('法庭')
    court.unmount()

    const meet = renderDetail(ev({ kind: 'meeting', place: '会议室' }))
    expect(document.body.textContent).toContain('地点')
    meet.unmount()
  })

  it('律师 / 方式 / 案号各行按存在与否渲染', () => {
    const { unmount } = renderDetail(
      ev({ person: '张律师', hearing_type: '线上', case_no: '（20XX）京01民初1号' }),
    )
    const text = document.body.textContent ?? ''
    expect(text).toContain('律师')
    expect(text).toContain('张律师')
    expect(text).toContain('方式')
    expect(text).toContain('线上')
    expect(text).toContain('案号')
    unmount()
  })

  it('关联对象名与标题相同时不重复显示', () => {
    const { unmount } = renderDetail(ev({ title: '同一名称', target_name: '同一名称' }))
    // 只出现标题一处（信息行不重复）
    const matches = (document.body.textContent ?? '').split('同一名称').length - 1
    expect(matches).toBeLessThanOrEqual(2)
    unmount()
  })

  it('完全没有附加信息时显示「没有更多信息」', () => {
    const { unmount } = renderDetail(
      ev({
        time_range: '',
        place: '',
        person: '',
        hearing_type: '',
        case_no: '',
        target_name: '',
      }),
    )
    expect(document.body.textContent).toContain('没有更多信息')
    unmount()
  })
})

describe('EventDetailDialog：合并提示', () => {
  it('members>1 时显示合并说明与成员 id', () => {
    const { unmount } = renderDetail(ev({ members: 3, member_ids: [11, 12, 13] }))
    const text = document.body.textContent ?? ''
    expect(text).toContain('3 条同步记录')
    expect(text).toContain('#11、#12、#13')
    unmount()
  })

  it('members<=1 时不显示合并说明', () => {
    const { unmount } = renderDetail(ev({ members: 1 }))
    expect(document.body.textContent).not.toContain('条同步记录')
    unmount()
  })
})

describe('EventDetailDialog：完成切换', () => {
  it('未完成时按钮文案为「标记完成」', () => {
    const { unmount } = renderDetail(ev({ is_completed: false }))
    expect(screen.getByRole('button', { name: /标记完成/ })).toBeTruthy()
    unmount()
  })

  it('已完成时按钮文案为「恢复为未完成」', () => {
    const { unmount } = renderDetail(ev({ is_completed: true }))
    expect(screen.getByRole('button', { name: /恢复为未完成/ })).toBeTruthy()
    unmount()
  })

  it('点完成按钮回调 onToggleComplete 带事件', () => {
    const onToggleComplete = vi.fn()
    const e = ev({ is_completed: false })
    const { unmount } = renderDetail(e, { onToggleComplete })

    fireEvent.click(screen.getByRole('button', { name: /标记完成/ }))
    expect(onToggleComplete).toHaveBeenCalledWith(e)
    unmount()
  })
})

describe('EventDetailDialog：跳案件', () => {
  it('有 case_id 时按钮可用并回调', () => {
    const onOpenCase = vi.fn()
    const e = ev({ case_id: 42 })
    const { unmount } = renderDetail(e, { onOpenCase })

    const btn = Array.from(document.querySelectorAll('button')).find((b) =>
      /案件/.test(b.textContent ?? ''),
    ) as HTMLButtonElement
    expect(btn.disabled).toBe(false)
    fireEvent.click(btn)
    expect(onOpenCase).toHaveBeenCalledWith(e)
    unmount()
  })

  it('无 case_id 时按钮禁用', () => {
    const { unmount } = renderDetail(ev({ case_id: null }))
    const btn = Array.from(document.querySelectorAll('button')).find((b) =>
      /案件/.test(b.textContent ?? ''),
    ) as HTMLButtonElement
    expect(btn.disabled).toBe(true)
    unmount()
  })
})
