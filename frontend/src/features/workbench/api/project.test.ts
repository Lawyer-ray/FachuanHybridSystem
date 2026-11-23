/**
 * workbench/api/project 单测（node 环境）。
 *
 * 「新建项目」链路里最容易被改坏的三处口径：
 * - currentLawyerId：先问 organization/me，端点不可用时退回律师列表首位；
 * - createBlankProject：contracts/full 的请求体逐字保持后端初始化口径，
 *   `contracts/full` 不回案件 id，必须按合同 id 回查 cases；
 * - uploadSampleMaterial：与真实上传同一条收件箱入口，且带上传超时
 *   （大 PDF 走 OCR 前置，普通请求超时会误杀）。
 *
 * mock 只打 @/lib/api 的 createApiClient / UPLOAD_TIMEOUT_MS；示例材料的 fetch
 * 与 templates.test 同一套路（stubGlobal + 还原）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const clients = vi.hoisted(() => [] as Array<{
  prefix: string
  get: ReturnType<typeof vi.fn>
  post: ReturnType<typeof vi.fn>
}>)

vi.mock('@/lib/api', () => ({
  UPLOAD_TIMEOUT_MS: 300_000,
  createApiClient: (opts?: { prefix?: string }) => {
    const client = {
      prefix: opts?.prefix ?? '/api/v1',
      get: vi.fn(),
      post: vi.fn(),
    }
    clients.push(client)
    return client
  },
}))

import { UPLOAD_TIMEOUT_MS } from '@/lib/api'

import { DEFAULT_CASE_STAGE, DEFAULT_CASE_TYPE, DEFAULT_FIXED_FEE_AMOUNT } from '../constants'
import { PROJECT_TEMPLATES } from '../templates'
import { createBlankProject, currentLawyerId, uploadSampleMaterial } from './project'

function client(prefix: string) {
  // contracts 前缀有两个客户端（CRUD / folder），第一个才是 project.ts 用的 contractsApi
  const c = clients.find((x) => x.prefix === prefix)
  if (!c) throw new Error(`客户端 ${prefix} 未创建`)
  return c
}

function respond(body: unknown) {
  const p = Promise.resolve(body)
  return Object.assign(p, { json: () => p })
}

function fail(message: string) {
  return { json: () => Promise.reject(new Error(message)) }
}

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('currentLawyerId：me 命中与律师列表兜底', () => {
  it('organization/me 返回 id 时直接用它，不再查律师列表', async () => {
    const api = client('/api/v1/organization')
    api.get.mockReturnValueOnce(respond({ id: 7 }))

    await expect(currentLawyerId()).resolves.toBe(7)
    expect(api.get).toHaveBeenCalledWith('me')
    expect(api.get).not.toHaveBeenCalledWith('lawyers')
  })

  it('me 端点不可用时退回律师列表首位（裸数组形态）', async () => {
    const api = client('/api/v1/organization')
    api.get.mockReturnValueOnce(fail('404'))
    api.get.mockReturnValueOnce(respond([{ id: 11 }, { id: 22 }]))

    await expect(currentLawyerId()).resolves.toBe(11)
    expect(api.get).toHaveBeenNthCalledWith(2, 'lawyers')
  })

  it('律师列表是分页对象形态时同样取 items 首位', async () => {
    const api = client('/api/v1/organization')
    api.get.mockReturnValueOnce(respond({ id: null }))
    api.get.mockReturnValueOnce(respond({ items: [{ id: 33 }] }))

    await expect(currentLawyerId()).resolves.toBe(33)
  })

  it('me 与律师列表都拿不到 id 时报「无法确定当前律师」', async () => {
    const api = client('/api/v1/organization')
    api.get.mockReturnValueOnce(fail('404'))
    api.get.mockReturnValueOnce(respond([]))

    await expect(currentLawyerId()).rejects.toThrow('无法确定当前律师，请重新登录后重试')
  })
})

describe('createBlankProject：请求体与案件回查', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-20T08:00:00Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('请求体按后端初始化口径逐字组装（默认案型/阶段/固定收费）', async () => {
    const contracts = client('/api/v1/contracts')
    const cases = client('/api/v1/cases')
    contracts.post.mockReturnValueOnce(respond({ id: 55 }))
    cases.get.mockReturnValueOnce(respond([{ id: 7, contract_id: 55 }]))

    await createBlankProject('某某公司顾问项目', 12)

    expect(contracts.post).toHaveBeenCalledWith('contracts/full', {
      json: {
        name: '某某公司顾问项目',
        case_type: DEFAULT_CASE_TYPE,
        status: 'active',
        start_date: '2026-10-20',
        lawyer_ids: [12],
        fee_mode: 'FIXED',
        fixed_amount: DEFAULT_FIXED_FEE_AMOUNT,
        cases: [
          {
            name: '某某公司顾问项目·案件',
            case_type: DEFAULT_CASE_TYPE,
            status: 'active',
            current_stage: DEFAULT_CASE_STAGE,
            cause_of_action: '',
          },
        ],
      },
    })
  })

  it('按合同 id 回查刚建的案件：返回案件 id 与合同 id', async () => {
    const contracts = client('/api/v1/contracts')
    const cases = client('/api/v1/cases')
    contracts.post.mockReturnValueOnce(respond({ id: 55 }))
    cases.get.mockReturnValueOnce(
      respond([
        { id: 7, contract_id: 56 },
        { id: 8, contract_id: 55 },
      ]),
    )

    await expect(createBlankProject('项目甲', 12)).resolves.toEqual({ caseId: 8, contractId: 55 })
    expect(cases.get).toHaveBeenCalledWith('cases')
  })

  it('合同建成功但回查不到对应案件时抛错（不返回半套 id）', async () => {
    const contracts = client('/api/v1/contracts')
    const cases = client('/api/v1/cases')
    contracts.post.mockReturnValueOnce(respond({ id: 55 }))
    cases.get.mockReturnValueOnce(respond([{ id: 7, contract_id: 56 }]))

    await expect(createBlankProject('项目乙', 12)).rejects.toThrow('建项目失败：建完案件后查不到')
  })
})

describe('uploadSampleMaterial：与真实上传同一条入口', () => {
  it('示例材料走 inbox messages/upload，并带上传超时与主题', async () => {
    const blob = new Blob(['%PDF-1.4'], { type: 'application/pdf' })
    const fetchMock = vi.fn(async () => ({ ok: true, blob: async () => blob }))
    vi.stubGlobal('fetch', fetchMock)
    const inbox = client('/api/v1/inbox')
    inbox.post.mockReturnValueOnce(respond({}))

    const template = PROJECT_TEMPLATES[0]!
    await uploadSampleMaterial(template)

    expect(fetchMock).toHaveBeenCalledWith(template.sample.file)
    expect(inbox.post).toHaveBeenCalledWith('messages/upload', {
      body: expect.any(FormData),
      timeout: UPLOAD_TIMEOUT_MS,
    })
    const body = inbox.post.mock.calls[0]![1].body as FormData
    expect(body.get('subject')).toBe(template.sample.label)
    const file = body.get('files') as File
    expect(file.name).toBe(decodeURIComponent(template.sample.file.split('/').pop()!))
  })
})
