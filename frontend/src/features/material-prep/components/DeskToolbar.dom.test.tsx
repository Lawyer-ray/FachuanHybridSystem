// @vitest-environment jsdom
/**
 * 统一工具栏（DeskToolbar）DOM 测试。
 *
 * 它承接了原来只属于收件箱的筛选条，因此要锁住的是「槽位由阶段决定」这条契约：
 * - 收件箱槽位：来源药丸 / 未读开关 / 搜索框 / 同步按钮，且回调打到 handlers
 * - 材料包槽位：只有「列表 / 卡片」切换，不残留收件箱的控件
 * - 同步状态机的提示挂在工具栏自己身上（按钮与提示必须同一个状态机）
 *
 * 同步 hook 打桩：真实实现要发包并轮询，这里只关心「按钮按下 → run 被调用」
 * 与「state 从 syncing 回落 → 提示」，两者都用假的状态机喂。
 */
import { act, fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const syncMock = vi.hoisted(() => ({
  useSyncSources: vi.fn(),
}))
vi.mock('../inbox/hooks/use-sync-sources', () => ({ useSyncSources: syncMock.useSyncSources }))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }))

import { toast } from 'sonner'

import { DeskToolbar } from './DeskToolbar'
import { toolbarSlotsFor, type DeskToolbarHandlers } from './desk-toolbar-types'
import type { SyncResult } from '../inbox/hooks/use-sync-sources'

function syncResult(over: Partial<SyncResult> = {}): SyncResult {
  return {
    state: 'idle',
    enabled: true,
    newCount: null,
    run: vi.fn(),
    lastWindowDays: 3,
    ...over,
  }
}

function renderToolbar(stage: 'inbox' | 'todo' | 'done' | 'filed', handlers: DeskToolbarHandlers = {}) {
  return render(<DeskToolbar stage={stage} slots={toolbarSlotsFor(stage)} handlers={{ source: 'all', ...handlers }} />)
}

beforeEach(() => {
  vi.clearAllMocks()
  syncMock.useSyncSources.mockReturnValue(syncResult())
})

describe('DeskToolbar：收件箱槽位', () => {
  it('渲染来源药丸 / 未读开关 / 搜索框 / 同步按钮', () => {
    renderToolbar('inbox')
    // 五个来源档位全在（顺序即 INBOX_SOURCE_TABS）
    for (const label of ['全部', '一张网', '邮箱', '法院短信', '材料包']) {
      expect(screen.getByRole('button', { name: label })).toBeTruthy()
    }
    expect(screen.getByRole('button', { name: /未读/ })).toBeTruthy()
    expect(screen.getByLabelText('搜索收件箱')).toBeTruthy()
    // 「全部」档位的同步按钮文案是「同步全部」
    expect(screen.getByRole('button', { name: /同步全部/ })).toBeTruthy()
    // 收件箱没有「列表 / 卡片」切换（消息流只有列表形态）
    expect(screen.queryByTitle('卡片')).toBeNull()
  })

  it('点药丸回调当前档位；当前档位带 aria-pressed', () => {
    const onSourceChange = vi.fn()
    renderToolbar('inbox', { source: 'imap', onSourceChange })
    expect(screen.getByRole('button', { name: '邮箱' }).getAttribute('aria-pressed')).toBe('true')
    fireEvent.click(screen.getByRole('button', { name: '法院短信' }))
    expect(onSourceChange).toHaveBeenCalledWith('court_sms')
  })

  it('未读开关：点击翻转，并显示父级算好的未读数', () => {
    const onUnreadOnlyChange = vi.fn()
    renderToolbar('inbox', { unreadOnly: false, onUnreadOnlyChange, unreadCount: 7 })
    const btn = screen.getByRole('button', { name: /未读/ })
    expect(btn.textContent).toContain('7')
    fireEvent.click(btn)
    expect(onUnreadOnlyChange).toHaveBeenCalledWith(true)
  })

  it('未读数为 0 时不显示数字药丸', () => {
    renderToolbar('inbox', { unreadCount: 0 })
    expect(screen.getByRole('button', { name: /未读/ }).textContent?.trim()).toBe('未读')
  })

  it('搜索框受控：输入回传 onSearchChange', () => {
    const onSearchChange = vi.fn()
    renderToolbar('inbox', { search: '执行', onSearchChange })
    const input = screen.getByLabelText('搜索收件箱') as HTMLInputElement
    expect(input.value).toBe('执行')
    fireEvent.change(input, { target: { value: '执行裁定' } })
    expect(onSearchChange).toHaveBeenCalledWith('执行裁定')
  })

  it('同步按钮：按下触发当前档位的同步', () => {
    const run = vi.fn()
    syncMock.useSyncSources.mockReturnValue(syncResult({ run }))
    renderToolbar('inbox', { source: 'court_inbox' })
    fireEvent.click(screen.getByRole('button', { name: /同步一张网/ }))
    expect(run).toHaveBeenCalled()
  })

  it('同步状态机按当前档位创建（按钮作用域就是左侧选中的档位）', () => {
    renderToolbar('inbox', { source: 'imap' })
    expect(syncMock.useSyncSources).toHaveBeenCalledWith('imap')
  })
})

describe('DeskToolbar：同步完成的提示', () => {
  it('syncing → idle 且有新增条数：提示新增数量', () => {
    syncMock.useSyncSources.mockReturnValue(syncResult({ state: 'syncing' }))
    const { rerender } = renderToolbar('inbox')
    syncMock.useSyncSources.mockReturnValue(syncResult({ state: 'idle', newCount: 4 }))
    act(() => {
      rerender(<DeskToolbar stage="inbox" slots={toolbarSlotsFor('inbox')} handlers={{ source: 'all' }} />)
    })
    expect(toast.success).toHaveBeenCalledWith('同步完成，新增 4 条消息')
  })

  it('syncing → background：提示仍在后台进行', () => {
    syncMock.useSyncSources.mockReturnValue(syncResult({ state: 'syncing' }))
    const { rerender } = renderToolbar('inbox')
    syncMock.useSyncSources.mockReturnValue(syncResult({ state: 'background' }))
    act(() => {
      rerender(<DeskToolbar stage="inbox" slots={toolbarSlotsFor('inbox')} handlers={{ source: 'all' }} />)
    })
    expect(toast.info).toHaveBeenCalledWith('同步仍在后台进行，稍后刷新查看')
  })

  it('未发起过同步（idle → idle）不提示', () => {
    renderToolbar('inbox')
    expect(toast.success).not.toHaveBeenCalled()
    expect(toast.info).not.toHaveBeenCalled()
  })
})

describe('DeskToolbar：材料包槽位', () => {
  it('只有「列表 / 卡片」切换，不残留收件箱控件', () => {
    renderToolbar('todo')
    expect(screen.getByTitle('列表')).toBeTruthy()
    expect(screen.getByTitle('卡片')).toBeTruthy()
    expect(screen.queryByLabelText('搜索收件箱')).toBeNull()
    expect(screen.queryByRole('button', { name: /未读/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /一张网/ })).toBeNull()
  })

  it('点击切换回传目标形态，当前形态带 aria-pressed', () => {
    const onViewModeChange = vi.fn()
    renderToolbar('todo', { viewMode: 'grid', onViewModeChange })
    expect(screen.getByTitle('卡片').getAttribute('aria-pressed')).toBe('true')
    fireEvent.click(screen.getByTitle('列表'))
    expect(onViewModeChange).toHaveBeenCalledWith('list')
  })
})
