vi.mock('../../hooks/use-message-sources', () => ({
  useMessageSources: vi.fn(),
}))

vi.mock('../../api', () => ({
  messageSourceApi: {
    sync: vi.fn().mockResolvedValue({ success: true }),
    syncAll: vi.fn().mockResolvedValue({ success: true }),
    update: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue(undefined),
  },
}))

vi.mock('../MessageSourceFormDialog', () => ({
  MessageSourceFormDialog: () => <div data-testid="form-dialog" />,
}))

vi.mock('@/components/shared/EmptyState', () => ({
  EmptyState: ({ title, onAction }: any) => (
    <div data-testid="empty-state">
      {title}
      {onAction && <button onClick={onAction} data-testid="empty-action">Action</button>}
    </div>
  ),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>()
  return {
    ...actual,
    useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  }
})

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MessageSourceList } from '../MessageSourceList'
import { useMessageSources } from '../../hooks/use-message-sources'
import { messageSourceApi } from '../../api'
import { toast } from 'sonner'

const mockUseMessageSources = vi.mocked(useMessageSources)
const mockMessageSourceApi = vi.mocked(messageSourceApi)
const mockToast = vi.mocked(toast)

const mockSource = (overrides = {}) => ({
  id: 1, display_name: 'Court Email', source_type: 'imap',
  credential_account: 'court@example.com', poll_interval_minutes: 30,
  is_enabled: true, last_sync_at: '2026-06-01T12:00:00Z', last_sync_status: 'success',
  ...overrides,
})

