// @vitest-environment jsdom
/**
 * 收件箱同步按钮测试。
 *
 * 锁定本次新增的语义：**同步按钮作用于当前选中的来源档位**。
 * 三条最容易退化的路径：
 * 1. 档位 → 按钮文案随档位变化（消除「点同步到底同步什么」的歧义）；
 * 2. 档位 → 实际调用的接口/来源集合正确（一张网只同步 court_inbox）；
 * 3. 材料包档位置灰且不发请求（它没有「拉新」语义）。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  listInbox: vi.fn(),
  listSources: vi.fn(),
  syncAllSources: vi.fn(),
  syncSource: vi.fn(),
}))

vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api')>()
  return {
    ...actual,
    listInbox: apiMock.listInbox,
    listSources: apiMock.listSources,
    syncAllSources: apiMock.syncAllSources,
    syncSource: apiMock.syncSource,
  }
})

import { INBOX_SYNC_SPEC } from './constants'
import { SyncButton } from './components/SyncButton'
import { useSyncSources } from './hooks/use-sync-sources'
import type { InboxSourceFilter } from './types'

function wrap(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
}

/** 用一个最小的宿主组件把 hook 接到真实按钮上 */
function Harness({ source }: { source: InboxSourceFilter }) {
  const sync = useSyncSources(source)
  return <SyncButton source={source} sync={sync} />
}

const SOURCES = [
  { id: 1, source_type: 'imap', last_sync_at: '2026-11-04T10:00:00+08:00', last_sync_status: 'success' },
  { id: 2, source_type: 'court_inbox', last_sync_at: '2026-11-04T10:00:00+08:00', last_sync_status: 'success' },
  { id: 3, source_type: 'court_inbox', last_sync_at: '2026-11-04T10:00:00+08:00', last_sync_status: 'success' },
  { id: 4, source_type: 'court_schedule', last_sync_at: '2026-11-04T10:00:00+08:00', last_sync_status: 'success' },
]

beforeEach(() => {
  vi.clearAllMocks()
  apiMock.listSources.mockResolvedValue(SOURCES)
  apiMock.listInbox.mockResolvedValue([])
  apiMock.syncAllSources.mockResolvedValue({ success: true, message: 'ok' })
  apiMock.syncSource.mockResolvedValue({ success: true, message: 'ok' })
})

describe('同步按钮文案跟随档位', () => {
  it.each([
    ['all', '同步全部'],
    ['court_inbox', '同步一张网'],
    ['imap', '同步邮箱'],
    ['court_sms', '同步短信'],
  ] as const)('%s 档位显示「%s」', (source, expected) => {
    render(wrap(<Harness source={source} />))
    expect(screen.getByRole('button', { name: new RegExp(expected) })).toBeTruthy()
  })

  it('材料包档位置灰且提示原因', () => {
    render(wrap(<Harness source="manual_upload,client_upload" />))
    const btn = screen.getByRole('button', { name: /材料包无需同步/ })
    expect((btn as HTMLButtonElement).disabled).toBe(true)
  })
})

describe('同步按钮的调用目标', () => {
  it('一张网档位只同步 court_inbox 来源', async () => {
    render(wrap(<Harness source="court_inbox" />))
    fireEvent.click(screen.getByRole('button', { name: /同步一张网/ }))

    await waitFor(() => {
      expect(apiMock.syncSource).toHaveBeenCalledTimes(2)
    })
    const ids = apiMock.syncSource.mock.calls.map((c) => c[0]).sort()
    expect(ids).toEqual([2, 3])
    // 不应调用 sync-all（那是「全部」档位的事）
    expect(apiMock.syncAllSources).not.toHaveBeenCalled()
  })

  it('邮箱档位只同步 imap 来源', async () => {
    render(wrap(<Harness source="imap" />))
    fireEvent.click(screen.getByRole('button', { name: /同步邮箱/ }))

    await waitFor(() => {
      expect(apiMock.syncSource).toHaveBeenCalledTimes(1)
    })
    expect(apiMock.syncSource.mock.calls[0]?.[0]).toBe(1)
  })

  it('全部档位走 sync-all 一次，不逐个调用', async () => {
    render(wrap(<Harness source="all" />))
    fireEvent.click(screen.getByRole('button', { name: /同步全部/ }))

    await waitFor(() => {
      expect(apiMock.syncAllSources).toHaveBeenCalledTimes(1)
    })
    expect(apiMock.syncSource).not.toHaveBeenCalled()
  })

  it('材料包档位点击不发任何同步请求', () => {
    render(wrap(<Harness source="manual_upload,client_upload" />))
    fireEvent.click(screen.getByRole('button', { name: /材料包无需同步/ }))

    expect(apiMock.syncAllSources).not.toHaveBeenCalled()
    expect(apiMock.syncSource).not.toHaveBeenCalled()
  })
})

describe('档位 → 同步目标映射表', () => {
  it('日历（court_schedule）不出现在任何具体档位的同步目标里', () => {
    for (const spec of Object.values(INBOX_SYNC_SPEC)) {
      if (Array.isArray(spec.target)) {
        expect(spec.target).not.toContain('court_schedule')
      }
    }
  })

  it('材料包档位没有同步目标且给了置灰原因', () => {
    const spec = INBOX_SYNC_SPEC['manual_upload,client_upload']
    expect(spec.target).toBeNull()
    expect(spec.disabledReason).toBeTruthy()
  })

  it('全部档位使用 sync-all 通道', () => {
    expect(INBOX_SYNC_SPEC.all.target).toBe('all')
  })
})
