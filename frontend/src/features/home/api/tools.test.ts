/**
 * home/api/tools 单测（node 环境）。
 *
 * mock 打 @/lib/api（createApiClient / UPLOAD_TIMEOUT_MS）与 ./download
 * （withAuthToken / API_BASE_URL），断言聚焦：提交信封的业务失败兜底、
 * 转换产物的 filename 解析、任务进度投影与历史分页参数。
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
  UPLOAD_TIMEOUT_MS: 300_000,
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

vi.mock('./download', () => ({
  API_BASE_URL: '/api/v1',
  // 安全审计 M-2：票据换取是异步的
  withAuthToken: (url: string) => Promise.resolve(`${url}?ticket=fake`),
}))

import {
  convertDocument,
  converterDownloadUrl,
  converterItemDownloadUrl,
  convertRecordDownloadUrl,
  copyConverterItemsToClipboard,
  createConverterJob,
  deleteConvertRecord,
  getConverterJob,
  listConvertRecords,
  listConvertTemplates,
  listConverterJobs,
  submitCourtSms,
} from './tools'

function client(prefix: string) {
  const c = clients.find((x) => x.prefix === prefix)
  if (!c) throw new Error(`客户端 ${prefix} 未创建`)
  return c
}

function respond(body: unknown) {
  const p = Promise.resolve(body)
  return Object.assign(p, { json: () => p })
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('submitCourtSms（提交信封）', () => {
  it('成功：返回 data.id', async () => {
    const api = client('/api/v1/automation')
    api.post.mockReturnValueOnce(respond({ success: true, data: { id: 42, status: 'pending' } }))
    await expect(submitCourtSms('短信正文')).resolves.toBe(42)
    expect(api.post).toHaveBeenCalledWith('court-sms', { json: { content: '短信正文' } })
  })

  it('业务失败（200 + success:false）：抛后端 message；缺 id 也兜底抛错', async () => {
    const api = client('/api/v1/automation')
    api.post.mockReturnValueOnce(respond({ success: false, message: '解析失败', data: {} }))
    await expect(submitCourtSms('x')).rejects.toThrow('解析失败')

    api.post.mockReturnValueOnce(respond({ success: true, data: {} }))
    await expect(submitCourtSms('x')).rejects.toThrow('短信提交失败')
  })
})

describe('模板列表', () => {
  it('listConvertTemplates：GET mbid-list，categories 缺省兜底 []', async () => {
    const api = client('/api/v1/doc-convert')
    const cats = [{ category: '民事', items: [] }]
    api.get.mockReturnValueOnce(respond({ categories: cats }))
    await expect(listConvertTemplates()).resolves.toBe(cats)

    api.get.mockReturnValueOnce(respond({}))
    await expect(listConvertTemplates()).resolves.toEqual([])
  })
})

describe('convertDocument（二进制产物 + filename 解析）', () => {
  function binResponse(blob: Blob, disposition: string) {
    return Promise.resolve({
      blob: async () => blob,
      headers: { get: (k: string) => (k.toLowerCase() === 'content-disposition' ? disposition : null) },
    })
  }

  it('响应头带 filename=...：解码使用服务端命名', async () => {
    const api = client('/api/v1/doc-convert')
    const blob = new Blob(['docx'])
    api.post.mockReturnValueOnce(binResponse(blob, 'attachment; filename="court_doc.docx"'))
    const res = await convertDocument('MB001', new File(['d'], '起诉状.doc'))
    expect(res.blob).toBe(blob)
    expect(res.filename).toBe('court_doc.docx')
  })

  it('RFC 5987 filename*（UTF-8 百分号编码）：percent-decode', async () => {
    const api = client('/api/v1/doc-convert')
    api.post.mockReturnValueOnce(binResponse(new Blob(['x']), "attachment; filename*=UTF-8''%E6%8A%A5%E4%BB%B7%E5%8D%95.docx"))
    const res = await convertDocument('MB001', new File(['d'], '起诉状.doc'))
    expect(res.filename).toBe('报价单.docx')
  })

  it('响应头缺 filename：回退「原名去后缀-要素式.docx」', async () => {
    const api = client('/api/v1/doc-convert')
    api.post.mockReturnValueOnce(binResponse(new Blob(['x']), ''))
    const res = await convertDocument('MB001', new File(['d'], '起诉状材料.doc'))
    expect(res.filename).toBe('起诉状材料-要素式.docx')
  })
})

describe('DOC 转 DOCX 任务', () => {
  it('createConverterJob：多文件进 FormData files[]，成功返回 job_id', async () => {
    const api = client('/api/v1/doc-converter')
    api.post.mockReturnValueOnce(respond({ success: true, job_id: 'job-9' }))
    const files = [new File(['a'], 'a.doc'), new File(['b'], 'b.doc')]
    await expect(createConverterJob(files)).resolves.toBe('job-9')
    const [path, opts] = api.post.mock.calls[0]! as [string, { body: FormData; timeout: number }]
    expect(path).toBe('jobs')
    expect(opts.body.getAll('files').map((f) => (f as File).name)).toEqual(['a.doc', 'b.doc'])
    expect(opts.timeout).toBe(300_000)
  })

  it('createConverterJob 业务失败 / 缺 job_id：抛 message 或默认文案', async () => {
    const api = client('/api/v1/doc-converter')
    api.post.mockReturnValueOnce(respond({ success: false, message: '队列已满' }))
    await expect(createConverterJob([])).rejects.toThrow('队列已满')

    api.post.mockReturnValueOnce(respond({}))
    await expect(createConverterJob([])).rejects.toThrow('创建转换任务失败')
  })

  it('getConverterJob：JobProgressOut → 前端投影（改名 / 兜底 / ok 推导）', async () => {
    const api = client('/api/v1/doc-converter')
    api.get.mockReturnValueOnce(
      respond({
        job: { id: 'job-9', status: 'completed', total_files: 3, converted_files: 2, failed_files: 1, download_url: '/zip' },
        items: [
          { id: 7, original_name: '起诉状.doc', download_url: '/d/7' },
          { id: 8, original_name: undefined, download_url: undefined },
        ],
      }),
    )
    const job = await getConverterJob('job-9')
    expect(job).toEqual({
      jobId: 'job-9',
      status: 'completed',
      total: 3,
      done: 2,
      failed: 1,
      items: [
        { id: '7', name: '起诉状.docx', ok: true, downloadUrl: '/d/7' },
        // original_name 缺省 → 未命名；download_url 缺省 → ok:false
        { id: '8', name: '未命名.docx', ok: false, downloadUrl: '' },
      ],
    })
  })

  it('listConverterJobs：page 进查询参数，行投影 hasZip 由 download_url 推导', async () => {
    const api = client('/api/v1/doc-converter')
    api.get.mockReturnValueOnce(
      respond({
        items: [
          { id: 'j1', status: 'completed', total_files: 2, converted_files: 2, failed_files: 0, download_url: '/zip', created_at: '2026-10-01T00:00:00' },
          { id: 'j2', status: 'failed', total_files: 1, converted_files: 0, failed_files: 1, download_url: '', created_at: undefined },
        ],
        count: 2,
        page: 1,
        num_pages: 1,
      }),
    )
    const res = await listConverterJobs(1)
    expect(api.get).toHaveBeenCalledWith('jobs', { searchParams: { page: '1' } })
    expect(res.items[0]).toMatchObject({ id: 'j1', hasZip: true, createdAt: '2026-10-01T00:00:00' })
    expect(res.items[1]).toMatchObject({ id: 'j2', hasZip: false, createdAt: '' })
    expect(res.count).toBe(2)
  })

  it('下载直链：拼 API_BASE_URL 并带 token；剪贴板复制走 POST copy-to-clipboard', async () => {
    await expect(converterDownloadUrl('job-9')).resolves.toBe('/api/v1/doc-converter/jobs/job-9/download?ticket=fake')
    await expect(converterItemDownloadUrl('job-9', '7')).resolves.toBe(
      '/api/v1/doc-converter/jobs/job-9/items/7/download?ticket=fake',
    )
    await expect(convertRecordDownloadUrl(15)).resolves.toBe('/api/v1/doc-convert/records/15/download?ticket=fake')
  })

  it('copyConverterItemsToClipboard：POST item_ids，响应直通', async () => {
    const api = client('/api/v1/doc-converter')
    const out = { success: true, copied: 2, reason: null }
    api.post.mockReturnValueOnce(respond(out))
    await expect(copyConverterItemsToClipboard('job-9', ['7', '8'])).resolves.toBe(out)
    expect(api.post).toHaveBeenCalledWith('jobs/job-9/items/copy-to-clipboard', { json: { item_ids: ['7', '8'] } })
  })
})

describe('要素式转换历史', () => {
  it('listConvertRecords：status 可选进查询参数，page 必带', async () => {
    const api = client('/api/v1/doc-convert')
    const page = { items: [], count: 0, page: 2, num_pages: 5 }
    api.get.mockReturnValueOnce(respond(page))
    await expect(listConvertRecords('success', 2)).resolves.toBe(page)
    expect(api.get).toHaveBeenCalledWith('records', { searchParams: { status: 'success', page: '2' } })

    api.get.mockReturnValueOnce(respond(page))
    await listConvertRecords(undefined, 1)
    expect(api.get).toHaveBeenLastCalledWith('records', { searchParams: { page: '1' } })
  })

  it('deleteConvertRecord：DELETE records/:id', async () => {
    const api = client('/api/v1/doc-convert')
    api.delete.mockReturnValueOnce(respond({}))
    await deleteConvertRecord(15)
    expect(api.delete).toHaveBeenCalledWith('records/15')
  })
})