describe('MessageSourceList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders empty state when no sources', () => {
    mockUseMessageSources.mockReturnValue({ data: [], isLoading: false } as any)
    render(<MessageSourceList />)
    expect(screen.getByText('暂无消息来源')).toBeInTheDocument()
  })

  it('renders table with source data', () => {
    mockUseMessageSources.mockReturnValue({ data: [mockSource()], isLoading: false } as any)
    render(<MessageSourceList />)
    expect(screen.getByText('Court Email')).toBeInTheDocument()
    expect(screen.getByText('court@example.com')).toBeInTheDocument()
  })

  it('renders header buttons', () => {
    mockUseMessageSources.mockReturnValue({ data: [], isLoading: false } as any)
    render(<MessageSourceList />)
    expect(screen.getByText('全部同步')).toBeInTheDocument()
    expect(screen.getByText('添加来源')).toBeInTheDocument()
  })

  it('shows loading skeleton when loading', () => {
    mockUseMessageSources.mockReturnValue({ data: undefined, isLoading: true } as any)
    const { container } = render(<MessageSourceList />)
    expect(container.querySelectorAll('[class*="animate-pulse"]').length).toBeGreaterThan(0)
  })

  it('renders multiple sources in table', () => {
    mockUseMessageSources.mockReturnValue({
      data: [
        mockSource({ id: 1, display_name: 'Source A' }),
        mockSource({ id: 2, display_name: 'Source B', source_type: 'yzw', is_enabled: false }),
      ],
      isLoading: false,
    } as any)
    render(<MessageSourceList />)
    expect(screen.getByText('Source A')).toBeInTheDocument()
    expect(screen.getByText('Source B')).toBeInTheDocument()
  })

  it('renders sync button for each source', () => {
    mockUseMessageSources.mockReturnValue({ data: [mockSource()], isLoading: false } as any)
    render(<MessageSourceList />)
    expect(screen.getByText('同步')).toBeInTheDocument()
  })

  it('renders disabled state when source is disabled', () => {
    mockUseMessageSources.mockReturnValue({ data: [mockSource({ is_enabled: false })], isLoading: false } as any)
    render(<MessageSourceList />)
    // Disabled source shows PowerOff icon and "点击启用" title
    expect(screen.getByTitle('点击启用')).toBeInTheDocument()
  })

  it('renders enabled state when source is enabled', () => {
    mockUseMessageSources.mockReturnValue({ data: [mockSource({ is_enabled: true })], isLoading: false } as any)
    render(<MessageSourceList />)
    expect(screen.getByTitle('点击禁用')).toBeInTheDocument()
  })

  it('renders last sync status', () => {
    mockUseMessageSources.mockReturnValue({ data: [mockSource()], isLoading: false } as any)
    render(<MessageSourceList />)
    expect(screen.getByText('同步成功')).toBeInTheDocument()
  })

  it('renders failed sync status', () => {
    mockUseMessageSources.mockReturnValue({ data: [mockSource({ last_sync_status: 'failed' })], isLoading: false } as any)
    render(<MessageSourceList />)
    expect(screen.getByText('同步失败')).toBeInTheDocument()
  })

  it('renders never synced status', () => {
    mockUseMessageSources.mockReturnValue({ data: [mockSource({ last_sync_at: null, last_sync_status: null })], isLoading: false } as any)
    render(<MessageSourceList />)
    // When last_sync_at is null, shows '-'
    expect(screen.getByText('-')).toBeInTheDocument()
  })

  it('renders poll interval', () => {
    mockUseMessageSources.mockReturnValue({ data: [mockSource()], isLoading: false } as any)
    render(<MessageSourceList />)
    expect(screen.getByText('30 分钟')).toBeInTheDocument()
  })

  it('renders different source types', () => {
    mockUseMessageSources.mockReturnValue({
      data: [mockSource({ source_type: 'yzw', display_name: 'YZW Source' })],
      isLoading: false,
    } as any)
    render(<MessageSourceList />)
    expect(screen.getByText('YZW Source')).toBeInTheDocument()
  })

  it('renders source type badges', () => {
    mockUseMessageSources.mockReturnValue({ data: [mockSource()], isLoading: false } as any)
    render(<MessageSourceList />)
    expect(screen.getByText('IMAP 邮箱')).toBeInTheDocument()
  })

  it('renders delete and edit actions', () => {
    mockUseMessageSources.mockReturnValue({ data: [mockSource()], isLoading: false } as any)
    render(<MessageSourceList />)
    expect(screen.getAllByText('编辑').length).toBeGreaterThanOrEqual(1)
    // Delete button uses icon only, check for button presence
    const buttons = screen.getAllByRole('button')
    expect(buttons.length).toBeGreaterThan(5)
  })

  it('handles sync click', () => {
    mockUseMessageSources.mockReturnValue({ data: [mockSource()], isLoading: false } as any)
    render(<MessageSourceList />)
    fireEvent.click(screen.getByText('同步'))
  })

  it('handles sync all click', () => {
    mockUseMessageSources.mockReturnValue({ data: [mockSource()], isLoading: false } as any)
    render(<MessageSourceList />)
    fireEvent.click(screen.getByText('全部同步'))
  })

  it('handles add source click', () => {
    mockUseMessageSources.mockReturnValue({ data: [], isLoading: false } as any)
    render(<MessageSourceList />)
    fireEvent.click(screen.getByText('添加来源'))
    expect(screen.getByTestId('form-dialog')).toBeInTheDocument()
  })

  it('renders with no last sync time', () => {
    mockUseMessageSources.mockReturnValue({
      data: [mockSource({ last_sync_at: null })],
      isLoading: false,
    } as any)
    render(<MessageSourceList />)
    expect(screen.getByText('-')).toBeInTheDocument()
  })

  it('renders table headers', () => {
    mockUseMessageSources.mockReturnValue({ data: [mockSource()], isLoading: false } as any)
    render(<MessageSourceList />)
    expect(screen.getByText('显示名称')).toBeInTheDocument()
    expect(screen.getByText('来源类型')).toBeInTheDocument()
    expect(screen.getByText('同步状态')).toBeInTheDocument()
  })

  // === NEW TESTS: Function coverage ===

  describe('handleSync', () => {
    it('triggers sync and shows success toast', async () => {
      mockUseMessageSources.mockReturnValue({ data: [mockSource()], isLoading: false } as any)
      render(<MessageSourceList />)
      fireEvent.click(screen.getByText('同步'))

      await waitFor(() => {
        expect(mockMessageSourceApi.sync).toHaveBeenCalledWith(1)
        expect(mockToast.success).toHaveBeenCalledWith('同步任务已触发')
      })
    })

    it('shows error toast on sync failure with Error instance', async () => {
      mockMessageSourceApi.sync.mockRejectedValueOnce(new Error('Connection timeout'))
      mockUseMessageSources.mockReturnValue({ data: [mockSource()], isLoading: false } as any)
      render(<MessageSourceList />)
      fireEvent.click(screen.getByText('同步'))

      await waitFor(() => {
        expect(mockToast.error).toHaveBeenCalledWith('Connection timeout')
      })
    })

    it('shows generic error toast on sync failure with non-Error', async () => {
      mockMessageSourceApi.sync.mockRejectedValueOnce('string error')
      mockUseMessageSources.mockReturnValue({ data: [mockSource()], isLoading: false } as any)
      render(<MessageSourceList />)
      fireEvent.click(screen.getByText('同步'))

      await waitFor(() => {
        expect(mockToast.error).toHaveBeenCalledWith('同步失败，请重试')
      })
    })

    it('shows syncing state while sync is in progress', async () => {
      let resolveSync: (value: unknown) => void
      mockMessageSourceApi.sync.mockReturnValueOnce(
        new Promise((resolve) => { resolveSync = resolve }) as any,
      )
      mockUseMessageSources.mockReturnValue({ data: [mockSource()], isLoading: false } as any)
      render(<MessageSourceList />)
      fireEvent.click(screen.getByText('同步'))

      await waitFor(() => {
        expect(screen.getByText('同步中')).toBeInTheDocument()
      })

      resolveSync!({})
      await waitFor(() => {
        expect(screen.getByText('同步')).toBeInTheDocument()
      })
    })
  })

  describe('handleSyncAll', () => {
    it('triggers syncAll and shows success toast', async () => {
      mockUseMessageSources.mockReturnValue({ data: [mockSource()], isLoading: false } as any)
      render(<MessageSourceList />)
      fireEvent.click(screen.getByText('全部同步'))

      await waitFor(() => {
        expect(mockMessageSourceApi.syncAll).toHaveBeenCalled()
        expect(mockToast.success).toHaveBeenCalledWith('全部同步任务已触发')
      })
    })

    it('shows error toast on syncAll failure with Error instance', async () => {
      mockMessageSourceApi.syncAll.mockRejectedValueOnce(new Error('Server error'))
      mockUseMessageSources.mockReturnValue({ data: [mockSource()], isLoading: false } as any)
      render(<MessageSourceList />)
      fireEvent.click(screen.getByText('全部同步'))

      await waitFor(() => {
        expect(mockToast.error).toHaveBeenCalledWith('Server error')
      })
    })

    it('shows generic error toast on syncAll failure with non-Error', async () => {
      mockMessageSourceApi.syncAll.mockRejectedValueOnce('fail')
      mockUseMessageSources.mockReturnValue({ data: [mockSource()], isLoading: false } as any)
      render(<MessageSourceList />)
      fireEvent.click(screen.getByText('全部同步'))

      await waitFor(() => {
        expect(mockToast.error).toHaveBeenCalledWith('全部同步失败，请重试')
      })
    })
  })

  describe('handleToggleEnabled', () => {
    it('disables an enabled source', async () => {
      mockUseMessageSources.mockReturnValue({ data: [mockSource({ is_enabled: true })], isLoading: false } as any)
      render(<MessageSourceList />)
      fireEvent.click(screen.getByTitle('点击禁用'))

      await waitFor(() => {
        expect(mockMessageSourceApi.update).toHaveBeenCalledWith(1, { is_enabled: false })
      })
    })

    it('enables a disabled source', async () => {
      mockUseMessageSources.mockReturnValue({ data: [mockSource({ is_enabled: false })], isLoading: false } as any)
      render(<MessageSourceList />)
      fireEvent.click(screen.getByTitle('点击启用'))

      await waitFor(() => {
        expect(mockMessageSourceApi.update).toHaveBeenCalledWith(1, { is_enabled: true })
      })
    })

    it('logs error when toggle fails', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      mockMessageSourceApi.update.mockRejectedValueOnce(new Error('Toggle failed'))
      mockUseMessageSources.mockReturnValue({ data: [mockSource()], isLoading: false } as any)
      render(<MessageSourceList />)
      fireEvent.click(screen.getByTitle('点击禁用'))

      await waitFor(() => {
        expect(consoleSpy).toHaveBeenCalledWith('Toggle failed:', expect.any(Error))
      })
      consoleSpy.mockRestore()
    })
  })

  describe('handleDeleteClick and handleDeleteConfirm', () => {
    it('opens delete confirmation dialog on delete click', () => {
      mockUseMessageSources.mockReturnValue({ data: [mockSource()], isLoading: false } as any)
      render(<MessageSourceList />)

      // Find delete button (the trash icon button)
      const deleteButtons = screen.getAllByRole('button')
      // The last button in the action cell is the delete button
      const deleteBtn = deleteButtons.find((btn) =>
        btn.className.includes('text-status-red'),
      )
      expect(deleteBtn).toBeDefined()
      fireEvent.click(deleteBtn!)

      expect(screen.getByText('确认删除')).toBeInTheDocument()
    })

    it('confirms deletion and calls API', async () => {
      mockUseMessageSources.mockReturnValue({ data: [mockSource()], isLoading: false } as any)
      render(<MessageSourceList />)

      // Open delete dialog
      const deleteBtn = screen.getAllByRole('button').find((btn) =>
        btn.className.includes('text-status-red'),
      )!
      fireEvent.click(deleteBtn)

      // Click confirm
      fireEvent.click(screen.getByText('确定删除'))

      await waitFor(() => {
        expect(mockMessageSourceApi.delete).toHaveBeenCalledWith(1)
      })
    })

    it('cancels deletion', () => {
      mockUseMessageSources.mockReturnValue({ data: [mockSource()], isLoading: false } as any)
      render(<MessageSourceList />)

      const deleteBtn = screen.getAllByRole('button').find((btn) =>
        btn.className.includes('text-status-red'),
      )!
      fireEvent.click(deleteBtn)

      expect(screen.getByText('确认删除')).toBeInTheDocument()

      // Cancel
      fireEvent.click(screen.getByText('取消'))

      // Dialog should close
      expect(screen.queryByText('确认删除')).not.toBeInTheDocument()
    })

    it('handles delete API failure gracefully', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      mockMessageSourceApi.delete.mockRejectedValueOnce(new Error('Delete failed'))
      mockUseMessageSources.mockReturnValue({ data: [mockSource()], isLoading: false } as any)
      render(<MessageSourceList />)

      const deleteBtn = screen.getAllByRole('button').find((btn) =>
        btn.className.includes('text-status-red'),
      )!
      fireEvent.click(deleteBtn)
      fireEvent.click(screen.getByText('确定删除'))

      await waitFor(() => {
        expect(consoleSpy).toHaveBeenCalledWith('Delete failed:', expect.any(Error))
      })
      consoleSpy.mockRestore()
    })
  })

  describe('handleEditClick', () => {
    it('opens form dialog in edit mode with source data', () => {
      mockUseMessageSources.mockReturnValue({ data: [mockSource()], isLoading: false } as any)
      render(<MessageSourceList />)

      fireEvent.click(screen.getByText('编辑'))

      expect(screen.getByTestId('form-dialog')).toBeInTheDocument()
    })
  })

  describe('empty state action', () => {
    it('opens form dialog when empty state action is clicked', () => {
      mockUseMessageSources.mockReturnValue({ data: [], isLoading: false } as any)
      render(<MessageSourceList />)

      const actionBtn = screen.getByTestId('empty-action')
      fireEvent.click(actionBtn)

      expect(screen.getByTestId('form-dialog')).toBeInTheDocument()
    })
  })

  describe('source type rendering', () => {
    it('renders court_inbox source type', () => {
      mockUseMessageSources.mockReturnValue({
        data: [mockSource({ source_type: 'court_inbox' })],
        isLoading: false,
      } as any)
      render(<MessageSourceList />)
      expect(screen.getByText('一张网收件箱')).toBeInTheDocument()
    })

    it('renders court_schedule source type', () => {
      mockUseMessageSources.mockReturnValue({
        data: [mockSource({ source_type: 'court_schedule' })],
        isLoading: false,
      } as any)
      render(<MessageSourceList />)
      expect(screen.getByText('一张网庭审日程')).toBeInTheDocument()
    })

    it('falls back to raw source_type for unknown types', () => {
      mockUseMessageSources.mockReturnValue({
        data: [mockSource({ source_type: 'unknown_type' })],
        isLoading: false,
      } as any)
      render(<MessageSourceList />)
      expect(screen.getByText('unknown_type')).toBeInTheDocument()
    })
  })

  describe('sync status rendering', () => {
    it('renders pending sync status', () => {
      mockUseMessageSources.mockReturnValue({
        data: [mockSource({ last_sync_status: 'pending' })],
        isLoading: false,
      } as any)
      render(<MessageSourceList />)
      expect(screen.getByText('待同步')).toBeInTheDocument()
    })

    it('falls back to raw sync status for unknown statuses', () => {
      mockUseMessageSources.mockReturnValue({
        data: [mockSource({ last_sync_status: 'unknown' })],
        isLoading: false,
      } as any)
      render(<MessageSourceList />)
      expect(screen.getByText('unknown')).toBeInTheDocument()
    })
  })
})
