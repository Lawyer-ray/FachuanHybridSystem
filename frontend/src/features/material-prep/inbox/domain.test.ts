/**
 * 收件箱领域逻辑单测（node 环境）。
 *
 * 覆盖三块纯函数：
 * - groupByTime：按自然日分组（今天 / 昨天 / 本周 / 更早），脏数据不炸；
 * - filterRows：本地二次筛（已读 + 关键字）；
 * - 可进入材料预处理的判定（packIdOf / canConvert / isPackSource）。
 *
 * 这些是收件箱页最容易静默退化的地方：分组错位会让消息「消失」在某组里，
 * 判定写错会让律师点了没反应。
 */
import { describe, expect, it } from 'vitest'

import { countUnread, filterRows, groupByTime } from './domain'
import { canConvert, isPackSource, packIdOf, type InboxRow } from './types'

/** 造一行最小可用的收件箱数据（只填被测字段，其余用后端恒返回的空默认值兜） */
function row(over: Partial<InboxRow> & { id: number; received_at: string }): InboxRow {
  return {
    source_name: '来源',
    source_type: 'court_inbox',
    subject: `主题 ${over.id}`,
    sender: '法院',
    recipient: '',
    has_attachments: false,
    attachment_count: 0,
    uploaded_by_id: null,
    uploaded_by_name: '',
    created_at: over.received_at,
    status: 'todo',
    segs: 0,
    named: 0,
    pages: 0,
    mats: 0,
    types: [],
    compose: '',
    is_read: true,
    upload_link_title: '',
    upload_contract_name: '',
    ...over,
  }
}

const NOW = new Date(2026, 9, 28, 12, 0, 0) // 2026-10-28 12:00 本地时间

describe('groupByTime', () => {
  it('按自然日分成今天 / 昨天 / 本周 / 更早', () => {
    const rows = [
      row({ id: 1, received_at: new Date(2026, 9, 28, 9, 0).toISOString() }), // 今天
      row({ id: 2, received_at: new Date(2026, 9, 27, 15, 0).toISOString() }), // 昨天
      row({ id: 3, received_at: new Date(2026, 9, 24, 10, 0).toISOString() }), // 本周（4 天前）
      row({ id: 4, received_at: new Date(2026, 8, 1, 10, 0).toISOString() }), // 更早
    ]
    const groups = groupByTime(rows, NOW)
    expect(groups.map((g) => g.key)).toEqual(['today', 'yesterday', 'week', 'earlier'])
    expect(groups.map((g) => g.rows.map((r) => r.id))).toEqual([[1], [2], [3], [4]])
  })

  it('空组被剔除（不渲染空标题）', () => {
    const groups = groupByTime([row({ id: 1, received_at: new Date(2026, 9, 28, 9, 0).toISOString() })], NOW)
    expect(groups).toHaveLength(1)
    expect(groups[0]?.key).toBe('today')
  })

  it('组内保持后端给的倒序（不重排）', () => {
    const rows = [
      row({ id: 10, received_at: new Date(2026, 9, 28, 11, 0).toISOString() }),
      row({ id: 11, received_at: new Date(2026, 9, 28, 8, 0).toISOString() }),
    ]
    expect(groupByTime(rows, NOW)[0]?.rows.map((r) => r.id)).toEqual([10, 11])
  })

  it('时间解析失败的行归「更早」，不让整页分组崩掉', () => {
    const groups = groupByTime([row({ id: 1, received_at: 'not-a-date' })], NOW)
    expect(groups).toHaveLength(1)
    expect(groups[0]?.key).toBe('earlier')
  })

  it('边界：今天 00:00 算今天，昨天 23:59 算昨天', () => {
    const rows = [
      row({ id: 1, received_at: new Date(2026, 9, 28, 0, 0).toISOString() }),
      row({ id: 2, received_at: new Date(2026, 9, 27, 23, 59).toISOString() }),
    ]
    const groups = groupByTime(rows, NOW)
    expect(groups[0]?.key).toBe('today')
    expect(groups[0]?.rows.map((r) => r.id)).toEqual([1])
    expect(groups[1]?.rows.map((r) => r.id)).toEqual([2])
  })
})

describe('filterRows', () => {
  const rows = [
    row({ id: 1, received_at: NOW.toISOString(), is_read: false, subject: '执行裁定书', sender: '甲县人民法院' }),
    row({ id: 2, received_at: NOW.toISOString(), is_read: true, subject: '民事判决书', sender: '乙市人民法院' }),
  ]

  it('unreadOnly 只留未读', () => {
    expect(filterRows(rows, { unreadOnly: true }).map((r) => r.id)).toEqual([1])
  })

  it('关键字匹配主题 / 发件人 / 来源名，大小写不敏感', () => {
    expect(filterRows(rows, { keyword: '判决' }).map((r) => r.id)).toEqual([2])
    expect(filterRows(rows, { keyword: '甲县' }).map((r) => r.id)).toEqual([1])
    expect(filterRows(rows, { keyword: '来源' })).toHaveLength(2)
  })

  it('关键字两端空白被忽略；空关键字不筛', () => {
    expect(filterRows(rows, { keyword: '  ' })).toHaveLength(2)
  })

  it('未读 + 关键字同时生效', () => {
    expect(filterRows(rows, { unreadOnly: true, keyword: '判决' })).toHaveLength(0)
  })
})

describe('countUnread', () => {
  it('只数未读', () => {
    const rows = [
      row({ id: 1, received_at: NOW.toISOString(), is_read: false }),
      row({ id: 2, received_at: NOW.toISOString(), is_read: false }),
      row({ id: 3, received_at: NOW.toISOString(), is_read: true }),
    ]
    expect(countUnread(rows)).toBe(2)
  })

  it('空列表为 0', () => {
    expect(countUnread([])).toBe(0)
  })
})

describe('材料预处理入口判定', () => {
  it('材料包来源直接就是可打开的包', () => {
    const pack = row({ id: 7, received_at: NOW.toISOString(), source_type: 'manual_upload' })
    expect(isPackSource(pack)).toBe(true)
    expect(packIdOf(pack)).toBe(7)
  })

  it('客户上传包同样直接可开', () => {
    const pack = row({ id: 8, received_at: NOW.toISOString(), source_type: 'client_upload' })
    expect(packIdOf(pack)).toBe(8)
  })

  it('外部来源未转过 → 没有包可开，但可转', () => {
    const msg = row({ id: 9, received_at: NOW.toISOString(), has_attachments: true })
    expect(packIdOf(msg)).toBeNull()
    expect(canConvert(msg)).toBe(true)
  })

  it('外部来源已转过 → 直接打开那个包，不再重复转', () => {
    const msg = row({
      id: 9,
      received_at: NOW.toISOString(),
      has_attachments: true,
      converted_message_id: 42,
    })
    expect(packIdOf(msg)).toBe(42)
    expect(canConvert(msg)).toBe(false)
  })

  it('无附件的通知类消息既不可开也不可转', () => {
    const notice = row({ id: 10, received_at: NOW.toISOString(), has_attachments: false })
    expect(packIdOf(notice)).toBeNull()
    expect(canConvert(notice)).toBe(false)
  })
})
