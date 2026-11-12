/**
 * copilot memory-api 单测（node 环境）。
 *
 * 只断言「请求怎么构造」：路径、动词、searchParams 的省略规则、请求体字段名
 * （后端是 snake_case，前端是 camelCase，映射写错就是 422）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { get, post, del } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), del: vi.fn() }))

vi.mock('@/lib/api', () => ({ api: { get, post, delete: del } }))

import {
  confirmMemories,
  createMemory,
  fetchMemoryScopes,
  fetchPromoteCandidates,
  forgetMemory,
  listMemories,
  promoteMemory,
  restoreMemory,
} from './memory-api'

const reply = <T,>(value: T) => ({ json: () => Promise.resolve(value) })

beforeEach(() => {
  vi.clearAllMocks()
})

describe('listMemories', () => {
  it('默认只带 limit=100（不传 scope/status 时不发空参数）', async () => {
    get.mockReturnValue(reply([]))
    await expect(listMemories()).resolves.toEqual([])
    expect(get).toHaveBeenCalledWith('agent/memory', { searchParams: { limit: 100 } })
  })

  it('按 scope / status / limit 过滤', async () => {
    get.mockReturnValue(reply([]))
    await listMemories({ scope: 'team', status: 'pending', limit: 20 })
    expect(get).toHaveBeenCalledWith('agent/memory', {
      searchParams: { limit: 20, scope: 'team', status: 'pending' },
    })
  })
})

describe('createMemory', () => {
  it('默认 kind=fact', async () => {
    post.mockReturnValue(reply({ id: 'm1' }))
    await expect(createMemory('我方是承租方')).resolves.toEqual({ id: 'm1' })
    expect(post).toHaveBeenCalledWith('agent/memory', { json: { content: '我方是承租方', kind: 'fact' } })
  })

  it('显式 kind 覆盖默认值', async () => {
    post.mockReturnValue(reply({ id: 'm2' }))
    await createMemory('先发催款函再起诉', 'procedure')
    expect(post).toHaveBeenCalledWith('agent/memory', { json: { content: '先发催款函再起诉', kind: 'procedure' } })
  })
})

describe('forgetMemory / restoreMemory', () => {
  it('软删走 DELETE agent/memory/:id', async () => {
    del.mockReturnValue(reply({ ok: true }))
    await expect(forgetMemory('m-9')).resolves.toEqual({ ok: true })
    expect(del).toHaveBeenCalledWith('agent/memory/m-9')
  })

  it('恢复走 POST agent/memory/:id/restore', async () => {
    post.mockReturnValue(reply({ id: 'm-9', status: 'active' }))
    await expect(restoreMemory('m-9')).resolves.toEqual({ id: 'm-9', status: 'active' })
    expect(post).toHaveBeenCalledWith('agent/memory/m-9/restore', { json: {} })
  })
})

describe('confirmMemories', () => {
  it('确认与否决共用同一端点，accept 决定方向', async () => {
    post.mockReturnValue(reply({ ok: true, affected: 2 }))
    await expect(confirmMemories(['a', 'b'], true)).resolves.toEqual({ ok: true, affected: 2 })
    expect(post).toHaveBeenCalledWith('agent/memory/confirm', { json: { ids: ['a', 'b'], accept: true } })
  })
})

describe('fetchMemoryScopes', () => {
  it('GET agent/memory/scopes', async () => {
    const scopes = { law_firm: { id: 1, can_curate: true }, teams: [] }
    get.mockReturnValue(reply(scopes))
    await expect(fetchMemoryScopes()).resolves.toEqual(scopes)
    expect(get).toHaveBeenCalledWith('agent/memory/scopes')
  })
})

describe('fetchPromoteCandidates', () => {
  it('默认 limit=50，不传 teamId 时不带 team_id', async () => {
    get.mockReturnValue(reply([]))
    await fetchPromoteCandidates({ scope: 'law_firm' })
    expect(get).toHaveBeenCalledWith('agent/memory/promotion/candidates', {
      searchParams: { scope: 'law_firm', limit: 50 },
    })
  })

  it('带 teamId / limit 时转成 snake_case 的 team_id', async () => {
    get.mockReturnValue(reply([]))
    await fetchPromoteCandidates({ scope: 'team', teamId: 3, limit: 10 })
    expect(get).toHaveBeenCalledWith('agent/memory/promotion/candidates', {
      searchParams: { scope: 'team', limit: 10, team_id: 3 },
    })
  })
})

describe('promoteMemory', () => {
  it('camelCase → snake_case 全量映射，省略项补 null / false', async () => {
    post.mockReturnValue(reply({ id: 'm-new' }))
    await promoteMemory({ sourceIds: ['s1', 's2'], content: '争议管辖优先约定在合同签订地', kind: 'playbook', scope: 'team' })
    expect(post).toHaveBeenCalledWith('agent/memory/promotion', {
      json: {
        source_ids: ['s1', 's2'],
        content: '争议管辖优先约定在合同签订地',
        kind: 'playbook',
        scope: 'team',
        team_id: null,
        acknowledged_firm_wide: false,
      },
    })
  })

  it('律所层提交：teamId 与 acknowledgedFirmWide 原样透传', async () => {
    post.mockReturnValue(reply({ id: 'm-firm' }))
    await promoteMemory({
      sourceIds: ['s1'],
      content: '归档前须双人复核',
      kind: 'procedure',
      scope: 'law_firm',
      teamId: 8,
      acknowledgedFirmWide: true,
    })
    expect(post).toHaveBeenCalledWith('agent/memory/promotion', {
      json: expect.objectContaining({ team_id: 8, acknowledged_firm_wide: true, scope: 'law_firm' }),
    })
  })
})
