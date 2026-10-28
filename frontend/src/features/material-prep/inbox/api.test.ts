/**
 * 收件箱 API 封装单测（node 环境）。
 *
 * 重点不是「能发出请求」，而是**参数怎么拼**：
 * - source 档位是后端 source_type 的多值串，'all' 必须**不传**该参数
 *   （传空串会被后端当成一个来源过滤，结果集变空——这类 bug 在页面上
 *   表现为「切换分类后什么都没了」，很难一眼看出来）；
 * - unread_only 用 'true' 字符串；
 * - search 去空白后为空则不传。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const clients = vi.hoisted(() => {
  const made: { prefix: string; get: ReturnType<typeof vi.fn>; post: ReturnType<typeof vi.fn> }[] = []
  return { made }
})

vi.mock('@/lib/api', () => ({
  createApiClient: ({ prefix }: { prefix: string }) => {
    const api = {
      prefix,
      get: vi.fn(() => ({ json: async () => [] })),
      post: vi.fn(() => ({ json: async () => ({ ok: true, message_id: 1, is_read: true, read_at: null, pack_id: 5 }) })),
    }
    clients.made.push(api)
    return api
  },
}))

function client() {
  const c = clients.made.find((x) => x.prefix === '/api/v1/inbox')
  if (!c) throw new Error('inbox 客户端未创建')
  return c
}

/** 取第 n 次 get/post 的 searchParams（测试里断言参数拼装） */
function paramsOf(n = 0): Record<string, string> {
  return (client().get.mock.calls[n]?.[1] as { searchParams: Record<string, string> } | undefined)!.searchParams
}

beforeEach(() => {
  clients.made.length = 0
  vi.resetModules()
  clients.made.length = 0
})

describe('listInbox', () => {
  it("source='all' 时不传 source_type（传空会被后端过滤成空集）", async () => {
    const { listInbox: fresh } = await import('./api')
    await fresh()
    const params = paramsOf()
    expect(params).not.toHaveProperty('source_type')
    // 默认仍要带 limit（后端默认 500，前端显式传更小值）
    expect(params.limit).toBe('200')
  })

  it('多值档位原样透传逗号串', async () => {
    const { listInbox: fresh } = await import('./api')
    await fresh({ source: 'manual_upload,client_upload' })
    expect(paramsOf().source_type).toBe('manual_upload,client_upload')
  })

  it('单值档位透传', async () => {
    const { listInbox: fresh } = await import('./api')
    await fresh({ source: 'court_inbox' })
    expect(paramsOf().source_type).toBe('court_inbox')
  })

  it('unreadOnly 拼成字符串 true；false 时不传', async () => {
    const { listInbox: fresh } = await import('./api')
    await fresh({ unreadOnly: true })
    expect(paramsOf().unread_only).toBe('true')
    await fresh({ unreadOnly: false })
    expect(paramsOf(1)).not.toHaveProperty('unread_only')
  })

  it('search 去空白；纯空白不传', async () => {
    const { listInbox: fresh } = await import('./api')
    await fresh({ search: '  判决书  ' })
    expect(paramsOf().search).toBe('判决书')
    await fresh({ search: '   ' })
    expect(paramsOf(1)).not.toHaveProperty('search')
  })

  it('请求路径是 messages（前缀由客户端承担）', async () => {
    const { listInbox: fresh } = await import('./api')
    await fresh()
    expect(client().get.mock.calls[0]?.[0]).toBe('messages')
  })
})

describe('setReadState', () => {
  it('POST messages/{id}/read，body 带 { read }', async () => {
    const { setReadState: fresh } = await import('./api')
    await fresh(9, false)
    expect(client().post.mock.calls[0]?.[0]).toBe('messages/9/read')
    expect(client().post.mock.calls[0]?.[1]).toEqual({ json: { read: false } })
  })
})

describe('convertToPack', () => {
  it('POST messages/{id}/convert', async () => {
    const { convertToPack: fresh } = await import('./api')
    await fresh(9)
    expect(client().post.mock.calls[0]?.[0]).toBe('messages/9/convert')
  })

  it('返回里的 pack_id 即材料包 id', async () => {
    const { convertToPack: fresh } = await import('./api')
    const res = await fresh(9)
    expect(res.pack_id).toBe(5)
  })
})

describe('attachmentUrl', () => {
  it('inline / download 用不同端点后缀', async () => {
    const { attachmentUrl } = await import('./api')
    expect(attachmentUrl(3, 1, true)).toBe('/api/v1/inbox/messages/3/attachments/1/preview')
    expect(attachmentUrl(3, 1, false)).toBe('/api/v1/inbox/messages/3/attachments/1/download')
  })
})
