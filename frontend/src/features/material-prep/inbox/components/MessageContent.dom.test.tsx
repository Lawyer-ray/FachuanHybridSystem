// @vitest-environment jsdom
/**
 * 收件箱消息内容里的「提交短信流程」按钮（jsdom）。
 *
 * 这条链路只对**一张网送达 + 有附件**开放：短信流程要靠附件做文书识别，
 * 没附件进去只会建一条空记录；邮箱/短信/材料包本身不走这条路。锁七件事：
 *
 * 1. 一张网 + 有附件才出现按钮（imap / 一张网无附件都不出现）；
 * 2. 点击把**这一条**消息 id 交给 submitMessageToSms；
 * 3. 新建（created=true）与命中幂等（created=false）的 toast 文案必须能分清；
 * 4. 请求在途时按钮 disabled 且转圈（防连点建双份）；
 * 5. 不传 onSubmittedToSms 也照常给按钮、照常 toast——提交结果由按钮自己说，
 *    回调只是给外层补动作（首页就地展开与抽屉这两处调用方都不传）。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  getInboxMessage: vi.fn(),
  submitMessageToSms: vi.fn(),
  fetchAttachmentThumbnail: vi.fn(
    async () => new Blob([new Uint8Array([1, 2, 3])], { type: 'image/jpeg' }),
  ),
  getContractMatch: vi.fn(),
}))

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return {
    ...actual,
    getInboxMessage: apiMock.getInboxMessage,
    submitMessageToSms: apiMock.submitMessageToSms,
    fetchAttachmentThumbnail: apiMock.fetchAttachmentThumbnail,
    getContractMatch: apiMock.getContractMatch,
  }
})

const toastMock = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
  warning: vi.fn(),
}))
vi.mock('sonner', () => ({ toast: toastMock }))

// 附件预览弹窗与查看器静态依赖 pdf.js（worker/wasm 初始化），jsdom 里必须打桩；
// 本用例不打开预览，只要模块能加载即可。
vi.mock('@/lib/pdf', () => ({
  loadPdfDocument: vi.fn(async () => ({ numPages: 1 })),
  renderPdfPage: vi.fn(async () => document.createElement('canvas')),
}))

import { MessageContent, type MessageContentRow } from './MessageContent'
import type { SubmitToSmsResult } from '../api'

const SUBJECT = '（20XX）粤0606执保XXXX号 - 送达回证'
const BODY = '请于本通知送达后三日内提交材料。'

/** 列表行投影（判定三件套 + id）。按钮只看这三个字段，不必造整条 InboxRow */
function row(over: Partial<MessageContentRow> & { id: number }): MessageContentRow {
  return {
    source_type: 'court_inbox',
    has_attachments: true,
    converted_message_id: null,
    is_read: false,
    ...over,
  }
}

/**
 * 详情投影。
 *
 * `attachments` 留空是刻意的：一条消息的 `has_attachments` 与详情里的附件元信息
 * 可以不同步（老数据就是有计数没有元信息，见 InboxRowItem.dom.test.tsx），
 * 而「提交短信流程」按钮只读列表行的 source_type / has_attachments。
 */
function detail(over: { id?: number; subject?: string; body_text?: string } = {}) {
  return {
    id: over.id ?? 1,
    subject: over.subject ?? SUBJECT,
    body_text: over.body_text ?? BODY,
    body_html: '',
    attachments: [],
  }
}

function result(over: Partial<SubmitToSmsResult> = {}): SubmitToSmsResult {
  return { sms_id: 123, created: true, attachment_count: 1, skipped: [], ...over }
}

function renderContent(
  data: MessageContentRow,
  props: { onSubmittedToSms?: () => void } = {},
) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={qc}>
      {/* imap 消息会渲染「可能关联的在办项目」面板，那里用 useNavigate */}
      <MemoryRouter>
        <MessageContent row={data} {...props} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** 等正文落地（详情查询完成），避免用 queryByRole 抢在首次渲染的空态上做断言 */
async function waitForBody() {
  await screen.findByText(BODY)
}

beforeEach(() => {
  vi.clearAllMocks()
  apiMock.getInboxMessage.mockResolvedValue(detail())
  apiMock.getContractMatch.mockResolvedValue({
    status: 'none',
    candidates: [],
    extracted_amounts: [],
    extracted_case_numbers: [],
  })
  apiMock.submitMessageToSms.mockResolvedValue(result())
})

