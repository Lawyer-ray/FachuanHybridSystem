import { beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * 文书生成 API 层：前缀、端点、超时、出参兼容。
 *
 * 锁死的三件事都会静默出错：
 * 1) **前缀**必须带 `/api/v1`。`createApiClient({ prefix })` 的 prefix 是
 *    **整体覆盖**而不是相对拼接（见 payment-intake/api.test.ts 的踩坑记录），
 *    少一段就会 404，而 tsc/lint/单测全绿；
 * 2) **超时**必须显式放大。一次起草是「模型逐槽写正文 → 渲染 docx → 落盘 →
 *    可选排审查」，ky 默认 10s 会把还在跑的请求掐掉——前端以为失败，文件其实
 *    已经写进文件夹了；
 * 3) **类型清单两种出参都要认**：现约定 `{ items: [...] }`，裸数组是它之前的
 *    形状。少一个分支，下拉会静默变成「没有可用的文书类型」。
 */
type Recorder = {
  prefix: string
  body: unknown
  get: ReturnType<typeof vi.fn>
  post: ReturnType<typeof vi.fn>
}

const recorders = vi.hoisted(() => [] as Recorder[])

vi.mock('@/lib/api', () => ({
  createApiClient: (opts?: { prefix?: string }) => {
    const prefix = opts?.prefix ?? '/api/v1'
    const existing = recorders.find((r) => r.prefix === prefix)
    if (existing) return existing
    const recorder: Recorder = {
      prefix,
      body: undefined,
      // body 未显式设置时给一个合法空包：惰性建客户端的首次调用（见 beforeEach）
      // 会先跑到它，undefined 会被 listDocTypes 当成坏出参直接炸掉
      get: vi.fn(() => respond(recorder.body ?? { items: [] })),
      post: vi.fn(() => respond(recorder.body ?? { items: [] })),
    }
    recorders.push(recorder)
    return recorder
  },
}))

/** ky ResponsePromise 形状桩：同步可链 `.json()`，await 得 body */
function respond(body: unknown) {
  const p = Promise.resolve(body)
  return Object.assign(p, { json: () => p })
}

import * as api from './api'

const PREFIX = '/api/v1/doc-workspace'

function workspace(): Recorder {
  const r = recorders.find((x) => x.prefix === PREFIX)
  if (!r) throw new Error('doc-workspace 客户端未创建')
  return r
}

function lastPost() {
  const calls = workspace().post.mock.calls
  return calls[calls.length - 1] as [string, Record<string, unknown>]
}

/**
 * api.ts 是**惰性**建客户端（延迟到第一次调用，与 doc-review-api.ts 同一处理）：
 * 每个用例先跑一次空调用把它落进 recorders，再清掉调用记录与上一条用例
 * 残留的 body。
 */
beforeEach(async () => {
  await api.listDocTypes()
  workspace().body = undefined
  vi.clearAllMocks()
})

describe('doc-generation api 前缀与端点', () => {
  it('前缀是完整的 /api/v1/doc-workspace（不是相对拼接）', async () => {
    await api.listDocTypes()
    expect(workspace().prefix).toBe(PREFIX)
  })

  it('类型清单打 doc-types', async () => {
    await api.listDocTypes()
    expect(workspace().get).toHaveBeenCalledWith('doc-types')
  })

  it('起草打 draft-by-type，body 原样下发且带放大后的超时', async () => {
    await api.draftByType({
      doc_type: 'jurisdiction_objection',
      case_id: 399,
      facts: {},
      auto_review: true,
      instruction: '管辖条款约定不明',
    })
    const [path, opts] = lastPost()
    expect(path).toBe('draft-by-type')
    expect(opts.json).toEqual({
      doc_type: 'jurisdiction_objection',
      case_id: 399,
      facts: {},
      auto_review: true,
      instruction: '管辖条款约定不明',
    })
    expect(opts.timeout).toBe(api.DRAFT_TIMEOUT_MS)
    expect(api.DRAFT_TIMEOUT_MS).toBeGreaterThan(10_000)
  })
})

describe('doc-generation api：类型清单出参兼容', () => {
  it('{ items: [...] } 形状取出数组', async () => {
    const items = [{ doc_type: 'complaint', display_name: '民事起诉状', family: 'litigation_v1' }]
    workspace().body = { items }
    await expect(api.listDocTypes()).resolves.toEqual(items)
  })

  it('裸数组形状也认（端点早期返回过数组）', async () => {
    const bare = [{ doc_type: 'defense', display_name: '民事答辩状', family: 'litigation_v1' }]
    workspace().body = bare
    await expect(api.listDocTypes()).resolves.toEqual(bare)
  })

  it('items 缺失时不抛，返回空清单', async () => {
    workspace().body = {}
    await expect(api.listDocTypes()).resolves.toEqual([])
  })
})
