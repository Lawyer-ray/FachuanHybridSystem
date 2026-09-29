import { beforeEach, describe, expect, it, vi } from 'vitest'
import { resolveMats } from './resolve'
import type { AttachmentMeta, InboxMessageDetail } from '../types'

vi.mock('../api', () => ({ fetchAttachmentBytes: vi.fn() }))
vi.mock('@/lib/pdf', () => ({ loadPdfDocument: vi.fn() }))

const { fetchAttachmentBytes } = await import('../api')
const { loadPdfDocument } = await import('@/lib/pdf')

const mockedFetch = vi.mocked(fetchAttachmentBytes)
const mockedLoad = vi.mocked(loadPdfDocument)

function detail(attachments: AttachmentMeta[]): InboxMessageDetail {
  return { id: 384, attachments } as unknown as InboxMessageDetail
}

function pdfAtt(over: Partial<AttachmentMeta> = {}): AttachmentMeta {
  return {
    filename: 'a.pdf',
    original_filename: 'a.pdf',
    custom_filename: null,
    size: 100,
    content_type: 'application/pdf',
    part_index: 0,
    ...over,
  }
}

describe('resolveMats 页数解析', () => {
  beforeEach(() => {
    mockedFetch.mockReset()
    mockedLoad.mockReset()
  })

  it('后端带 page_count：直接采用，不下载附件', async () => {
    const mats = await resolveMats(detail([pdfAtt({ part_index: 0, page_count: 92 })]))
    expect(mats).toEqual([{ partIndex: 0, n: 'a.pdf', k: 'pdf', pages: 92 }])
    expect(mockedFetch).not.toHaveBeenCalled()
  })

  it('缺失 page_count：下载 PDF 用 pdf.js 数页数兜底', async () => {
    mockedFetch.mockResolvedValue(new ArrayBuffer(8))
    mockedLoad.mockResolvedValue({ numPages: 7 } as never)
    const mats = await resolveMats(detail([pdfAtt({ part_index: 3 })]))
    expect(mats).toEqual([{ partIndex: 3, n: 'a.pdf', k: 'pdf', pages: 7 }])
    expect(mockedFetch).toHaveBeenCalledWith(384, 3)
  })

  it('下载失败：页数回落为 1，不抛错', async () => {
    mockedFetch.mockRejectedValue(new Error('network'))
    const mats = await resolveMats(detail([pdfAtt()]))
    expect(mats).toEqual([{ partIndex: 0, n: 'a.pdf', k: 'pdf', pages: 1 }])
  })

  it('非 PDF 附件页数恒为 1，且不触发下载', async () => {
    const mats = await resolveMats(
      detail([pdfAtt({ filename: 'x.jpg', original_filename: 'x.jpg', content_type: 'image/jpeg' })]),
    )
    expect(mats).toEqual([{ partIndex: 0, n: 'x.jpg', k: 'photo', pages: 1 }])
    expect(mockedFetch).not.toHaveBeenCalled()
  })

  it('多附件并行解析：每个缺页数的 PDF 各自下载一次', async () => {
    mockedFetch.mockResolvedValue(new ArrayBuffer(8))
    mockedLoad.mockResolvedValue({ numPages: 2 } as never)
    const mats = await resolveMats(detail([pdfAtt({ part_index: 0 }), pdfAtt({ filename: 'b.pdf', part_index: 1 })]))
    expect(mats.map((m) => m.pages)).toEqual([2, 2])
    expect(mockedFetch).toHaveBeenCalledTimes(2)
  })
})
