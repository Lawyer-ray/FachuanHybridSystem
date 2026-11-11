/**
 * home/api/court-sms 单测（node 环境）。
 *
 * mock 打 ./tools（automationApi）与 ./download（withAuthToken / API_BASE_URL——票据换取为异步），
 * 断言聚焦：列表筛选参数、人工分配 / 终止任务的业务失败兜底、
 * 剪贴板复制的响应归一化与下载直链拼装。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const automationApi = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
}))

vi.mock('./tools', () => ({ automationApi }))
vi.mock('./download', () => ({
  API_BASE_URL: '/api/v1',
  // 安全审计 M-2：票据换取是异步的，这里返回拼好 ?ticket= 的 Promise
  withAuthToken: (url: string) => Promise.resolve(`${url}?ticket=fake`),
}))

import {
  abortCourtSmsTask,
  assignCourtSmsCase,
  copyCourtSmsDocsToClipboard,
  courtSmsDocDownloadUrl,
  courtSmsDownloadAllUrl,
  deleteCourtSms,
  getCourtSmsDetail,
  listCourtSms,
  retryCourtSms,
  uploadCourtSmsMaterials,
} from './court-sms'

function respond(body: unknown) {
  const p = Promise.resolve(body)
  return Object.assign(p, { json: () => p })
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('下载直链（带下载票据，安全审计 M-2）', () => {
  it('单件 / 打包下载地址按 smsId + refIndex 拼装', async () => {
    await expect(courtSmsDocDownloadUrl(3, 2)).resolves.toBe(
      '/api/v1/automation/court-sms/3/documents/2/download?ticket=fake',
    )
    await expect(courtSmsDownloadAllUrl(3)).resolves.toBe(
      '/api/v1/automation/court-sms/3/documents/download-all?ticket=fake',
    )
  })
})

describe('copyCourtSmsDocsToClipboard（响应归一化）', () => {
  it('success/copyped/reason 缺省兜底：copied→0、reason→null、success 严格 true', async () => {
    automationApi.post.mockReturnValueOnce(respond({}))
    await expect(copyCourtSmsDocsToClipboard(3, [0, 1])).resolves.toEqual({ success: false, copied: 0, reason: null })
    expect(automationApi.post).toHaveBeenCalledWith('court-sms/3/documents/copy-to-clipboard', { json: { indexes: [0, 1] } })
  })

  it('success 未声明但带 message：按业务失败抛出', async () => {
    automationApi.post.mockReturnValueOnce(respond({ message: '剪贴板不可用' }))
    await expect(copyCourtSmsDocsToClipboard(3, [])).rejects.toThrow('剪贴板不可用')
  })

  it('正常响应：字段直通', async () => {
    automationApi.post.mockReturnValueOnce(respond({ success: true, copied: 2, reason: null }))
    await expect(copyCourtSmsDocsToClipboard(3, [0, 1])).resolves.toEqual({ success: true, copied: 2, reason: null })
  })
})

describe('详情与列表', () => {
  it('getCourtSmsDetail：GET court-sms/:id 直通', async () => {
    const detail = { id: 3, status: 'completed', case: null, documents: [], download_links: [], case_numbers: [], party_names: [] }
    automationApi.get.mockReturnValueOnce(respond(detail))
    await expect(getCourtSmsDetail(3)).resolves.toBe(detail)
    expect(automationApi.get).toHaveBeenCalledWith('court-sms/3')
  })

  it('listCourtSms：group=all 不带 status_group；其余组透传；items/count 缺省兜底', async () => {
    automationApi.get.mockReturnValueOnce(respond({}))
    await expect(listCourtSms('all', 1)).resolves.toEqual({ items: [], count: 0 })
    expect(automationApi.get).toHaveBeenCalledWith('court-sms', { searchParams: { page: '1' } })

    automationApi.get.mockReturnValueOnce(respond({ items: [{ id: 1 }], count: 9 }))
    await expect(listCourtSms('needs_action', 2)).resolves.toEqual({ items: [{ id: 1 }], count: 9 })
    expect(automationApi.get).toHaveBeenLastCalledWith('court-sms', { searchParams: { status_group: 'needs_action', page: '2' } })
  })
})

describe('人工分配 / 重试 / 删除 / 终止', () => {
  it('assignCourtSmsCase：成功静默；success:false 抛 message（缺省有兜底文案）', async () => {
    automationApi.post.mockReturnValueOnce(respond({ success: true }))
    await expect(assignCourtSmsCase(3, 88)).resolves.toBeUndefined()
    expect(automationApi.post).toHaveBeenCalledWith('court-sms/3/assign-case', { json: { case_id: 88 } })

    automationApi.post.mockReturnValueOnce(respond({ success: false, message: '案件不存在' }))
    await expect(assignCourtSmsCase(3, 99)).rejects.toThrow('案件不存在')

    automationApi.post.mockReturnValueOnce(respond({ success: false }))
    await expect(assignCourtSmsCase(3, 99)).rejects.toThrow('指定案件失败')
  })

  it('retryCourtSms：POST retry；deleteCourtSms：DELETE court-sms/:id', async () => {
    automationApi.post.mockReturnValueOnce(respond({}))
    await retryCourtSms(3)
    expect(automationApi.post).toHaveBeenCalledWith('court-sms/3/retry')

    automationApi.delete.mockReturnValueOnce(respond({}))
    await deleteCourtSms(3)
    expect(automationApi.delete).toHaveBeenCalledWith('court-sms/3')
  })

  it('abortCourtSmsTask：成功静默；success:false 抛 message / 兜底文案', async () => {
    automationApi.post.mockReturnValueOnce(respond({ success: true }))
    await expect(abortCourtSmsTask(3)).resolves.toBeUndefined()

    automationApi.post.mockReturnValueOnce(respond({ success: false, message: '队列繁忙' }))
    await expect(abortCourtSmsTask(3)).rejects.toThrow('队列繁忙')

    automationApi.post.mockReturnValueOnce(respond({ success: false }))
    await expect(abortCourtSmsTask(3)).rejects.toThrow('停止任务失败')
  })
})

describe('uploadCourtSmsMaterials（客户转交材料）', () => {
  function pdf(name: string) {
    return new File(['x'], name, { type: 'application/pdf' })
  }

  it('multipart 传 files[]，带备注时一并传 content', async () => {
    automationApi.post.mockReturnValueOnce(
      respond({ success: true, data: { id: 42, materials: { saved: ['a.pdf'], skipped: [] } } }),
    )

    const out = await uploadCourtSmsMaterials([pdf('a.pdf')], '客户微信转来的判决书')

    expect(automationApi.post).toHaveBeenCalledTimes(1)
    const call = automationApi.post.mock.calls[0]!
    expect(call[0]).toBe('court-sms/upload')
    const body = (call[1] as { body: FormData }).body
    expect(body).toBeInstanceOf(FormData)
    expect(body.getAll('files')).toHaveLength(1)
    expect(body.get('content')).toBe('客户微信转来的判决书')
    expect(out).toEqual({ id: 42, materials: { saved: ['a.pdf'], skipped: [] } })
  })

  it('备注为空白时不传 content（后端按文件名生成占位正文）', async () => {
    automationApi.post.mockReturnValueOnce(
      respond({ success: true, data: { id: 43, materials: { saved: ['a.pdf'], skipped: [] } } }),
    )

    await uploadCourtSmsMaterials([pdf('a.pdf')], '   ')

    const body = (automationApi.post.mock.calls[0]![1] as { body: FormData }).body
    expect(body.get('content')).toBeNull()
  })

  it('多文件按拖入顺序追加到同一 files 字段', async () => {
    automationApi.post.mockReturnValueOnce(
      respond({ success: true, data: { id: 44, materials: { saved: ['a.pdf', 'b.pdf'], skipped: [] } } }),
    )

    await uploadCourtSmsMaterials([pdf('a.pdf'), pdf('b.pdf')])

    const body = (automationApi.post.mock.calls[0]![1] as { body: FormData }).body
    expect(body.getAll('files')).toHaveLength(2)
  })

  it('materials 缺失时返回 null（短信通道语义），saved/skipped 缺省补齐为空数组', async () => {
    automationApi.post.mockReturnValueOnce(respond({ success: true, data: { id: 45 } }))
    await expect(uploadCourtSmsMaterials([pdf('a.pdf')])).resolves.toEqual({ id: 45, materials: null })

    automationApi.post.mockReturnValueOnce(
      respond({ success: true, data: { id: 46, materials: { saved: ['x.pdf'] } } }),
    )
    await expect(uploadCourtSmsMaterials([pdf('x.pdf')])).resolves.toEqual({
      id: 46,
      materials: { saved: ['x.pdf'], skipped: [] },
    })
  })

  it('success:false 抛后端 message；缺 id 也抛（不拿 undefined 去轮询）', async () => {
    automationApi.post.mockReturnValueOnce(respond({ success: false, message: '拖入的文件都不受支持' }))
    await expect(uploadCourtSmsMaterials([pdf('a.pdf')])).rejects.toThrow('拖入的文件都不受支持')

    automationApi.post.mockReturnValueOnce(respond({ success: true, data: {} }))
    await expect(uploadCourtSmsMaterials([pdf('a.pdf')])).rejects.toThrow('材料提交失败')
  })
})
