/**
 * home/api/court-sms 的文书下载路径单测（node 环境）。
 *
 * 单件文书下载只有这一处权威路径：带票据的直链（<a download> 用）与取二进制
 * （剪贴板写文件用）必须落在同一个 URL 上。此前 UI 层（tools/court-sms/copy-files.ts）
 * 自己拼了一遍 `/automation/court-sms/{id}/documents/{i}/download`，路径一改就
 * 静默降级成「只复制文件名」——故这里锁死 URL 与「不带票据、走 Authorization」
 * 两条口径（安全审计 M-2：能带头的请求不消耗一次性票据）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const clients = vi.hoisted(() => [] as Array<{ prefix: string; get: ReturnType<typeof vi.fn> }>)

vi.mock('@/lib/api', () => ({
  UPLOAD_TIMEOUT_MS: 300_000,
  createApiClient: (opts?: { prefix?: string }) => {
    const client = { prefix: opts?.prefix ?? '/api/v1', get: vi.fn() }
    clients.push(client)
    return client
  },
}))

vi.mock('./download', () => ({
  API_BASE_URL: '/api/v1',
  withAuthToken: (url: string) => Promise.resolve(`${url}?ticket=fake`),
}))

import { courtSmsDocDownloadUrl, fetchCourtSmsDocBlob } from './court-sms'

function automationClient() {
  const c = clients.find((x) => x.prefix === '/api/v1/automation')
  if (!c) throw new Error('automation 客户端未创建')
  return c
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('courtSmsDocDownloadUrl', () => {
  it('拼出单件下载的绝对路径并附下载票据', async () => {
    await expect(courtSmsDocDownloadUrl(3, 0)).resolves.toBe(
      '/api/v1/automation/court-sms/3/documents/0/download?ticket=fake',
    )
  })
})

describe('fetchCourtSmsDocBlob', () => {
  it('走 automationApi 的同一个路径取二进制（相对段不带 /api/v1 前缀）', async () => {
    const blob = new Blob(['x'], { type: 'application/pdf' })
    automationClient().get.mockReturnValue({ blob: () => Promise.resolve(blob) })

    await expect(fetchCourtSmsDocBlob(7, 2)).resolves.toBe(blob)
    expect(automationClient().get).toHaveBeenCalledWith('court-sms/7/documents/2/download')
  })

  it('取不到（非 2xx）时向上抛错，由调用方降级', async () => {
    automationClient().get.mockReturnValue({ blob: () => Promise.reject(new Error('Request failed with status code 404')) })

    await expect(fetchCourtSmsDocBlob(7, 0)).rejects.toThrow('404')
  })
})
