/**
 * bank-litigation api 层单测（node 环境）。
 *
 * mock 只打 HTTP 客户端工厂（@/lib/api 的 createApiClient）：六个不同 prefix 的
 * 客户端（cases / doc-convert / oa-filing / court-filing / oa-stamp / oa-archive /
 * pdf-splitting）各自可寻址，断言聚焦「请求参数构造」，不测 ky 本身。
 *
 * ⚠️ 本文件顺带充当**路径层级防回归网**：cases 的列表/详情是双层 `cases/cases`，
 * 子资源是单层 `<id>/...`。踩过的坑是子资源也写成 `cases/${id}/...` → 404，
 * 而界面表现成「起诉条件校验失败」，看着像业务错误。每条 cases 断言都钉住层级。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { clients } = vi.hoisted(() => ({
  clients: [] as Array<{
    prefix: string
    get: ReturnType<typeof vi.fn>
    post: ReturnType<typeof vi.fn>
    put: ReturnType<typeof vi.fn>
    delete: ReturnType<typeof vi.fn>
  }>,
}))

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
  applyArchive,
  applyStamp,
  bindMaterials,
  cancelSplitJob,
  confirmSplitJob,
  convertToElemental,
  createSplitJob,
  downloadSplitZip,
  executeCourtFiling,
  executeOAFiling,
  getArchiveSession,
  getCase,
  getCaseFilingInfo,
  getCourtFilingSession,
  getMaterialStatus,
  getOAFilingSession,
  getReadiness,
  getSplitJob,
  getStampSession,
  listBindCandidates,
  listCases,
  listConvertRecords,
  listMbidTypes,
  listOAConfigs,
  lookupArchiveContract,
  lookupStampContract,
  openContractInOA,
  runConflictCheck,
  uploadCaseMaterials,
} from './index'

/** 按前缀取 mock 客户端（模块加载时各客户端已按 prefix 建好） */
function client(prefix: string) {
  const c = clients.find((x) => x.prefix === prefix)
  if (!c) throw new Error(`客户端 ${prefix} 未创建`)
  return c
}

/** ky ResponsePromise 形状桩：同步可链 .json()，await 得 body */
function respond(body: unknown) {
  const p = Promise.resolve(body)
  return Object.assign(p, { json: () => p })
}

