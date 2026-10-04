/**
 * material-prep api 层单测（node 环境）。
 *
 * mock 只打 HTTP 客户端工厂（@/lib/api 的 createApiClient）：四个不同 prefix 的
 * 客户端（inbox / client / pdf-splitting / 默认 core）各自可寻址，断言聚焦
 * 「请求参数构造」与「信封 / 缓存语义」（setPackStatusRemote 的草稿回写合并、
 * fetchAttachmentBytes 的同 key 复用与失败重试），不测 ky 本身。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { clients, uploadTimeout } = vi.hoisted(() => ({
  clients: [] as Array<{
    prefix: string
    get: ReturnType<typeof vi.fn>
    post: ReturnType<typeof vi.fn>
    put: ReturnType<typeof vi.fn>
    delete: ReturnType<typeof vi.fn>
  }>,
  uploadTimeout: 300_000,
}))

vi.mock('@/lib/api', () => ({
  UPLOAD_TIMEOUT_MS: uploadTimeout,
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
  appendPackFiles,
  clearBytesCache,
  createPdfSplitJob,
  deletePack,
  fetchAttachmentBytes,
  getPackDetail,
  getPdfSplitJob,
  listMaterialPacks,
  ocrImage,
  renamePack,
  saveDraft,
  searchCases,
  searchClients,
  setPackStatusRemote,
  uploadPack,
} from './api'

/** 按前缀取 mock 客户端（模块加载时四个客户端已按 prefix 建好） */
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

/** fetchAttachmentBytes 的响应桩：可链 .arrayBuffer() */
function bytesResponse(buf: ArrayBuffer) {
  return Promise.resolve({ arrayBuffer: () => Promise.resolve(buf) })
}

beforeEach(() => {
  vi.clearAllMocks()
  clearBytesCache()
})

describe('收件箱资源封装', () => {
  it('listMaterialPacks：固定 manual_upload + has_attachments 查询参数（收件箱里筛出材料包）', async () => {
    const inbox = client('/api/v1/inbox')
    inbox.get.mockReturnValueOnce(respond([]))
    await listMaterialPacks()
    expect(inbox.get).toHaveBeenCalledWith('messages', {
      searchParams: { source_type: 'manual_upload', has_attachments: 'true' },
    })
  })

  it('getPackDetail 走 GET、deletePack 走 DELETE，同拼 messages/:id 路径', async () => {
    const inbox = client('/api/v1/inbox')
    inbox.get.mockReturnValueOnce(respond({ id: 3 }))
    inbox.delete.mockReturnValueOnce(respond({ ok: true }))
    await getPackDetail(3)
    await deletePack(3)
    expect(inbox.get).toHaveBeenCalledWith('messages/3')
    expect(inbox.delete).toHaveBeenCalledWith('messages/3')
  })

  it('renamePack：PUT messages/:id，subject 进 json body', async () => {
    const inbox = client('/api/v1/inbox')
    inbox.put.mockReturnValueOnce(respond({ ok: true }))
    await renamePack(3, '起诉状材料')
    expect(inbox.put).toHaveBeenCalledWith('messages/3', { json: { subject: '起诉状材料' } })
  })

  it('uploadPack：FormData 携带全部文件，subject 可选，超时走上传档位', async () => {
    const inbox = client('/api/v1/inbox')
    inbox.post.mockReturnValue(respond({}))
    const f1 = new File(['a'], 'a.pdf', { type: 'application/pdf' })
    const f2 = new File(['b'], 'b.jpg', { type: 'image/jpeg' })

    await uploadPack([f1, f2], '新包标题')
    const withSubject = inbox.post.mock.calls[0]!
    expect(withSubject[0]).toBe('messages/upload')
    expect(withSubject[1].body).toBeInstanceOf(FormData)
    // FormData 取出的 File 是新包装对象（非同引用），按名与内容比对
    const filesOf = (fd: FormData) => fd.getAll('files').map((x) => (x as File).name)
    expect(filesOf(withSubject[1].body)).toEqual(['a.pdf', 'b.jpg'])
    expect(withSubject[1].body.get('subject')).toBe('新包标题')
    expect(withSubject[1].timeout).toBe(uploadTimeout)

    // 不带 subject：FormData 里不出现 subject 键
    await uploadPack([f1])
    const withoutSubject = inbox.post.mock.calls[1]!
    expect(withoutSubject[1].body.has('subject')).toBe(false)
    expect(filesOf(withoutSubject[1].body)).toEqual(['a.pdf'])
  })

  it('appendPackFiles：POST messages/:id/attachments，文件进 FormData', async () => {
    const inbox = client('/api/v1/inbox')
    inbox.post.mockReturnValueOnce(respond({}))
    const f = new File(['x'], 'x.pdf')
    await appendPackFiles(7, [f])
    expect(inbox.post).toHaveBeenCalledWith('messages/7/attachments', expect.objectContaining({ timeout: uploadTimeout }))
    const [, opts] = inbox.post.mock.calls[0]! as [string, { body: FormData }]
    expect(opts.body.getAll('files')).toEqual([f])
    expect(opts.body.has('subject')).toBe(false)
  })

  it('saveDraft：PUT messages/:id/draft，整份草稿作为 draft 字段回写', async () => {
    const inbox = client('/api/v1/inbox')
    inbox.put.mockReturnValueOnce(respond({}))
    const draft = { mats: [], segs: [], infos: [] }
    await saveDraft(7, draft)
    expect(inbox.put).toHaveBeenCalledWith('messages/7/draft', { json: { draft } })
  })
})

