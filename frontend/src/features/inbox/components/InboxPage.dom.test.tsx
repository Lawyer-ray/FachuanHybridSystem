// @vitest-environment jsdom
/**
 * 收件箱页 DOM 测试（jsdom）。
 *
 * 锁定三条最容易退化的用户路径：
 * 1. 列表按来源档位过滤 → 点档位后重新取数（参数对）；
 * 2. 点开一行 → 抽屉出现、并标记已读；
 * 3. 有附件的消息在抽屉里「转材料包」→ 跳材料预处理详情
 *    （这就是本次「点击后直接进入材料预处理」的闭环）。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  listInbox: vi.fn(),
  getInboxMessage: vi.fn(),
  setReadState: vi.fn(),
  convertToPack: vi.fn(),
}))

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return {
    ...actual,
    listInbox: apiMock.listInbox,
    getInboxMessage: apiMock.getInboxMessage,
    setReadState: apiMock.setReadState,
    convertToPack: apiMock.convertToPack,
  }
})
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }))

import { InboxPage } from './InboxPage'
import type { InboxRow } from '../types'

function row(over: Partial<InboxRow> & { id: number }): InboxRow {
  const now = new Date()
  return {
    source_name: '一张网收件箱',
    source_type: 'court_inbox',
    subject: '（20XX）粤0606执保XXXX号 - 告知书',
    sender: '某某人民法院',
    recipient: '',
    received_at: now.toISOString(),
    has_attachments: true,
    attachment_count: 2,
    uploaded_by_id: null,
    uploaded_by_name: '',
    created_at: now.toISOString(),
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

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/inbox']}>
        <Routes>
          <Route path="/inbox" element={node} />
          <Route path="/material-prep/:id" element={<div>材料预处理页</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  apiMock.listInbox.mockReset()
  apiMock.getInboxMessage.mockReset()
  apiMock.setReadState.mockReset().mockResolvedValue({ ok: true, message_id: 1, is_read: true, read_at: '' })
  apiMock.convertToPack.mockReset().mockResolvedValue({ ok: true, message_id: 1, pack_id: 99 })
  apiMock.getInboxMessage.mockResolvedValue({
    id: 1,
    subject: '（20XX）粤0606执保XXXX号 - 告知书',
    body_text: '请于本通知送达后三日内提交材料。',
    body_html: '',
    attachments: [
      { filename: '裁定书.pdf', original_filename: '裁定书.pdf', size: 100, content_type: 'application/pdf', part_index: 0 },
    ],
  })
})

describe('InboxPage', () => {
  it('渲染收件箱标题与消息行', async () => {
    apiMock.listInbox.mockResolvedValue([row({ id: 1 })])
    wrap(<InboxPage />)
    expect(await screen.findByRole('heading', { name: '收件箱' })).toBeTruthy()
    expect(await screen.findByText(/执保XXXX号/)).toBeTruthy()
  })

  it('切换来源档位会用对应 source_type 重新取数', async () => {
    apiMock.listInbox.mockResolvedValue([row({ id: 1 })])
    wrap(<InboxPage />)
    await screen.findByText(/执保XXXX号/)
    fireEvent.click(screen.getByRole('button', { name: '邮箱' }))
    await waitFor(() => {
      expect(apiMock.listInbox).toHaveBeenLastCalledWith(expect.objectContaining({ source: 'imap' }))
    })
  })

  it('点开一行 → 抽屉出现并标记已读', async () => {
    apiMock.listInbox.mockResolvedValue([row({ id: 1 })])
    wrap(<InboxPage />)
    fireEvent.click(await screen.findByText(/执保XXXX号/))
    expect(await screen.findByRole('dialog', { name: '消息详情' })).toBeTruthy()
    // 未读消息点开即标已读
    await waitFor(() => {
      expect(apiMock.setReadState).toHaveBeenCalledWith(1, true)
    })
  })

  it('已读的消息点开不重复发标记请求', async () => {
    apiMock.listInbox.mockResolvedValue([row({ id: 1, is_read: true })])
    wrap(<InboxPage />)
    fireEvent.click(await screen.findByText(/执保XXXX号/))
    await screen.findByRole('dialog', { name: '消息详情' })
    expect(apiMock.setReadState).not.toHaveBeenCalled()
  })

  it('抽屉内转材料包 → 跳材料预处理详情（闭环）', async () => {
    apiMock.listInbox.mockResolvedValue([row({ id: 1, has_attachments: true, converted_message_id: null })])
    wrap(<InboxPage />)
    fireEvent.click(await screen.findByText(/执保XXXX号/))
    const btn = await screen.findByRole('button', { name: /转材料包并打开/ })
    fireEvent.click(btn)
    await waitFor(() => {
      expect(apiMock.convertToPack).toHaveBeenCalledWith(1)
    })
    // 跳转后落到材料预处理路由
    expect(await screen.findByText('材料预处理页')).toBeTruthy()
  })

  it('无附件的通知类消息不给转材料包按钮，并说明原因', async () => {
    apiMock.listInbox.mockResolvedValue([row({ id: 1, has_attachments: false, attachment_count: 0 })])
    wrap(<InboxPage />)
    fireEvent.click(await screen.findByText(/执保XXXX号/))
    await screen.findByRole('dialog', { name: '消息详情' })
    expect(screen.queryByRole('button', { name: /转材料包/ })).toBeNull()
    expect(screen.getByText(/没有附件，无可拆分材料/)).toBeTruthy()
  })

  it('已转过材料包的消息直接给「打开已转的材料包」', async () => {
    apiMock.listInbox.mockResolvedValue([row({ id: 1, converted_message_id: 42 })])
    wrap(<InboxPage />)
    fireEvent.click(await screen.findByText(/执保XXXX号/))
    expect(await screen.findByRole('button', { name: /打开已转的材料包/ })).toBeTruthy()
  })

  it('材料包来源给「打开材料预处理」', async () => {
    apiMock.listInbox.mockResolvedValue([
      row({ id: 5, source_type: 'manual_upload', source_name: '前端材料预处理上传', subject: '手动上传材料' }),
    ])
    wrap(<InboxPage />)
    fireEvent.click(await screen.findByText('手动上传材料'))
    expect(await screen.findByRole('button', { name: /打开材料预处理/ })).toBeTruthy()
  })

  it('未读筛选开关会用 unreadOnly 重新取数', async () => {
    apiMock.listInbox.mockResolvedValue([row({ id: 1 })])
    wrap(<InboxPage />)
    await screen.findByText(/执保XXXX号/)
    fireEvent.click(screen.getByRole('button', { name: /未读/ }))
    await waitFor(() => {
      expect(apiMock.listInbox).toHaveBeenLastCalledWith(expect.objectContaining({ unreadOnly: true }))
    })
  })

  it('空列表按筛选条件给不同空态文案', async () => {
    apiMock.listInbox.mockResolvedValue([])
    wrap(<InboxPage />)
    expect(await screen.findByText('收件箱是空的')).toBeTruthy()
  })
})
