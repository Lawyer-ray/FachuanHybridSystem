/**
 * document-parsing api 状态映射单测（node 环境即可）。
 *
 * mock 只打 HTTP 客户端工厂（@/lib/api 的 createApiClient），
 * 断言 parseDocument / getParseTaskTask 对后端响应的归一化：
 * 异步 task_id vs 同步结果双路径、缺省兜底、表单字段映射。
 */
import { describe, expect, it, vi } from 'vitest'

const { postMock, getMock } = vi.hoisted(() => ({
  postMock: vi.fn(),
  getMock: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  createApiClient: () => ({ post: postMock, get: getMock }),
}))

import { DOC_PARSE_TIMEOUT_MS, getParseTaskTask, parseDocument } from './document-parsing'
import type { ParseBackend } from './document-parsing'

/** ky ResponsePromise 形状桩：同步可链 .json()，await 得 body */
function respond(body: unknown) {
  const p = Promise.resolve(body)
  return Object.assign(p, { json: () => p })
}

function submitOpts(backend: ParseBackend = 'auto') {
  return { backend, extractTables: false, extractImages: false, returnMarkdown: true }
}

describe('parseDocument 提交路径映射', () => {
  it('异步云端路径：返回 task_id 时交由调用方轮询，outcome 为 null', async () => {
    postMock.mockReturnValueOnce(respond({ task_id: 'T-001', status: 'pending' }))
    const r = await parseDocument(new File(['x'], 'a.pdf'), submitOpts())
    expect(r).toEqual({ taskId: 'T-001', status: 'pending', outcome: null })
  })

  it('task_id 数字会被字符串化（后端返回数值 id 的兼容）', async () => {
    postMock.mockReturnValueOnce(respond({ task_id: 42, status: 'running' }))
    const r = await parseDocument(new File(['x'], 'a.pdf'), submitOpts())
    expect(r.taskId).toBe('42')
    expect(r.status).toBe('running')
  })

  it('缺状态按后端初始态 pending 兜底，绝不当成完成', async () => {
    postMock.mockReturnValueOnce(respond({ task_id: 'T' }))
    const r = await parseDocument(new File(['x'], 'a.pdf'), submitOpts())
    expect(r.status).toBe('pending')
  })

  it('本地同步成功路径：markdown/text/parse_method/metadata 归一化到 outcome', async () => {
    postMock.mockResolvedValueOnce(
      respond({
        success: true,
        markdown: '# 标题',
        text: '标题',
        parse_method: 'pymupdf',
        metadata: { pages: 3 },
      }),
    )
    const r = await parseDocument(new File(['x'], 'a.pdf'), submitOpts('local'))
    expect(r.taskId).toBeNull()
    expect(r.outcome).toEqual({
      ok: true,
      markdown: '# 标题',
      text: '标题',
      method: 'pymupdf',
      error: null,
      metadata: { pages: 3 },
    })
  })

  it('同步失败路径：success=false 时透传后端 error 文案', async () => {
    postMock.mockReturnValueOnce(respond({ success: false, error: '不支持的格式' }))
    const r = await parseDocument(new File(['x'], 'a.docx'), submitOpts('local'))
    expect(r.taskId).toBeNull()
    expect(r.outcome?.ok).toBe(false)
    expect(r.outcome?.error).toBe('不支持的格式')
    expect(r.outcome?.markdown).toBe('')
  })

  it('同步失败且无 error：兜底「解析失败」', async () => {
    postMock.mockReturnValueOnce(respond({ success: false }))
    const r = await parseDocument(new File(['x'], 'a.docx'), submitOpts('local'))
    expect(r.outcome?.error).toBe('解析失败')
  })

  it('multipart 表单字段映射：backend 与三个开关按后端 upload_view 字段名提交', async () => {
    postMock.mockReturnValueOnce(respond({ task_id: 'T', status: 'pending' }))
    await parseDocument(
      new File(['x'], 'a.pdf'),
      { backend: 'mineru', extractTables: true, extractImages: false, returnMarkdown: false },
    )
    expect(postMock).toHaveBeenCalledWith(
      'parse',
      expect.objectContaining({
        body: expect.any(FormData),
        timeout: DOC_PARSE_TIMEOUT_MS,
      }),
    )
    const body = postMock.mock.calls[0]?.[1]?.body as FormData
    expect(body.get('backend')).toBe('mineru')
    expect(body.get('extract_tables')).toBe('true')
    expect(body.get('extract_images')).toBe('false')
    expect(body.get('return_markdown')).toBe('false')
    expect(body.get('file')).toBeInstanceOf(File)
  })
})

describe('getParseTaskTask 轮询状态映射', () => {
  it('success 终态：result 归一化到 outcome，taskId 以响应为准回填', async () => {
    getMock.mockResolvedValueOnce(
      respond({
        task_id: 'T-002',
        status: 'success',
        result: { success: true, text: '正文', markdown: '', parse_method: 'mineru' },
      }),
    )
    const s = await getParseTaskTask('T-002')
    expect(s.taskId).toBe('T-002')
    expect(s.status).toBe('success')
    expect(s.outcome?.ok).toBe(true)
    expect(s.outcome?.text).toBe('正文')
    expect(s.outcome?.method).toBe('mineru')
  })

  it('中间态（running）：无 result，outcome 为 null', async () => {
    getMock.mockReturnValueOnce(respond({ task_id: 'T', status: 'running' }))
    const s = await getParseTaskTask('T')
    expect(s.status).toBe('running')
    expect(s.outcome).toBeNull()
  })

  it('failure 终态：result.error 透传到 outcome.error', async () => {
    getMock.mockResolvedValueOnce(
      respond({ task_id: 'T', status: 'failure', result: { success: false, error: '云端配额不足' } }),
    )
    const s = await getParseTaskTask('T')
    expect(s.status).toBe('failure')
    expect(s.outcome?.ok).toBe(false)
    expect(s.outcome?.error).toBe('云端配额不足')
  })

  it('缺状态按 not_found 归一（调用方按宽限逻辑处理）', async () => {
    getMock.mockReturnValueOnce(respond({ task_id: 'T' }))
    const s = await getParseTaskTask('T')
    expect(s.status).toBe('not_found')
  })

  it('taskId 带特殊字符会 encodeURIComponent（后端路径安全）', async () => {
    getMock.mockReturnValueOnce(respond({ task_id: 'a/b c', status: 'running' }))
    await getParseTaskTask('a/b c')
    expect(getMock).toHaveBeenCalledWith('task/a%2Fb%20c')
  })
})
