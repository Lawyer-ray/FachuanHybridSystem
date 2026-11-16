/**
 * Office 取字（/api/v1/document-parsing/parse, backend=office）单测。
 *
 * 这里守的是四个**踩过的真实坑**：
 *
 * 1. `file.type` 为空串时按扩展名回填 MIME。从 ArrayBuffer 重建 File 时
 *    （预览、拖拽、粘贴都会）`type` 是空串，直接上传会让后端 storage_service
 *    拿到 application/octet-stream，报「文件类型与扩展名不匹配」——用户看到的是
 *    「Word 打不开」，其实是 MIME 没填。
 * 2. 四种扩展名各映射到标准 MIME，未知扩展名返回空串（空串意味着「不回填、
 *    原样上传」，让后端自己判，而不是硬塞一个错的 MIME）。
 * 3. `success === false` 必须抛（后端把「解析失败」当 200 返回，不抛的话调用方
 *    会拿空字符串当解析结果，画布一片空白且无提示）。
 * 4. `markdown`/`text` 为 null 时兜底成空串并 trim：旧任务 / 纯文本 docx 只有
 *    其一，`null` 会让 `.trim()` 直接炸。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

type Recorder = {
  prefix: string
  post: ReturnType<typeof vi.fn>
}

const recorders = vi.hoisted(() => [] as Recorder[])
/** 下一次 parse 的响应体（每条用例自己设） */
const state = vi.hoisted(() => ({ response: {} as Record<string, unknown> }))

vi.mock('@/lib/api', () => ({
  UPLOAD_TIMEOUT_MS: 300_000,
  createApiClient: (opts?: { prefix?: string }) => {
    const prefix = opts?.prefix ?? '/api/v1'
    const existing = recorders.find((r) => r.prefix === prefix)
    if (existing) return existing
    const respond = () => {
      const p = Promise.resolve(state.response)
      return Object.assign(p, { json: () => p })
    }
    const recorder: Recorder = { prefix, post: vi.fn(() => respond()) }
    recorders.push(recorder)
    return recorder
  },
}))

import { parseOfficeFile } from './office'

function parsing(): Recorder {
  const r = recorders.find((x) => x.prefix === '/api/v1/document-parsing')
  if (!r) throw new Error('document-parsing 客户端未创建')
  return r
}

function lastForm() {
  const calls = parsing().post.mock.calls
  const [path, opts] = calls[calls.length - 1] as [string, { body: FormData; timeout: number }]
  return { path, form: opts.body, timeout: opts.timeout }
}

beforeEach(() => {
  vi.clearAllMocks()
  state.response = { success: true, markdown: '正文', text: '正文' }
})

describe('parseOfficeFile：请求形状', () => {
  it('打 parse，带 backend=office 与 return_markdown=true，用上传超时', async () => {
    await parseOfficeFile(new File(['x'], 'a.docx', { type: 'application/msword' }))
    const { path, form, timeout } = lastForm()
    expect(path).toBe('parse')
    expect(form.get('backend')).toBe('office')
    expect(form.get('return_markdown')).toBe('true')
    // ky 默认 10s，大文档转换远超这个数
    expect(timeout).toBe(300_000)
  })

  it.each([
    ['a.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'],
    ['a.doc', 'application/msword'],
    ['a.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'],
    ['a.xls', 'application/vnd.ms-excel'],
  ])('%s 的 type 为空串时按扩展名回填 %s', async (name, mime) => {
    // 从 ArrayBuffer 重建 File 时 type 恒为空串（预览/拖拽/粘贴都走这条路）
    const file = new File([new Uint8Array([1, 2])], name, { type: '' })
    await parseOfficeFile(file)
    const sent = lastForm().form.get('file') as File
    // 不回填的话后端拿到 application/octet-stream → 报「文件类型与扩展名不匹配」
    expect(sent.type).toBe(mime)
    expect(sent.name).toBe(name)
  })

  it('扩展名大小写不敏感（.DOCX 也认）', async () => {
    const file = new File([new Uint8Array([1])], 'A.DOCX', { type: '' })
    await parseOfficeFile(file)
    const sent = lastForm().form.get('file') as File
    expect(sent.type).toBe('application/vnd.openxmlformats-officedocument.wordprocessingml.document')
  })

  it('未知扩展名不回填 MIME，原样上传（硬塞错 MIME 比空串更糟）', async () => {
    const file = new File([new Uint8Array([1])], 'a.txt', { type: '' })
    await parseOfficeFile(file)
    const sent = lastForm().form.get('file') as File
    expect(sent.type).toBe('')
  })

  it('已有 type 时优先用 file.type，不按扩展名覆盖', async () => {
    const file = new File([new Uint8Array([1])], 'a.weird', { type: 'application/msword' })
    await parseOfficeFile(file)
    expect((lastForm().form.get('file') as File).type).toBe('application/msword')
  })
})

describe('parseOfficeFile：响应处理', () => {
  it('success === false 时抛错，并优先用后端给的 error 文案', async () => {
    state.response = { success: false, error: '文档已加密' }
    // 不抛的话调用方会把空字符串当成解析结果，画布一片空白还查不出原因
    await expect(parseOfficeFile(new File(['x'], 'a.docx'))).rejects.toThrow('文档已加密')
  })

  it('success === false 且无 error 时用默认文案', async () => {
    state.response = { success: false }
    await expect(parseOfficeFile(new File(['x'], 'a.docx'))).rejects.toThrow('Office 文档解析失败')
  })

  it('markdown / text 为 null 时兜底成空串（旧任务只有其一，null 会让 trim 炸）', async () => {
    state.response = { success: true, markdown: null, text: null }
    await expect(parseOfficeFile(new File(['x'], 'a.docx'))).resolves.toEqual({ markdown: '', text: '' })
  })

  it('缺字段时同样兜底成空串', async () => {
    state.response = { success: true }
    await expect(parseOfficeFile(new File(['x'], 'a.docx'))).resolves.toEqual({ markdown: '', text: '' })
  })

  it('两端都 trim（后端会带尾换行，直接塞进 Markdown 渲染会多出空段）', async () => {
    state.response = { success: true, markdown: '\n# 标题\n', text: '  正文  ' }
    await expect(parseOfficeFile(new File(['x'], 'a.docx'))).resolves.toEqual({
      markdown: '# 标题',
      text: '正文',
    })
  })
})
