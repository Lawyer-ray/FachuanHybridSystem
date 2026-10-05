/**
 * home/api/reminders 单测（node 环境）。
 *
 * mock 只打 HTTP 客户端工厂（@/lib/api 的 createApiClient），断言聚焦：
 * 请求参数构造、响应投影（searchTargetOptions 的 name 拆分 / 白名单收窄、
 * setRemindersCompleted 取 updated）、createReminder 的 target_type → 字段拆开。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const clients = vi.hoisted(() => [] as Array<{
  prefix: string
  get: ReturnType<typeof vi.fn>
  post: ReturnType<typeof vi.fn>
  put: ReturnType<typeof vi.fn>
  delete: ReturnType<typeof vi.fn>
}>)

vi.mock('@/lib/api', () => ({
  createApiClient: (opts?: { prefix?: string }) => {
    const client = {
      prefix: opts?.prefix ?? '/api/v1',
      get: vi.fn(),
      post: vi.fn(),
      put: vi.fn(),
      delete: vi.fn(),
    }
    clients.push(client)
    return client
  },
}))

import {
  calendarKeys,
  createReminder,
  fetchCalendarMonth,
  listReminderTypes,
  parseReminder,
  searchTargetOptions,
  setRemindersCompleted,
} from './reminders'

function remindersClient() {
  const c = clients.find((x) => x.prefix === '/api/v1/reminders')
  if (!c) throw new Error('reminders 客户端未创建')
  return c
}

/** ky ResponsePromise 形状桩：可链 .json() */
function respond(body: unknown) {
  const p = Promise.resolve(body)
  return Object.assign(p, { json: () => p })
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('日历与完成标记', () => {
  it('fetchCalendarMonth：GET calendar 带 year/month 查询参数，响应原样返回', async () => {
    const api = remindersClient()
    const month = { days: {}, stats: { today: 0, deadline_in_7days: 0, month_court: 0 } }
    api.get.mockReturnValueOnce(respond(month))
    await expect(fetchCalendarMonth(2026, 10)).resolves.toBe(month)
    expect(api.get).toHaveBeenCalledWith('calendar', { searchParams: { year: 2026, month: 10 } })
  })

  it('setRemindersCompleted：POST complete 传 reminder_ids + is_completed，返回 updated 条数', async () => {
    const api = remindersClient()
    api.post.mockReturnValueOnce(respond({ updated: 3 }))
    await expect(setRemindersCompleted([1, 2, 3], true)).resolves.toBe(3)
    expect(api.post).toHaveBeenCalledWith('complete', {
      json: { reminder_ids: [1, 2, 3], is_completed: true },
    })
  })

  it('calendarKeys 工厂：month 在 all 前缀下展开（invalidate 按前缀失效）', () => {
    expect(calendarKeys.all).toEqual(['home-calendar'])
    expect(calendarKeys.month(2026, 10)).toEqual(['home-calendar', 2026, 10])
  })
})

describe('searchTargetOptions（name 拆分 + 类型白名单）', () => {
  it('contract / case：name 原样进 title，hint 为空', async () => {
    const api = remindersClient()
    api.get.mockReturnValueOnce(
      respond({
        items: [
          { id: 1, target_type: 'contract', target_type_label: '合同', name: '常年法律顾问合同' },
          { id: 2, target_type: 'case', target_type_label: '案件', name: '  张三诉李四案  ' },
        ],
      }),
    )
    const rows = await searchTargetOptions('顾问')
    expect(api.get).toHaveBeenCalledWith('target-options', { searchParams: { q: '顾问' }, signal: undefined })
    expect(rows).toEqual([
      { id: 1, target_type: 'contract', target_type_label: '合同', title: '常年法律顾问合同', hint: '' },
      // name 两端空白被 trim
      { id: 2, target_type: 'case', target_type_label: '案件', title: '张三诉李四案', hint: '' },
    ])
  })

  it('case_log：`#123 案件名｜日志摘要` 拆成 title + hint', async () => {
    const api = remindersClient()
    api.get.mockReturnValueOnce(
      respond({
        items: [{ id: 5, target_type: 'case_log', target_type_label: '案件日志', name: '#123 张三案｜开庭笔录节选' }],
      }),
    )
    const rows = await searchTargetOptions('笔录')
    expect(rows[0]).toMatchObject({ title: '张三案', hint: '开庭笔录节选' })
  })

  it('case_log 无分隔符｜：整体作为 title，hint 为空；无 #id 前缀也不炸', async () => {
    const api = remindersClient()
    api.get.mockReturnValueOnce(
      respond({
        items: [
          { id: 6, target_type: 'case_log', target_type_label: '日志', name: '#7 只有案件名' },
          { id: 7, target_type: 'case_log', target_type_label: '日志', name: '裸名称｜' },
        ],
      }),
    )
    const rows = await searchTargetOptions('x')
    expect(rows[0]).toMatchObject({ title: '只有案件名', hint: '' })
    // 尾随｜：slice 出空 hint，trim 后为空串
    expect(rows[1]).toMatchObject({ title: '裸名称', hint: '' })
  })

  it('未知 target_type 兜底为 contract（不丢候选行）；items 缺省按空处理', async () => {
    const api = remindersClient()
    api.get.mockReturnValueOnce(
      respond({
        items: [{ id: 9, target_type: 'mystery', target_type_label: '未知', name: '任意名' }],
      }),
    )
    const rows = await searchTargetOptions('y')
    expect(rows[0]).toMatchObject({ target_type: 'contract', title: '任意名' })

    api.get.mockReturnValueOnce(respond({}))
    await expect(searchTargetOptions('z')).resolves.toEqual([])
  })

  it('signal 透传（联想请求可取消）', async () => {
    const api = remindersClient()
    api.get.mockReturnValueOnce(respond({ items: [] }))
    const ac = new AbortController()
    await searchTargetOptions('q', ac.signal)
    expect(api.get).toHaveBeenCalledWith('target-options', { searchParams: { q: 'q' }, signal: ac.signal })
  })
})

describe('类型下拉与文本解析', () => {
  it('listReminderTypes：GET types 直通', async () => {
    const api = remindersClient()
    const types = [{ code: 'hearing', label: '开庭' }]
    api.get.mockReturnValueOnce(respond(types))
    await expect(listReminderTypes()).resolves.toBe(types)
    expect(api.get).toHaveBeenCalledWith('types')
  })

  it('parseReminder：POST parse 传原文；空响应兜底为 []', async () => {
    const api = remindersClient()
    api.post.mockReturnValueOnce(respond(null))
    await expect(parseReminder('明天开会')).resolves.toEqual([])
    expect(api.post).toHaveBeenCalledWith('parse', { json: { text: '明天开会' } })

    const rows = [{ due_at: '2026-10-01T09:30:00', content: '开庭' }]
    api.post.mockReturnValueOnce(respond(rows))
    await expect(parseReminder('2026-10-01 09:30 开庭')).resolves.toBe(rows)
  })
})

describe('createReminder（target_type → wire 字段拆开）', () => {
  it('contract → contract_id；case → case_id；case_log → case_log_id（三者只填一个）', async () => {
    const api = remindersClient()
    api.post.mockReturnValue(respond({}))
    const base = { reminder_type: 'other', content: '缴费', due_at: '2026-10-01T09:00:00' }

    await createReminder({ ...base, target_type: 'contract', target_id: 11 })
    expect(api.post).toHaveBeenLastCalledWith('create', {
      json: expect.objectContaining({ contract_id: 11 }),
    })
    const firstCall = api.post.mock.calls[0]![1] as { json: Record<string, unknown> }
    expect(firstCall.json.case_id).toBeUndefined()
    expect(firstCall.json.case_log_id).toBeUndefined()

    await createReminder({ ...base, target_type: 'case', target_id: 22 })
    expect(api.post).toHaveBeenLastCalledWith('create', {
      json: expect.objectContaining({ case_id: 22 }),
    })

    await createReminder({ ...base, target_type: 'case_log', target_id: 33 })
    expect(api.post).toHaveBeenLastCalledWith('create', {
      json: expect.objectContaining({ case_log_id: 33 }),
    })
  })

  it('不关联对象：走缺省 case_id=null；target_id 缺省为 null', async () => {
    const api = remindersClient()
    api.post.mockReturnValueOnce(respond({}))
    await createReminder({ reminder_type: 'other', content: '提醒', due_at: '2026-10-01T09:00:00' })
    expect(api.post).toHaveBeenCalledWith('create', {
      json: expect.objectContaining({ case_id: null }),
    })

    api.post.mockReturnValueOnce(respond({}))
    await createReminder({
      reminder_type: 'other',
      content: '提醒',
      due_at: '2026-10-01T09:00:00',
      target_type: 'case',
    })
    expect(api.post).toHaveBeenLastCalledWith('create', {
      json: expect.objectContaining({ case_id: null }),
    })
  })
})