describe('MessageContent：提交短信流程按钮的出现条件', () => {
  it('一张网 + 有附件 → 出现按钮', async () => {
    renderContent(row({ id: 1 }))
    expect(await screen.findByRole('button', { name: /提交短信流程/ })).toBeTruthy()
  })

  it('邮箱消息（imap）→ 不出现', async () => {
    renderContent(row({ id: 2, source_type: 'imap' }))
    await waitForBody()
    expect(screen.queryByRole('button', { name: /提交短信流程/ })).toBeNull()
  })

  it('一张网但没有附件 → 不出现', async () => {
    renderContent(row({ id: 3, has_attachments: false }))
    await waitForBody()
    expect(screen.queryByRole('button', { name: /提交短信流程/ })).toBeNull()
  })
})

describe('MessageContent：提交短信流程的动作', () => {
  it('点击 → 用这条消息自己的 id 调 submitMessageToSms', async () => {
    renderContent(row({ id: 7 }))
    fireEvent.click(await screen.findByRole('button', { name: /提交短信流程/ }))
    await waitFor(() => expect(apiMock.submitMessageToSms).toHaveBeenCalledWith(7))
  })

  it('created=true → toast「已提交短信处理（SMS #123）」', async () => {
    apiMock.submitMessageToSms.mockResolvedValue(result({ sms_id: 123, created: true }))
    renderContent(row({ id: 1 }))
    fireEvent.click(await screen.findByRole('button', { name: /提交短信流程/ }))

    await waitFor(() =>
      expect(toastMock.success).toHaveBeenCalledWith('已提交短信处理（SMS #123）'),
    )
    // 新建不能落到「已提交过」那一种文案上，否则用户分不清这次到底建没建
    expect(toastMock.info).not.toHaveBeenCalled()
    expect(toastMock.error).not.toHaveBeenCalled()
  })

  it('created=false（命中幂等）→ toast「该消息已提交过（SMS #123）」', async () => {
    apiMock.submitMessageToSms.mockResolvedValue(result({ sms_id: 123, created: false }))
    renderContent(row({ id: 1 }))
    fireEvent.click(await screen.findByRole('button', { name: /提交短信流程/ }))

    await waitFor(() =>
      expect(toastMock.info).toHaveBeenCalledWith('该消息已提交过（SMS #123）'),
    )
    expect(toastMock.success).not.toHaveBeenCalled()
  })

  it('请求在途：按钮 disabled 且转圈，连点不会发第二条请求', async () => {
    let release!: (value: SubmitToSmsResult) => void
    apiMock.submitMessageToSms.mockReturnValue(
      new Promise<SubmitToSmsResult>((resolve) => {
        release = resolve
      }),
    )
    renderContent(row({ id: 9 }))
    const button = (await screen.findByRole('button', {
      name: /提交短信流程/,
    })) as HTMLButtonElement

    fireEvent.click(button)

    await waitFor(() => expect(button.disabled).toBe(true))
    expect(button.querySelector('.animate-spin')).toBeTruthy()
    fireEvent.click(button)
    expect(apiMock.submitMessageToSms).toHaveBeenCalledTimes(1)

    release(result({ sms_id: 321, created: true }))
    await waitFor(() => expect(button.disabled).toBe(false))
  })

  it('不传 onSubmittedToSms → 按钮照常出现、照常 toast（回调只是附加通知）', async () => {
    // 首页就地展开与抽屉两处调用方都不传回调；按钮若挂在回调上就永远看不到
    renderContent(row({ id: 11 }))
    fireEvent.click(await screen.findByRole('button', { name: /提交短信流程/ }))
    await waitFor(() =>
      expect(toastMock.success).toHaveBeenCalledWith('已提交短信处理（SMS #123）'),
    )
  })

  it('传了 onSubmittedToSms → 成功后调用一次', async () => {
    const onSubmittedToSms = vi.fn()
    renderContent(row({ id: 12 }), { onSubmittedToSms })
    fireEvent.click(await screen.findByRole('button', { name: /提交短信流程/ }))
    await waitFor(() => expect(onSubmittedToSms).toHaveBeenCalledTimes(1))
  })
})
