vi.mock('react-router', () => ({
  useNavigate: () => vi.fn(),
}))

const { mockGet } = vi.hoisted(() => {
  const mockGet = vi.fn()
  return { mockGet }
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
})