describe('setPackStatusRemote 信封回写', () => {
  it('未拆分过的包（draft_state 为 {}）原样回写：只补 status，不造 assign 键', async () => {
    const inbox = client('/api/v1/inbox')
    inbox.get.mockReturnValueOnce(respond({ id: 1, draft_state: {} }))
    inbox.put.mockReturnValueOnce(respond({}))
    await setPackStatusRemote(1, 'done')
    expect(inbox.get).toHaveBeenCalledWith('messages/1')
    expect(inbox.put).toHaveBeenCalledWith('messages/1/draft', {
      json: { draft: { status: 'done' } },
    })
  })

  it('已拆分包保留既有草稿内容，status 覆盖、assign 有值才写入', async () => {
    const inbox = client('/api/v1/inbox')
    const stored = { mats: [{ partIndex: 0, n: 'a.pdf', k: 'pdf', pages: 2 }], segs: [], infos: [] }
    inbox.get.mockReturnValueOnce(respond({ id: 2, draft_state: { ...stored, status: 'todo' } }))
    inbox.put.mockReturnValueOnce(respond({}))
    await setPackStatusRemote(2, 'filed', { target: 'existing', caseId: 9 })
    const [, opts] = inbox.put.mock.calls[0]! as [string, { json: { draft: object } }]
    expect(opts.json.draft).toEqual({
      ...stored,
      status: 'filed',
      assign: { target: 'existing', caseId: 9 },
    })
  })
})

