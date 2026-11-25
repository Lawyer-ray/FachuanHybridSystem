// @vitest-environment jsdom
/**
 * 收件箱单行的附件入口（jsdom）。
 *
 * 这一行是本次改动的核心：从「点行 → 抽屉 → 再点眼睛」变成「扫一眼就知道
 * 里面是什么」。锁四件事：
 *
 * 1. 份数胶囊是**真按钮**，点它直接预览第一份（不再进抽屉）；
 * 2. 点胶囊**不许**顺手把消息标已读（预案：行是拉伸按钮，事件会冒泡到它）；
 * 3. 多份才给展开箭头，展开后每份都能点，点第几份就预览第几份；
 * 4. 老数据（有 `has_attachments` 但没有 `attachments` 元信息）退回纯文本胶囊，
 *    不给一个点了没反应的假入口。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const pdfMock = vi.hoisted(() => ({
  loadPdfDocument: vi.fn(async () => ({ numPages: 2 })),
  renderPdfPage: vi.fn(async (_doc: unknown, _page: number, _width?: number) => document.createElement('canvas')),
}))
vi.mock('@/lib/pdf', () => pdfMock)

const bytesMock = vi.hoisted(() => ({ fetchAttachmentBytes: vi.fn(async () => new ArrayBuffer(16)) }))
vi.mock('../../api', () => ({ fetchAttachmentBytes: bytesMock.fetchAttachmentBytes }))

const thumbMock = vi.hoisted(() => ({
  fetchAttachmentThumbnail: vi.fn(async () => new Blob([new Uint8Array([1, 2, 3])], { type: 'image/jpeg' })),
}))
vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return { ...actual, fetchAttachmentThumbnail: thumbMock.fetchAttachmentThumbnail }
})
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() } }))

import { InboxRowItem } from './InboxRowItem'
import type { InboxAttachment, InboxRow } from '../types'

function att(partIndex: number, filename: string, over: Partial<InboxAttachment> = {}): InboxAttachment {
  return {
    filename,
    original_filename: filename,
    custom_filename: null,
    size: 1024,
    content_type: filename.endsWith('.pdf') ? 'application/pdf' : 'image/png',
    part_index: partIndex,
    page_count: filename.endsWith('.pdf') ? 8 : null,
    expanded_from: null,
    ...over,
  }
}

function row(over: Partial<InboxRow> & { id: number }): InboxRow {
  const now = new Date().toISOString()
  return {
    source_name: '一张网收件箱',
    source_type: 'court_inbox',
    subject: '（20XX）粤0606执保XXXX号 - 送达回证',
    sender: '某某人民法院',
    recipient: '',
    received_at: now,
    has_attachments: true,
    attachment_count: 1,
    attachments: [],
    uploaded_by_id: null,
    uploaded_by_name: '',
    created_at: now,
    status: 'todo',
    segs: 0,
    named: 0,
    pages: 0,
    mats: 0,
    types: [],
    compose: '',
    is_read: false,
    upload_link_title: '',
    upload_contract_name: '',
    ...over,
  }
}

function renderRow(data: InboxRow) {
  const onSelect = vi.fn()
  const utils = render(
    <ul>
      <InboxRowItem row={data} active={false} onSelect={onSelect} />
    </ul>,
  )
  return { ...utils, onSelect }
}

beforeEach(() => {
  vi.clearAllMocks()
  // jsdom 不实现 object URL；缩略图 hook 会用到
  if (!('createObjectURL' in URL)) {
    Object.defineProperty(URL, 'createObjectURL', { value: () => 'blob:thumb', writable: true })
    Object.defineProperty(URL, 'revokeObjectURL', { value: () => undefined, writable: true })
  }
})

describe('InboxRowItem：附件胶囊', () => {
  it('点胶囊直接打开预览，且不把消息标已读', async () => {
    const { onSelect } = renderRow(row({ id: 1, attachments: [att(0, '送达回证.pdf')] }))

    fireEvent.click(screen.getByRole('button', { name: '预览附件' }))

    expect(await screen.findByRole('dialog', { name: /附件预览：送达回证\.pdf/ })).toBeTruthy()
    // 预览 ≠ 读过了：收件箱未读数按消息算，看一眼附件就刷掉会让用户以为消息在消失
    expect(onSelect).not.toHaveBeenCalled()
  })

  it('单份附件不给展开箭头（没有「看全部」的意义）', () => {
    renderRow(row({ id: 1, attachments: [att(0, '送达回证.pdf')] }))
    expect(screen.queryByRole('button', { name: '展开附件列表' })).toBeNull()
  })

  it('多份附件：展开后逐份可见，点第几份预览第几份', async () => {
    const attachments = [att(0, '起诉状.pdf'), att(1, '证据清单.pdf'), att(2, '现场照片.png')]
    renderRow(row({ id: 1, attachment_count: 3, attachments }))

    const toggle = screen.getByRole('button', { name: '展开附件列表' })
    fireEvent.click(toggle)

    expect(screen.getByRole('button', { name: '收起附件列表' })).toBeTruthy()
    expect(screen.getByText('证据清单.pdf')).toBeTruthy()
    expect(screen.getByText('现场照片.png')).toBeTruthy()

    fireEvent.click(screen.getByTitle('预览 证据清单.pdf'))
    expect(await screen.findByRole('dialog', { name: /附件预览：证据清单\.pdf/ })).toBeTruthy()
  })

  it('点行本体打开详情（预览与详情是两个动作）', () => {
    const { onSelect } = renderRow(row({ id: 7, attachments: [att(0, '送达回证.pdf')] }))
    fireEvent.click(screen.getByRole('button', { name: /打开：/ }))
    expect(onSelect).toHaveBeenCalledTimes(1)
  })
})

describe('InboxRowItem：老数据兜底', () => {
  it('只有附件数、没有附件元信息时不可点（不给假入口）', () => {
    renderRow(row({ id: 1, has_attachments: true, attachment_count: 2, attachments: [] }))
    expect(screen.getByText('2 附件')).toBeTruthy()
    expect(screen.queryByRole('button', { name: '预览附件' })).toBeNull()
  })
})