/** 二进制响应桩：可链 .blob() */
function blobResponse(blob: Blob) {
  const p = Promise.resolve({ blob: () => Promise.resolve(blob) })
  return p
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('客户端按域拆分', () => {
  it('七个 prefix 各建一个客户端，路径只写后半段', () => {
    const prefixes = clients.map((c) => c.prefix).sort()
    expect(prefixes).toEqual([
      '/api/v1/cases',
      '/api/v1/court-filing',
      '/api/v1/doc-convert',
      '/api/v1/oa-archive',
      '/api/v1/oa-filing',
      '/api/v1/oa-stamp',
      '/api/v1/pdf-splitting',
    ])
  })
})

describe('案件资源（层级不统一，逐条钉住）', () => {
  it('listCases：双层 cases', async () => {
    const api = client('/api/v1/cases')
    api.get.mockReturnValueOnce(respond([{ id: 1 }]))
    await expect(listCases()).resolves.toEqual([{ id: 1 }])
    expect(api.get).toHaveBeenCalledWith('cases')
  })

  it('getCase：双层 cases/:id', async () => {
    const api = client('/api/v1/cases')
    api.get.mockReturnValueOnce(respond({ id: 406 }))
    await getCase(406)
    expect(api.get).toHaveBeenCalledWith('cases/406')
  })

  it('子资源是单层：material-status / readiness 都直接挂 <id> 下', async () => {
    const api = client('/api/v1/cases')
    api.get.mockReturnValueOnce(respond({})).mockReturnValueOnce(respond({}))
    await getMaterialStatus(406)
    await getReadiness(406)
    expect(api.get).toHaveBeenNthCalledWith(1, '406/material-status')
    expect(api.get).toHaveBeenNthCalledWith(2, '406/readiness')
  })

  it('runConflictCheck 走 POST 子资源（有副作用：会写审计）', async () => {
    const api = client('/api/v1/cases')
    api.post.mockReturnValueOnce(respond({ level: 'neutral' }))
    await expect(runConflictCheck(406)).resolves.toEqual({ level: 'neutral' })
    expect(api.post).toHaveBeenCalledWith('406/conflict-check')
  })

  it('bindMaterials：POST <id>/materials/bind，items 进 json body', async () => {
    const api = client('/api/v1/cases')
    api.post.mockReturnValueOnce(respond({ saved_count: 2 }))
    const items = [{ attachment_id: 11, category: '证据', type_name: '借款合同' }]
    await expect(bindMaterials(406, items)).resolves.toEqual({ saved_count: 2 })
    expect(api.post).toHaveBeenCalledWith('406/materials/bind', { json: { items } })
  })

  it('uploadCaseMaterials：字段名是 files（复数），每个文件各 append 一次，超时走上传档', async () => {
    const api = client('/api/v1/cases')
    api.post.mockReturnValueOnce(respond({ log_id: 1, attachment_ids: [7, 8] }))
    const f1 = new File(['a'], 'a.pdf', { type: 'application/pdf' })
    const f2 = new File(['b'], 'b.pdf', { type: 'application/pdf' })

    await uploadCaseMaterials(406, [f1, f2])

    const [path, opts] = api.post.mock.calls[0]!
    expect(path).toBe('406/materials/upload')
    expect(opts.body).toBeInstanceOf(FormData)
    // ⚠️ 写成 file（单数）后端会静默成功但返回空 attachment_ids
    const names = (opts.body as FormData).getAll('files')
    expect(names).toHaveLength(2)
    expect((names[0] as File).name).toBe('a.pdf')
    expect((names[1] as File).name).toBe('b.pdf')
    expect(opts.timeout).toBe(300_000)
  })

  it('listBindCandidates：GET bind-candidates（已上传但还没变成材料的附件）', async () => {
    const api = client('/api/v1/cases')
    api.get.mockReturnValueOnce(respond([]))
    await expect(listBindCandidates(406)).resolves.toEqual([])
    expect(api.get).toHaveBeenCalledWith('406/materials/bind-candidates')
  })
})

describe('要素式转换', () => {
  it('listMbidTypes：GET mbid-list', async () => {
    const api = client('/api/v1/doc-convert')
    const list = { categories: [{ category: '起诉状', items: [] }] }
    api.get.mockReturnValueOnce(respond(list))
    await expect(listMbidTypes()).resolves.toBe(list)
    expect(api.get).toHaveBeenCalledWith('mbid-list')
  })

  it('convertToElemental：FormData 走 body（不是 json），回 .blob() 且超时 2 分钟', async () => {
    const api = client('/api/v1/doc-convert')
    const blob = new Blob(['docx'])
    api.post.mockReturnValueOnce(blobResponse(blob))
    const file = new File(['x'], '起诉状.docx')

    await expect(convertToElemental(file, 'jrjkqsz')).resolves.toBe(blob)

    const [path, opts] = api.post.mock.calls[0]!
    expect(path).toBe('convert')
    // ⚠️ 写成 json 会让 ky 去序列化 FormData，请求发不出去，界面永远停在「转换中…」
    expect(opts.json).toBeUndefined()
    expect(opts.body).toBeInstanceOf(FormData)
    expect((opts.body as FormData).get('mbid')).toBe('jrjkqsz')
    expect(((opts.body as FormData).get('file') as File).name).toBe('起诉状.docx')
    expect(opts.timeout).toBe(120_000)
  })

  it('listConvertRecords：GET records', async () => {
    const api = client('/api/v1/doc-convert')
    api.get.mockReturnValueOnce(respond({ items: [] }))
    await expect(listConvertRecords()).resolves.toEqual({ items: [] })
    expect(api.get).toHaveBeenCalledWith('records')
  })
})

describe('律所 OA 立案', () => {
  it('listOAConfigs：GET configs', async () => {
    const api = client('/api/v1/oa-filing')
    api.get.mockReturnValueOnce(respond([{ id: 1 }]))
    await expect(listOAConfigs()).resolves.toEqual([{ id: 1 }])
    expect(api.get).toHaveBeenCalledWith('configs')
  })

  it('executeOAFiling：POST execute，payload 进 json body', async () => {
    const api = client('/api/v1/oa-filing')
    api.post.mockReturnValueOnce(respond({ id: 9, status: 'pending' }))
    const payload = { contract_id: 3, site_name: '某某律所OA' }
    await expect(executeOAFiling(payload)).resolves.toEqual({ id: 9, status: 'pending' })
    expect(api.post).toHaveBeenCalledWith('execute', { json: payload })
  })

  it('getOAFilingSession：GET session/:id', async () => {
    const api = client('/api/v1/oa-filing')
    api.get.mockReturnValueOnce(respond({ id: 9, status: 'success' }))
    await getOAFilingSession(9)
    expect(api.get).toHaveBeenCalledWith('session/9')
  })
})

describe('一张网立案', () => {
  it('getCaseFilingInfo：GET case-info/:caseId（案号在前缀后第一段）', async () => {
    const api = client('/api/v1/court-filing')
    api.get.mockReturnValueOnce(respond({ case_id: 406 }))
    await getCaseFilingInfo(406)
    expect(api.get).toHaveBeenCalledWith('case-info/406')
  })

  it('executeCourtFiling 与 getCourtFilingSession 共用 execute / session/:id', async () => {
    const api = client('/api/v1/court-filing')
    api.post.mockReturnValueOnce(respond({ session_id: 5 }))
    api.get.mockReturnValueOnce(respond({ session_id: 5, status: 'running' }))
    const payload = { case_id: 406 }

    await executeCourtFiling(payload)
    await getCourtFilingSession(5)

    expect(api.post).toHaveBeenCalledWith('execute', { json: payload })
    expect(api.get).toHaveBeenCalledWith('session/5')
  })
})

describe('OA 盖章（入参是 file_path，不是 contract_id）', () => {
  it('lookupStampContract / applyStamp 都收 StampApplyIn', async () => {
    const api = client('/api/v1/oa-stamp')
    api.post.mockReturnValueOnce(respond({ contract_name: 'A 合同' })).mockReturnValueOnce(respond({ id: 1 }))
    const payload = { file_path: '/case/起诉状.pdf', site_name: '某某律所OA' }

    await expect(lookupStampContract(payload)).resolves.toEqual({ contract_name: 'A 合同' })
    await applyStamp(payload)

    expect(api.post).toHaveBeenNthCalledWith(1, 'lookup', { json: payload })
    expect(api.post).toHaveBeenNthCalledWith(2, 'apply', { json: payload })
  })

  it('getStampSession：GET session/:id', async () => {
    const api = client('/api/v1/oa-stamp')
    api.get.mockReturnValueOnce(respond({ id: 1, status: 'success' }))
    await getStampSession(1)
    expect(api.get).toHaveBeenCalledWith('session/1')
  })
})

describe('OA 归档', () => {
  it('lookupArchiveContract / applyArchive 都收 ArchiveApplyIn（文件路径是数组）', async () => {
    const api = client('/api/v1/oa-archive')
    api.post.mockReturnValueOnce(respond({ contract_name: 'A 合同' })).mockReturnValueOnce(respond({ id: 2 }))
    const payload = { file_paths: ['/case/判决书.pdf', '/case/裁定书.pdf'], site_name: '某某律所OA' }

    await lookupArchiveContract(payload)
    await applyArchive(payload)

    expect(api.post).toHaveBeenNthCalledWith(1, 'lookup', { json: payload })
    expect(api.post).toHaveBeenNthCalledWith(2, 'apply', { json: payload })
  })

  it('getArchiveSession：GET session/:id', async () => {
    const api = client('/api/v1/oa-archive')
    api.get.mockReturnValueOnce(respond({ id: 2, status: 'running' }))
    await getArchiveSession(2)
    expect(api.get).toHaveBeenCalledWith('session/2')
  })

  it('openContractInOA：POST open-oa（只把用户带去 OA 页面，不跑自动化）', async () => {
    const api = client('/api/v1/oa-archive')
    api.post.mockReturnValueOnce(respond({ success: true, message: '已打开' }))
    // OpenOAIn 的三个字段都是必填（description / site_name 后端有默认值，但生成物不标 optional）。
    // 这里验的是入参【原样透传】，site_name 的取值不影响断言，故用中性占位值。
    const payload = { contract_id: 3, description: '详见卷宗', site_name: 'OA站点' }
    await expect(openContractInOA(payload)).resolves.toEqual({ success: true, message: '已打开' })
    expect(api.post).toHaveBeenCalledWith('open-oa', { json: payload })
  })
})

describe('整包 PDF 分段', () => {
  it('createSplitJob：默认模板 filing_materials_v1，固定 content_analysis + balanced，超时 5 分钟', async () => {
    const api = client('/api/v1/pdf-splitting')
    api.post.mockReturnValueOnce(respond({ job_id: 'j1', status: 'queued' }))
    const file = new File(['pdf'], '整包.pdf')

    await expect(createSplitJob(file)).resolves.toEqual({ job_id: 'j1', status: 'queued' })

    const [path, opts] = api.post.mock.calls[0]!
    expect(path).toBe('jobs')
    const form = opts.body as FormData
    expect(form).toBeInstanceOf(FormData)
    expect((form.get('file') as File).name).toBe('整包.pdf')
    expect(form.get('split_mode')).toBe('content_analysis')
    expect(form.get('template_key')).toBe('filing_materials_v1')
    expect(form.get('ocr_profile')).toBe('balanced')
    expect(opts.timeout).toBe(300_000)
  })

  it('createSplitJob：显式传二审模板时透传（选错模板会让模型把判决书全判 unrecognized）', async () => {
    const api = client('/api/v1/pdf-splitting')
    api.post.mockReturnValueOnce(respond({ job_id: 'j2', status: 'queued' }))
    await createSplitJob(new File(['pdf'], '二审包.pdf'), 'appeal_defense_v1')
    expect((api.post.mock.calls[0]![1].body as FormData).get('template_key')).toBe('appeal_defense_v1')
  })

  it('getSplitJob：GET jobs/:id', async () => {
    const api = client('/api/v1/pdf-splitting')
    api.get.mockReturnValueOnce(respond({ job_id: 'j1', status: 'running' }))
    await getSplitJob('j1')
    expect(api.get).toHaveBeenCalledWith('jobs/j1')
  })

  it('cancelSplitJob：POST jobs/:id/cancel', async () => {
    const api = client('/api/v1/pdf-splitting')
    api.post.mockReturnValueOnce(respond({ job_id: 'j1', status: 'cancelled' }))
    await cancelSplitJob('j1')
    expect(api.post).toHaveBeenCalledWith('jobs/j1/cancel')
  })

  it('confirmSplitJob：segments 包成 { segments } 进 json，超时 5 分钟', async () => {
    const api = client('/api/v1/pdf-splitting')
    api.post.mockReturnValueOnce(respond({ job_id: 'j1', status: 'exporting' }))
    const segments = [
      { id: 1, order: 1, page_start: 1, page_end: 4, segment_type: 'complaint', filename: '01.pdf' },
    ]

    await confirmSplitJob('j1', segments)

    expect(api.post).toHaveBeenCalledWith('jobs/j1/confirm', { json: { segments }, timeout: 300_000 })
  })

  it('downloadSplitZip：GET jobs/:id/download 并回 .blob()（结果是 zip，不是 JSON）', async () => {
    const api = client('/api/v1/pdf-splitting')
    const zip = new Blob(['PK'])
    api.get.mockReturnValueOnce(blobResponse(zip))
    await expect(downloadSplitZip('j1')).resolves.toBe(zip)
    expect(api.get).toHaveBeenCalledWith('jobs/j1/download', { timeout: 300_000 })
  })
})