describe('OCR 与检索', () => {
  it('ocrImage：POST ocr，Blob 以 page.png 文件名进 FormData', async () => {
    const inbox = client('/api/v1/inbox')
    inbox.post.mockReturnValueOnce(respond({ width: 100, height: 50, blocks: [] }))
    const blob = new Blob(['png-bytes'], { type: 'image/png' })
    await ocrImage(blob)
    const [path, opts] = inbox.post.mock.calls[0]! as [string, { body: FormData }]
    expect(path).toBe('ocr')
    const file = opts.body.get('file')
    expect(file).toBeInstanceOf(File)
    expect((file as File).name).toBe('page.png')
  })

  it('searchCases：空白词短路返回 []（零请求）；非空带 q 与 limit=10 走 core 客户端', async () => {
    const core = client('/api/v1')
    await expect(searchCases('   ')).resolves.toEqual([])
    expect(core.get).not.toHaveBeenCalled()

    const rows = [{ id: 1, name: '案件A' }]
    core.get.mockReturnValueOnce(respond(rows))
    await expect(searchCases('王五')).resolves.toBe(rows)
    expect(core.get).toHaveBeenCalledWith('cases/search', {
      searchParams: { q: '王五', limit: '10' },
      signal: undefined,
    })
  })

  it('searchClients：isOurClient 转字符串查询参数，signal 透传支持取消', async () => {
    const clientApi = client('/api/v1/client')
    clientApi.get.mockReturnValue(respond([]))
    const ac = new AbortController()
    await searchClients('李四', true, ac.signal)
    expect(clientApi.get).toHaveBeenCalledWith('parties/search', {
      searchParams: { keyword: '李四', is_our_client: 'true' },
      signal: ac.signal,
    })
    await searchClients('李四', false)
    expect(clientApi.get).toHaveBeenLastCalledWith('parties/search', {
      searchParams: { keyword: '李四', is_our_client: 'false' },
      signal: undefined,
    })
  })
})

describe('fetchAttachmentBytes 字节缓存', () => {
  it('同 messageId:partIndex 复用同一份 Promise（多次取字节只打一次接口）', async () => {
    const inbox = client('/api/v1/inbox')
    const buf = new ArrayBuffer(8)
    inbox.get.mockReturnValueOnce(bytesResponse(buf))
    const p1 = fetchAttachmentBytes(5, 0)
    const p2 = fetchAttachmentBytes(5, 0)
    expect(p1).toBe(p2)
    await expect(p1).resolves.toBe(buf)
    expect(inbox.get).toHaveBeenCalledTimes(1)
    expect(inbox.get).toHaveBeenCalledWith('messages/5/attachments/0/preview')
    // 不同附件不共享缓存
    inbox.get.mockReturnValueOnce(bytesResponse(buf))
    await fetchAttachmentBytes(5, 1)
    expect(inbox.get).toHaveBeenCalledTimes(2)
  })

  it('失败后清掉缓存条目：下次同 key 重新发请求（不把 rejection 缓存住）', async () => {
    const inbox = client('/api/v1/inbox')
    inbox.get.mockReturnValueOnce(Promise.reject(new Error('网络中断')))
    await expect(fetchAttachmentBytes(9, 0)).rejects.toThrow('网络中断')
    const buf = new ArrayBuffer(4)
    inbox.get.mockReturnValueOnce(bytesResponse(buf))
    await expect(fetchAttachmentBytes(9, 0)).resolves.toBe(buf)
    expect(inbox.get).toHaveBeenCalledTimes(2)
  })
})

describe('PDF 拆分任务', () => {
  it('createPdfSplitJob：文件 + 模板三参数进 FormData，解析 job_id；getPdfSplitJob 按 id 查询', async () => {
    const pdfSplit = client('/api/v1/pdf-splitting')
    pdfSplit.post.mockReturnValueOnce(respond({ job_id: 'job-1' }))
    const f = new File(['pdf'], '材料.pdf')
    await expect(createPdfSplitJob(f)).resolves.toBe('job-1')
    const [path, opts] = pdfSplit.post.mock.calls[0]! as [string, { body: FormData }]
    expect(path).toBe('jobs')
    expect(opts.body.get('file')).toBeInstanceOf(File)
    expect((opts.body.get('file') as File).name).toBe('材料.pdf')
    expect(opts.body.get('template_key')).toBe('filing_materials_v1')
    expect(opts.body.get('split_mode')).toBe('content_analysis')
    expect(opts.body.get('ocr_profile')).toBe('accurate')

    const payload = { job_id: 'job-1', status: 'processing', progress: 10, segments: [], error_message: '' }
    pdfSplit.get.mockReturnValueOnce(respond(payload))
    await expect(getPdfSplitJob('job-1')).resolves.toBe(payload)
    expect(pdfSplit.get).toHaveBeenCalledWith('jobs/job-1')
  })
})
