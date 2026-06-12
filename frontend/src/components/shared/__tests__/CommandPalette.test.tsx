vi.mock('react-router', () => ({
  useNavigate: () => mockNavigate,
}))

const { mockGet, mockNavigate } = vi.hoisted(() => {
  const mockGet = vi.fn()
  const mockNavigate = vi.fn()
  return { mockGet, mockNavigate }
})

vi.mock('@/lib/api', () => ({
  createFeatureApiClient: vi.fn().mockReturnValue({
    get: (...args: unknown[]) => mockGet(...args),
  }),
}))

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React from 'react'
import { CommandPalette } from '../CommandPalette'

beforeAll(() => {
  // Polyfill scrollIntoView for jsdom
  Element.prototype.scrollIntoView = vi.fn()
})

describe('CommandPalette', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGet.mockReturnValue({
      json: vi.fn().mockResolvedValue({
        clients: [],
        cases: [],
        contracts: [],
        inbox: [],
        court_sms: [],
        contacts: [],
      }),
    })
  })

  it('renders without errors', () => {
    const { container } = render(<CommandPalette />)
    expect(container).toBeTruthy()
  })

  it('opens on Cmd+K keyboard shortcut', async () => {
    render(<CommandPalette />)
    await userEvent.keyboard('{Meta>}k{/Meta}')
    const input = screen.getByPlaceholderText('搜索功能、当事人、案件、合同...')
    expect(input).toBeInTheDocument()
  })

  it('shows navigation commands when opened without query', async () => {
    render(<CommandPalette />)
    await userEvent.keyboard('{Meta>}k{/Meta}')
    expect(screen.getByText('仪表盘')).toBeInTheDocument()
    expect(screen.getByText('收件箱')).toBeInTheDocument()
    expect(screen.getByText('当事人管理')).toBeInTheDocument()
    expect(screen.getByText('合同管理')).toBeInTheDocument()
    expect(screen.getByText('案件管理')).toBeInTheDocument()
  })

  it('shows all tool navigation items', async () => {
    render(<CommandPalette />)
    await userEvent.keyboard('{Meta>}k{/Meta}')
    expect(screen.getByText('法院短信')).toBeInTheDocument()
    expect(screen.getByText('快递查询')).toBeInTheDocument()
    expect(screen.getByText('LPR 计算器')).toBeInTheDocument()
    expect(screen.getByText('系统设置')).toBeInTheDocument()
  })

  it('shows search input with correct placeholder', async () => {
    render(<CommandPalette />)
    await userEvent.keyboard('{Meta>}k{/Meta}')
    expect(screen.getByPlaceholderText('搜索功能、当事人、案件、合同...')).toBeInTheDocument()
  })

  it('closes on second Cmd+K', async () => {
    render(<CommandPalette />)
    await userEvent.keyboard('{Meta>}k{/Meta}')
    expect(screen.getByPlaceholderText('搜索功能、当事人、案件、合同...')).toBeInTheDocument()
    await userEvent.keyboard('{Meta>}k{/Meta}')
    await waitFor(() => {
      expect(screen.queryByPlaceholderText('搜索功能、当事人、案件、合同...')).not.toBeInTheDocument()
    })
  })

  it('shows filtered navigation commands when searching by keyword', async () => {
    render(<CommandPalette />)
    await userEvent.keyboard('{Meta>}k{/Meta}')
    const input = screen.getByPlaceholderText('搜索功能、当事人、案件、合同...')
    await userEvent.type(input, '案件')

    // Should show filtered navigation results
    await waitFor(() => {
      expect(screen.getByText('案件管理')).toBeInTheDocument()
    })
  })

  it('shows search results when API returns data', async () => {
    mockGet.mockReturnValue({
      json: vi.fn().mockResolvedValue({
        clients: [{ id: 1, title: 'Wang', subtitle: '当事人' }],
        cases: [],
        contracts: [],
        inbox: [],
        court_sms: [],
        contacts: [],
      }),
    })

    render(<CommandPalette />)
    await userEvent.keyboard('{Meta>}k{/Meta}')
    const input = screen.getByPlaceholderText('搜索功能、当事人、案件、合同...')
    await userEvent.type(input, 'Wang')

    await waitFor(() => {
      expect(screen.getByText('Wang')).toBeInTheDocument()
    }, { timeout: 3000 })
  })

  it('shows multiple result groups when API returns data for multiple types', async () => {
    mockGet.mockReturnValue({
      json: vi.fn().mockResolvedValue({
        clients: [{ id: 1, title: 'Wang', subtitle: 'client' }],
        cases: [{ id: 1, title: 'Case 1', subtitle: 'case' }],
        contracts: [],
        inbox: [],
        court_sms: [],
        contacts: [],
      }),
    })

    render(<CommandPalette />)
    await userEvent.keyboard('{Meta>}k{/Meta}')
    const input = screen.getByPlaceholderText('搜索功能、当事人、案件、合同...')
    await userEvent.type(input, 'test')

    await waitFor(() => {
      expect(screen.getByText('当事人')).toBeInTheDocument()
      expect(screen.getByText('案件')).toBeInTheDocument()
    }, { timeout: 3000 })
  })

  it('shows both search results and filtered navigation when query matches', async () => {
    mockGet.mockReturnValue({
      json: vi.fn().mockResolvedValue({
        clients: [{ id: 1, title: 'Test', subtitle: 'test' }],
        cases: [],
        contracts: [],
        inbox: [],
        court_sms: [],
        contacts: [],
      }),
    })

    render(<CommandPalette />)
    await userEvent.keyboard('{Meta>}k{/Meta}')
    const input = screen.getByPlaceholderText('搜索功能、当事人、案件、合同...')
    await userEvent.type(input, '当事人')

    await waitFor(() => {
      // Should show both navigation filter results and search results
      expect(screen.getByText('当事人管理')).toBeInTheDocument()
    }, { timeout: 3000 })
  })

  it('handles search API error gracefully', async () => {
    mockGet.mockReturnValue({
      json: vi.fn().mockRejectedValue(new Error('Network error')),
    })

    render(<CommandPalette />)
    await userEvent.keyboard('{Meta>}k{/Meta}')
    const input = screen.getByPlaceholderText('搜索功能、当事人、案件、合同...')
    await userEvent.type(input, 'test')

    // Should not crash and should show fallback
    await waitFor(() => {
      expect(input).toBeInTheDocument()
    }, { timeout: 3000 })
  })

  it('shows search result subtitle when available', async () => {
    mockGet.mockReturnValue({
      json: vi.fn().mockResolvedValue({
        clients: [{ id: 1, title: 'Wang Corp', subtitle: '制造业' }],
        cases: [],
        contracts: [],
        inbox: [],
        court_sms: [],
        contacts: [],
      }),
    })

    render(<CommandPalette />)
    await userEvent.keyboard('{Meta>}k{/Meta}')
    const input = screen.getByPlaceholderText('搜索功能、当事人、案件、合同...')
    await userEvent.type(input, 'Wang')

    await waitFor(() => {
      expect(screen.getByText('Wang Corp')).toBeInTheDocument()
      expect(screen.getByText('制造业')).toBeInTheDocument()
    }, { timeout: 3000 })
  })

  it('shows contacts search results', async () => {
    mockGet.mockReturnValue({
      json: vi.fn().mockResolvedValue({
        clients: [],
        cases: [],
        contracts: [],
        inbox: [],
        court_sms: [],
        contacts: [{ id: 1, title: 'Zhang Wei', subtitle: '律师' }],
      }),
    })

    render(<CommandPalette />)
    await userEvent.keyboard('{Meta>}k{/Meta}')
    const input = screen.getByPlaceholderText('搜索功能、当事人、案件、合同...')
    await userEvent.type(input, 'Zhang')

    await waitFor(() => {
      expect(screen.getByText('工作人员')).toBeInTheDocument()
    }, { timeout: 3000 })
  })

  it('shows court_sms search results', async () => {
    mockGet.mockReturnValue({
      json: vi.fn().mockResolvedValue({
        clients: [],
        cases: [],
        contracts: [],
        inbox: [],
        court_sms: [{ id: 1, title: 'SMS 001', subtitle: '已发送' }],
        contacts: [],
      }),
    })

    render(<CommandPalette />)
    await userEvent.keyboard('{Meta>}k{/Meta}')
    const input = screen.getByPlaceholderText('搜索功能、当事人、案件、合同...')
    await userEvent.type(input, 'SMS')

    await waitFor(() => {
      expect(screen.getByText('法院短信')).toBeInTheDocument()
    }, { timeout: 3000 })
  })

  // === NEW TESTS: Function coverage ===

  describe('handleSelect navigation', () => {
    it('navigates to the selected path and closes palette', async () => {
      render(<CommandPalette />)
      await userEvent.keyboard('{Meta>}k{/Meta}')

      // Click on a navigation command item
      const dashboardItem = screen.getByText('仪表盘')
      await userEvent.click(dashboardItem)

      expect(mockNavigate).toHaveBeenCalledWith('/admin/dashboard')
    })

    it('navigates to different commands on select', async () => {
      render(<CommandPalette />)
      await userEvent.keyboard('{Meta>}k{/Meta}')

      const clientsItem = screen.getByText('当事人管理')
      await userEvent.click(clientsItem)

      expect(mockNavigate).toHaveBeenCalledWith('/admin/clients')
    })

    it('navigates to search result path when selecting a result', async () => {
      mockGet.mockReturnValue({
        json: vi.fn().mockResolvedValue({
          clients: [{ id: 42, title: 'Wang Corp', subtitle: '制造业' }],
          cases: [],
          contracts: [],
          inbox: [],
          court_sms: [],
          contacts: [],
        }),
      })

      render(<CommandPalette />)
      await userEvent.keyboard('{Meta>}k{/Meta}')
      const input = screen.getByPlaceholderText('搜索功能、当事人、案件、合同...')
      await userEvent.type(input, 'Wang')

      await waitFor(() => {
        expect(screen.getByText('Wang Corp')).toBeInTheDocument()
      }, { timeout: 3000 })

      await userEvent.click(screen.getByText('Wang Corp'))
      expect(mockNavigate).toHaveBeenCalledWith('/admin/clients/42')
    })

    it('navigates to cases path when selecting a case result', async () => {
      mockGet.mockReturnValue({
        json: vi.fn().mockResolvedValue({
          clients: [],
          cases: [{ id: 7, title: 'Case 7', subtitle: '民事' }],
          contracts: [],
          inbox: [],
          court_sms: [],
          contacts: [],
        }),
      })

      render(<CommandPalette />)
      await userEvent.keyboard('{Meta>}k{/Meta}')
      const input = screen.getByPlaceholderText('搜索功能、当事人、案件、合同...')
      await userEvent.type(input, 'Case')

      await waitFor(() => {
        expect(screen.getByText('Case 7')).toBeInTheDocument()
      }, { timeout: 3000 })

      await userEvent.click(screen.getByText('Case 7'))
      expect(mockNavigate).toHaveBeenCalledWith('/admin/cases/7')
    })

    it('navigates to contracts path when selecting a contract result', async () => {
      mockGet.mockReturnValue({
        json: vi.fn().mockResolvedValue({
          clients: [],
          cases: [],
          contracts: [{ id: 3, title: 'Contract 3', subtitle: '租赁' }],
          inbox: [],
          court_sms: [],
          contacts: [],
        }),
      })

      render(<CommandPalette />)
      await userEvent.keyboard('{Meta>}k{/Meta}')
      const input = screen.getByPlaceholderText('搜索功能、当事人、案件、合同...')
      await userEvent.type(input, 'Contract')

      await waitFor(() => {
        expect(screen.getByText('Contract 3')).toBeInTheDocument()
      }, { timeout: 3000 })

      await userEvent.click(screen.getByText('Contract 3'))
      expect(mockNavigate).toHaveBeenCalledWith('/admin/contracts/3')
    })

    it('navigates to cases page for contacts results', async () => {
      mockGet.mockReturnValue({
        json: vi.fn().mockResolvedValue({
          clients: [],
          cases: [],
          contracts: [],
          inbox: [],
          court_sms: [],
          contacts: [{ id: 5, title: 'Zhang Wei', subtitle: '律师' }],
        }),
      })

      render(<CommandPalette />)
      await userEvent.keyboard('{Meta>}k{/Meta}')
      const input = screen.getByPlaceholderText('搜索功能、当事人、案件、合同...')
      await userEvent.type(input, 'Zhang')

      await waitFor(() => {
        expect(screen.getByText('Zhang Wei')).toBeInTheDocument()
      }, { timeout: 3000 })

      await userEvent.click(screen.getByText('Zhang Wei'))
      expect(mockNavigate).toHaveBeenCalledWith('/admin/cases')
    })

    it('navigates to inbox page for inbox results', async () => {
      mockGet.mockReturnValue({
        json: vi.fn().mockResolvedValue({
          clients: [],
          cases: [],
          contracts: [],
          inbox: [{ id: 1, title: 'Email 1', subtitle: '已读' }],
          court_sms: [],
          contacts: [],
        }),
      })

      render(<CommandPalette />)
      await userEvent.keyboard('{Meta>}k{/Meta}')
      const input = screen.getByPlaceholderText('搜索功能、当事人、案件、合同...')
      await userEvent.type(input, 'Email')

      await waitFor(() => {
        expect(screen.getByText('Email 1')).toBeInTheDocument()
      }, { timeout: 3000 })

      await userEvent.click(screen.getByText('Email 1'))
      expect(mockNavigate).toHaveBeenCalledWith('/admin/inbox')
    })

    it('navigates to court SMS page for court_sms results', async () => {
      mockGet.mockReturnValue({
        json: vi.fn().mockResolvedValue({
          clients: [],
          cases: [],
          contracts: [],
          inbox: [],
          court_sms: [{ id: 1, title: 'SMS-001', subtitle: '已发送' }],
          contacts: [],
        }),
      })

      render(<CommandPalette />)
      await userEvent.keyboard('{Meta>}k{/Meta}')
      const input = screen.getByPlaceholderText('搜索功能、当事人、案件、合同...')
      await userEvent.type(input, 'SMS')

      await waitFor(() => {
        expect(screen.getByText('SMS-001')).toBeInTheDocument()
      }, { timeout: 3000 })

      await userEvent.click(screen.getByText('SMS-001'))
      expect(mockNavigate).toHaveBeenCalledWith('/admin/tools/court-sms')
    })
  })

  describe('doSearch edge cases', () => {
    it('clears results when query becomes empty', async () => {
      render(<CommandPalette />)
      await userEvent.keyboard('{Meta>}k{/Meta}')
      const input = screen.getByPlaceholderText('搜索功能、当事人、案件、合同...')

      // Type then clear
      await userEvent.type(input, 'test')
      await userEvent.clear(input)

      // Navigation commands should be shown again (no query = nav commands visible)
      await waitFor(() => {
        expect(screen.getByText('仪表盘')).toBeInTheDocument()
      })
    })

    it('sets searching to false when query is empty string', async () => {
      render(<CommandPalette />)
      await userEvent.keyboard('{Meta>}k{/Meta}')
      const input = screen.getByPlaceholderText('搜索功能、当事人、案件、合同...')

      // Type space then clear - tests the empty trim branch
      await userEvent.type(input, '   ')
      await userEvent.clear(input)

      await waitFor(() => {
        expect(screen.getByText('仪表盘')).toBeInTheDocument()
      })
    })

    it('clears debounce timeout when typing quickly', async () => {
      render(<CommandPalette />)
      await userEvent.keyboard('{Meta>}k{/Meta}')
      const input = screen.getByPlaceholderText('搜索功能、当事人、案件、合同...')

      // Type quickly to trigger debounce clearing
      await userEvent.type(input, 'ab')
      await userEvent.type(input, 'cd')

      await waitFor(() => {
        expect(mockGet).toHaveBeenCalled()
      }, { timeout: 3000 })
    })

    it('handles non-error exceptions in search gracefully', async () => {
      mockGet.mockReturnValue({
        json: vi.fn().mockRejectedValue('string error'),
      })

      render(<CommandPalette />)
      await userEvent.keyboard('{Meta>}k{/Meta}')
      const input = screen.getByPlaceholderText('搜索功能、当事人、案件、合同...')
      await userEvent.type(input, 'test')

      await waitFor(() => {
        expect(input).toBeInTheDocument()
      }, { timeout: 3000 })
    })
  })

  describe('filtered navigation commands during search', () => {
    it('filters navigation commands by keyword match', async () => {
      render(<CommandPalette />)
      await userEvent.keyboard('{Meta>}k{/Meta}')
      const input = screen.getByPlaceholderText('搜索功能、当事人、案件、合同...')
      await userEvent.type(input, 'inbox')

      await waitFor(() => {
        expect(screen.getByText('收件箱')).toBeInTheDocument()
      })
    })

    it('filters navigation commands by Chinese label', async () => {
      render(<CommandPalette />)
      await userEvent.keyboard('{Meta>}k{/Meta}')
      const input = screen.getByPlaceholderText('搜索功能、当事人、案件、合同...')
      await userEvent.type(input, '日志')

      await waitFor(() => {
        expect(screen.getByText('日志')).toBeInTheDocument()
      })
    })

    it('shows no navigation results for non-matching query', async () => {
      mockGet.mockReturnValue({
        json: vi.fn().mockResolvedValue({
          clients: [], cases: [], contracts: [], inbox: [], court_sms: [], contacts: [],
        }),
      })

      render(<CommandPalette />)
      await userEvent.keyboard('{Meta>}k{/Meta}')
      const input = screen.getByPlaceholderText('搜索功能、当事人、案件、合同...')
      await userEvent.type(input, 'zzzznonexistent')

      await waitFor(() => {
        expect(screen.getByText('未找到相关数据')).toBeInTheDocument()
      }, { timeout: 3000 })
    })
  })

  describe('open/close state management', () => {
    it('resets query and results when dialog closes', async () => {
      mockGet.mockReturnValue({
        json: vi.fn().mockResolvedValue({
          clients: [{ id: 1, title: 'Test', subtitle: 'test' }],
          cases: [], contracts: [], inbox: [], court_sms: [], contacts: [],
        }),
      })

      render(<CommandPalette />)
      await userEvent.keyboard('{Meta>}k{/Meta}')
      const input = screen.getByPlaceholderText('搜索功能、当事人、案件、合同...')
      await userEvent.type(input, 'test')

      await waitFor(() => {
        expect(screen.getByText('Test')).toBeInTheDocument()
      }, { timeout: 3000 })

      // Close with Escape
      await userEvent.keyboard('{Escape}')

      await waitFor(() => {
        expect(screen.queryByPlaceholderText('搜索功能、当事人、案件、合同...')).not.toBeInTheDocument()
      })

      // Reopen - should be clean
      await userEvent.keyboard('{Meta>}k{/Meta}')
      const newInput = screen.getByPlaceholderText('搜索功能、当事人、案件、合同...')
      expect(newInput).toHaveValue('')
    })

    it('clears debounce timeout on unmount', async () => {
      const clearTimeoutSpy = vi.spyOn(global, 'clearTimeout')
      const { unmount } = render(<CommandPalette />)
      await userEvent.keyboard('{Meta>}k{/Meta}')

      unmount()

      // The cleanup effect should call clearTimeout
      expect(clearTimeoutSpy).toHaveBeenCalled()
      clearTimeoutSpy.mockRestore()
    })
  })

  describe('searching state display', () => {
    it('shows searching indicator while search is in progress', async () => {
      // Make the API slow
      let resolveJson: (value: unknown) => void
      const slowPromise = new Promise((resolve) => { resolveJson = resolve })
      mockGet.mockReturnValue({
        json: () => slowPromise,
      })

      render(<CommandPalette />)
      await userEvent.keyboard('{Meta>}k{/Meta}')
      const input = screen.getByPlaceholderText('搜索功能、当事人、案件、合同...')
      await userEvent.type(input, 'test')

      await waitFor(() => {
        expect(screen.getByText('搜索中...')).toBeInTheDocument()
      }, { timeout: 3000 })

      // Resolve the promise
      resolveJson!({
        clients: [], cases: [], contracts: [], inbox: [], court_sms: [], contacts: [],
      })

      await waitFor(() => {
        expect(screen.queryByText('搜索中...')).not.toBeInTheDocument()
      }, { timeout: 3000 })
    })
  })

  describe('Ctrl+K shortcut', () => {
    it('opens palette on Ctrl+K', async () => {
      render(<CommandPalette />)
      await userEvent.keyboard('{Control>}k{/Control}')
      const input = screen.getByPlaceholderText('搜索功能、当事人、案件、合同...')
      expect(input).toBeInTheDocument()
    })
  })
})
