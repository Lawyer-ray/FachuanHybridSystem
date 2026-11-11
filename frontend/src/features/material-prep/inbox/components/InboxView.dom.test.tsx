// @vitest-environment jsdom
/**
 * 收件箱页 DOM 测试（jsdom）。
 *
 * 锁定三条最容易退化的用户路径：
 * 1. 筛选（来源档位 / 未读 / 搜索）作为**受控 props** 生效 → 按 props 取数，
 *    且深链接放开筛选时回调的是父级而不是本地 state；
 * 2. 点开一行 → 抽屉出现、并标记已读；
 * 3. 有附件的消息在抽屉里「转材料包」→ 跳材料预处理详情
 *    （这就是本次「点击后直接进入材料预处理」的闭环）。
 *
 * 筛选控件本身已上提到 DeskPage 的统一工具栏，不在本视图 DOM 里；
 * 因此这里只喂受控值、断言取数参数与空态，不再点档位药丸。
 */
import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  listInbox: vi.fn(),
  getInboxMessage: vi.fn(),
  setReadState: vi.fn(),
  convertToPack: vi.fn(),
  listSources: vi.fn(),
}))

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return {
    ...actual,
    listInbox: apiMock.listInbox,
    getInboxMessage: apiMock.getInboxMessage,
    setReadState: apiMock.setReadState,
    convertToPack: apiMock.convertToPack,
    listSources: apiMock.listSources,
  }
})
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }))

// 下载票据与下载触发都是跨模块副作用（换票要发请求、downloadUrl 要操作 DOM），
// 在这里打桩以断言「确实换票了」——这正是曾经漏掉、导致 401 的那一步。
const dlMock = vi.hoisted(() => ({
  withDownloadTicket: vi.fn(async (u: string) => `${u}?ticket=TICKET123`),
  downloadUrl: vi.fn(),
}))
vi.mock('@/lib/download-ticket', () => ({ withDownloadTicket: dlMock.withDownloadTicket }))
vi.mock('@/lib/download', () => ({ downloadUrl: dlMock.downloadUrl }))

import { InboxView } from './InboxView'
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

/**
 * 受控外壳：筛选状态由父级（DeskPage 的统一工具栏）持有，本视图只收值与回调。
 * 这里用一个真实的 state 容器模拟父级，让「点筛选 → 回调 → 重新取数」这条链路
 * 能被端到端验证；单独断言回调被调用的用例见下面 `filter calls` describe。
 */
type InboxProps = Parameters<typeof InboxView>[0]

/**
 * 父级侧的最小工具栏替身：统一工具栏本尊在 DeskPage 里、不归本视图，
 * 这里只放几个按钮，把「改父级状态 → 传新 props 给 InboxView」的链路跑通。
 */
function ParentToolbar({
  onSource,
  onUnread,
  onSearch,
}: {
  onSource: () => void
  onUnread: () => void
  onSearch: () => void
}) {
  return (
    <>
      <button type="button" onClick={onSource}>
        切到邮箱
      </button>
      <button type="button" onClick={onUnread}>
        打开未读
      </button>
      <button type="button" onClick={onSearch}>
        搜索执行
      </button>
    </>
  )
}

function ControlledHarness({
  initial,
  onSourceChange,
  onSearchChange,
  onUnreadOnlyChange,
}: {
  initial?: Partial<InboxProps>
  onSourceChange?: (s: InboxProps['source']) => void
  onSearchChange?: (v: string) => void
  onUnreadOnlyChange?: (v: boolean) => void
}) {
  const [source, setSource] = useState<InboxProps['source']>(initial?.source ?? 'all')
  const [search, setSearch] = useState(initial?.search ?? '')
  const [unreadOnly, setUnreadOnly] = useState(initial?.unreadOnly ?? false)
  return (
    <>
      <ParentToolbar
        onSource={() => setSource('imap')}
        onUnread={() => setUnreadOnly(true)}
        onSearch={() => setSearch('执行')}
      />
      <InboxView
        source={source}
        onSourceChange={(s) => {
          onSourceChange?.(s)
          setSource(s)
        }}
        search={search}
        onSearchChange={(v) => {
          onSearchChange?.(v)
          setSearch(v)
        }}
        unreadOnly={unreadOnly}
        onUnreadOnlyChange={(v) => {
          onUnreadOnlyChange?.(v)
          setUnreadOnly(v)
        }}
      />
    </>
  )
}

