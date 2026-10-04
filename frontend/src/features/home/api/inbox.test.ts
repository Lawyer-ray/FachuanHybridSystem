/**
 * home/api/inbox 单测（node 环境）。
 *
 * mock 只打 @/lib/api 的 createApiClient；覆盖 listInbox 的行投影
 * （source_type → kind 映射、sms 标记 hot、limit 截取）与 formatRelative
 * 的相对时间口径（今天/昨天/更早/非法值，用 fake system time 固定「现在」）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

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

import { formatRelative, listInbox } from './inbox'
import type { InboxMessageOut } from './inbox'

function inboxClient() {
  const c = clients.find((x) => x.prefix === '/api/v1/inbox')
  if (!c) throw new Error('inbox 客户端未创建')
  return c
}

function respond(body: unknown) {
  const p = Promise.resolve(body)
  return Object.assign(p, { json: () => p })
}

function msg(id: number, sourceType: string, sourceName: string, receivedAt: string): InboxMessageOut {
  return {
    id,
    source_name: sourceName,
    source_type: sourceType,
    subject: `条目${id}`,
    sender: '发送方',
    recipient: '收件方',
    received_at: receivedAt,
    has_attachments: true,
    attachment_count: 1,
    segs: 0,
    named: 0,
    pages: 0,
    mats: 0,
    types: [],
    compose: '',
    created_at: receivedAt,
  } as InboxMessageOut
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.useFakeTimers()
  vi.setSystemTime(new Date(2026, 9, 15, 12, 0, 0)) // 2026-10-15 12:00 本地
})

afterEach(() => {
  vi.useRealTimers()
})

describe('listInbox（最近流入投影）', () => {
  it('source_type 映射 kind：court_sms→sms(hot)、court_inbox/email→mail、manual_upload/未知→mat', async () => {
    const api = inboxClient()
    api.get.mockReturnValueOnce(
      respond([
        msg(1, 'court_sms', '法院短信', '2026-10-15T08:30:00'),
        msg(2, 'court_inbox', '法院专递', '2026-10-15T08:00:00'),
        msg(3, 'email', '邮件', '2026-10-15T07:00:00'),
        msg(4, 'manual_upload', '手动上传', '2026-10-15T06:00:00'),
        msg(5, 'anything_else', '其他来源', '2026-10-15T05:00:00'),
      ]),
    )
    const rows = await listInbox()
    expect(api.get).toHaveBeenCalledWith('messages', { searchParams: { limit: 6 } })
    expect(rows.map((r) => [r.kind, r.hot])).toEqual([
      ['sms', true],
      ['mail', false],
      ['mail', false],
      ['mat', false],
      ['mat', false], // 未知来源兜底 mat
    ])
    expect(rows[0]).toMatchObject({ id: 1, sourceLabel: '法院短信', who: '发送方', title: '条目1' })
  })

  it('自定义 limit：查询参数与本地截取同步生效', async () => {
    const api = inboxClient()
    api.get.mockReturnValueOnce(respond([msg(1, 'court_sms', 'a', '2026-10-15T08:30:00'), msg(2, 'email', 'b', '2026-10-15T08:30:00')]))
    const rows = await listInbox(1)
    expect(api.get).toHaveBeenCalledWith('messages', { searchParams: { limit: 1 } })
    expect(rows).toHaveLength(1)
  })
})

describe('formatRelative（相对时间口径）', () => {
  it('今天 → `今天 HH:mm`（时区无关，本地字段直读）', () => {
    expect(formatRelative('2026-10-15T09:05:00')).toBe('今天 09:05')
  })

  it('昨天 → `昨天 HH:mm`', () => {
    expect(formatRelative('2026-10-14T23:59:00')).toBe('昨天 23:59')
  })

  it('更早 → `M 月 D 日`（不带年份与时分）', () => {
    expect(formatRelative('2026-10-01T09:00:00')).toBe('10 月 1 日')
    expect(formatRelative('2026-09-30T09:00:00')).toBe('9 月 30 日')
  })

  it('跨月边界（昨天是上月末）也正确判昨天', () => {
    vi.setSystemTime(new Date(2026, 9, 1, 12, 0, 0)) // 10-01，昨天是 09-30
    expect(formatRelative('2026-09-30T18:00:00')).toBe('昨天 18:00')
  })

  it('非法值 → 空串（不抛错）', () => {
    expect(formatRelative('not-a-date')).toBe('')
  })
})