/** 包一层路由 + query 外壳。`element` 换成任意受控节点（直连 props 的用例用它）。 */
function wrapWith(harness: Partial<Parameters<typeof ControlledHarness>[0]> = {}, element?: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/inbox']}>
        <Routes>
          <Route path="/inbox" element={element ?? <ControlledHarness {...harness} />} />
          <Route path="/material-prep/:id" element={<div>材料预处理页</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function wrap(
  harness: Partial<Parameters<typeof ControlledHarness>[0]> = {},
  initialEntries: string[] = ['/inbox'],
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={initialEntries}>
        <Routes>
          <Route path="/inbox" element={<ControlledHarness {...harness} />} />
          <Route path="/material-prep/:id" element={<div>材料预处理页</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  dlMock.withDownloadTicket.mockClear()
  dlMock.withDownloadTicket.mockImplementation(async (u: string) => `${u}?ticket=TICKET123`)
  dlMock.downloadUrl.mockClear()
  apiMock.listInbox.mockReset()
  apiMock.getInboxMessage.mockReset()
  apiMock.setReadState.mockReset().mockResolvedValue({ ok: true, message_id: 1, is_read: true, read_at: '' })
  apiMock.convertToPack.mockReset().mockResolvedValue({ ok: true, message_id: 1, pack_id: 99 })
  apiMock.listSources.mockReset().mockResolvedValue([])
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

describe('InboxView', () => {
  it('渲染消息行（页面标题与阶段页签由 DeskPage 提供，不归本视图）', async () => {
    apiMock.listInbox.mockResolvedValue([row({ id: 1 })])
    wrap()
    expect(await screen.findByText(/执保XXXX号/)).toBeTruthy()
    // 筛选控件已上提到统一工具栏，本视图不再自带二级筛选条
    expect(screen.queryByRole('button', { name: '邮箱' })).toBeNull()
    expect(screen.queryByPlaceholderText('搜主题 / 发件人')).toBeNull()
  })

  it('source 受控 prop 变化会用对应 source_type 重新取数', async () => {
    apiMock.listInbox.mockResolvedValue([row({ id: 1 })])
    wrapWith({ initial: { source: 'all' } })
    await screen.findByText(/执保XXXX号/)
    expect(apiMock.listInbox).toHaveBeenLastCalledWith(expect.objectContaining({ source: 'all' }))

    // 换一次受控值 = 工具栏里换了档位
    fireEvent.click(screen.getByRole('button', { name: '切到邮箱' }))
    await waitFor(() => {
      expect(apiMock.listInbox).toHaveBeenLastCalledWith(expect.objectContaining({ source: 'imap' }))
    })
  })

  it('点开一行 → 抽屉出现并标记已读', async () => {
    apiMock.listInbox.mockResolvedValue([row({ id: 1 })])
    wrap()
    fireEvent.click(await screen.findByText(/执保XXXX号/))
    expect(await screen.findByRole('dialog', { name: '消息详情' })).toBeTruthy()
    // 未读消息点开即标已读
    await waitFor(() => {
      expect(apiMock.setReadState).toHaveBeenCalledWith(1, true)
    })
  })

  it('已读的消息点开不重复发标记请求', async () => {
    apiMock.listInbox.mockResolvedValue([row({ id: 1, is_read: true })])
    wrap()
    fireEvent.click(await screen.findByText(/执保XXXX号/))
    await screen.findByRole('dialog', { name: '消息详情' })
    expect(apiMock.setReadState).not.toHaveBeenCalled()
  })

  it('抽屉内转材料包 → 跳材料预处理详情（闭环）', async () => {
    apiMock.listInbox.mockResolvedValue([row({ id: 1, has_attachments: true, converted_message_id: null })])
    wrap()
    fireEvent.click(await screen.findByText(/执保XXXX号/))
    const btn = await screen.findByRole('button', { name: /转材料包并打开/ })
    fireEvent.click(btn)
    await waitFor(() => {
      expect(apiMock.convertToPack).toHaveBeenCalledWith(1)
    })
    // 跳转后落到材料预处理路由
    expect(await screen.findByText('材料预处理页')).toBeTruthy()
  })

  // 回归：附件预览/下载曾用裸 <a href> 打开后端端点，浏览器带不上 JWT、
  // 后端又刻意不收 ?token=，导致任何账号都是 401（「用自己的账号下载自己的
  // 一张网材料也失败」，与权限无关）。必须经一次性下载票据换 ?ticket=。
  it('预览附件：先换下载票据，再带 ticket 开新标签', async () => {
    const openSpy = vi.fn()
    vi.stubGlobal('open', openSpy)
    apiMock.listInbox.mockResolvedValue([row({ id: 1, has_attachments: true })])
    wrap()
    fireEvent.click(await screen.findByText(/执保XXXX号/))
    fireEvent.click(await screen.findByRole('button', { name: '预览附件' }))

    await waitFor(() => expect(dlMock.withDownloadTicket).toHaveBeenCalled())
    // 换票的入参必须是 preview 端点，且不含任何 JWT
    const arg = dlMock.withDownloadTicket.mock.calls[0]?.[0] as string
    expect(arg).toBe('/api/v1/inbox/messages/1/attachments/0/preview')
    await waitFor(() => expect(openSpy).toHaveBeenCalled())
    expect(String(openSpy.mock.calls[0]?.[0])).toContain('ticket=TICKET123')
    vi.unstubAllGlobals()
  })

  it('下载附件：先换下载票据，再以带 ticket 的 URL 触发下载', async () => {
    apiMock.listInbox.mockResolvedValue([row({ id: 1, has_attachments: true })])
    wrap()
    fireEvent.click(await screen.findByText(/执保XXXX号/))
    fireEvent.click(await screen.findByRole('button', { name: '下载附件' }))

    await waitFor(() => expect(dlMock.withDownloadTicket).toHaveBeenCalled())
    expect(dlMock.withDownloadTicket.mock.calls[0]?.[0]).toBe(
      '/api/v1/inbox/messages/1/attachments/0/download',
    )
    await waitFor(() => expect(dlMock.downloadUrl).toHaveBeenCalled())
    expect(String(dlMock.downloadUrl.mock.calls[0]?.[0])).toContain('ticket=TICKET123')
  })

  it('附件按钮不再渲染裸 <a href> 指向受保护端点（否则必然 401）', async () => {
    apiMock.listInbox.mockResolvedValue([row({ id: 1, has_attachments: true })])
    wrap()
    fireEvent.click(await screen.findByText(/执保XXXX号/))
    await screen.findByRole('button', { name: '预览附件' })
    const links = Array.from(document.querySelectorAll('a[href*="/attachments/"]'))
    expect(links).toHaveLength(0)
  })

  it('无附件的通知类消息不给转材料包按钮，并说明原因', async () => {
    apiMock.listInbox.mockResolvedValue([row({ id: 1, has_attachments: false, attachment_count: 0 })])
    wrap()
    fireEvent.click(await screen.findByText(/执保XXXX号/))
    await screen.findByRole('dialog', { name: '消息详情' })
    expect(screen.queryByRole('button', { name: /转材料包/ })).toBeNull()
    expect(screen.getByText(/没有附件，无可拆分材料/)).toBeTruthy()
  })

  it('已转过材料包的消息直接给「打开已转的材料包」', async () => {
    apiMock.listInbox.mockResolvedValue([row({ id: 1, converted_message_id: 42 })])
    wrap()
    fireEvent.click(await screen.findByText(/执保XXXX号/))
    expect(await screen.findByRole('button', { name: /打开已转的材料包/ })).toBeTruthy()
  })

  it('材料包来源给「打开材料预处理」', async () => {
    apiMock.listInbox.mockResolvedValue([
      row({ id: 5, source_type: 'manual_upload', source_name: '前端材料预处理上传', subject: '手动上传材料' }),
    ])
    wrap()
    fireEvent.click(await screen.findByText('手动上传材料'))
    expect(await screen.findByRole('button', { name: /打开材料预处理/ })).toBeTruthy()
  })

  it('unreadOnly / search 受控 prop 变化会带进取数参数', async () => {
    apiMock.listInbox.mockResolvedValue([row({ id: 1 })])
    wrapWith()
    await screen.findByText(/执保XXXX号/)

    fireEvent.click(screen.getByRole('button', { name: '打开未读' }))
    await waitFor(() => {
      expect(apiMock.listInbox).toHaveBeenLastCalledWith(expect.objectContaining({ unreadOnly: true }))
    })

    fireEvent.click(screen.getByRole('button', { name: '搜索执行' }))
    await waitFor(() => {
      expect(apiMock.listInbox).toHaveBeenLastCalledWith(expect.objectContaining({ search: '执行' }))
    })
  })

  it('空列表按筛选条件给不同空态文案', async () => {
    apiMock.listInbox.mockResolvedValue([])
    wrap()
    expect(await screen.findByText('收件箱是空的')).toBeTruthy()
  })
})

describe('筛选状态受控：深链接与回调', () => {
  it('深链接 ?message=<id> 命中时自动展开抽屉', async () => {
    apiMock.listInbox.mockResolvedValue([row({ id: 7, subject: '到账通知 - 深链接目标' })])
    wrap({}, ['/inbox?message=7'])

    expect(await screen.findByText('到账通知 - 深链接目标')).toBeTruthy()
    expect(await screen.findByRole('dialog', { name: '消息详情' })).toBeTruthy()
  })

  it('目标消息被筛掉时通过回调放开父级筛选，而不是静默失败', async () => {
    // 第一次（带筛选的）请求返回空，放开筛选后返回目标行
    apiMock.listInbox.mockImplementation(async (params: { source?: string; unreadOnly?: boolean; search?: string }) =>
      params.source === 'court_sms' ? [] : [row({ id: 9, subject: '被筛选挡住的到账通知' })],
    )
    const onSourceChange = vi.fn()
    const onUnreadOnlyChange = vi.fn()
    const onSearchChange = vi.fn()

    wrap(
      {
        initial: { source: 'court_sms', unreadOnly: true, search: '旧关键词' },
        onSourceChange,
        onUnreadOnlyChange,
        onSearchChange,
      },
      ['/inbox?message=9'],
    )

    await waitFor(() => expect(onSourceChange).toHaveBeenCalledWith('all'))
    expect(onUnreadOnlyChange).toHaveBeenCalledWith(false)
    expect(onSearchChange).toHaveBeenCalledWith('')
    // 放开筛选后重新取数并命中目标
    expect(await screen.findByText('被筛选挡住的到账通知')).toBeTruthy()
    expect(await screen.findByRole('dialog', { name: '消息详情' })).toBeTruthy()
  })

  it('未带筛选时深链接不会误调筛选回调', async () => {
    apiMock.listInbox.mockResolvedValue([row({ id: 11, subject: '已在当前列表内' })])
    const onSourceChange = vi.fn()
    const onUnreadOnlyChange = vi.fn()
    const onSearchChange = vi.fn()

    wrap({ onSourceChange, onUnreadOnlyChange, onSearchChange }, ['/inbox?message=11'])

    expect(await screen.findByRole('dialog', { name: '消息详情' })).toBeTruthy()
    expect(onSourceChange).not.toHaveBeenCalled()
    expect(onUnreadOnlyChange).not.toHaveBeenCalled()
    expect(onSearchChange).not.toHaveBeenCalled()
  })
})

describe('空态区分「暂无消息」与「通路未接入」', () => {
  it('法院短信档位为空时给出专门的接入说明，而不是「暂无消息」', async () => {
    apiMock.listInbox.mockResolvedValue([])
    wrap({ initial: { source: 'court_sms' } })

    // 关键：不能退化成通用空态文案——那会让用户以为等一等就有数据
    expect(await screen.findByText('法院短信暂未接入收件箱')).toBeTruthy()
    expect(screen.queryByText('这一分类下暂无消息')).toBeNull()
  })

  it('法院短信空态提供前往管理的入口', async () => {
    apiMock.listInbox.mockResolvedValue([])
    wrap({ initial: { source: 'court_sms' } })

    const link = await screen.findByRole('link', { name: /前往法院短信管理/ })
    expect(link.getAttribute('href')).toContain('/admin/automation/courtsms/')
  })

  it('邮箱档位为空时仍是通用空态文案（该通路是通的）', async () => {
    apiMock.listInbox.mockResolvedValue([])
    wrap({ initial: { source: 'imap' } })

    expect(await screen.findByText('这一分类下暂无消息')).toBeTruthy()
    expect(screen.queryByText('法院短信暂未接入收件箱')).toBeNull()
  })
})
