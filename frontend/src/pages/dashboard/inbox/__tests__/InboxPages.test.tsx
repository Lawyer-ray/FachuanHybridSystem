import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import InboxListPage from '../InboxListPage'
import InboxDetailPage from '../InboxDetailPage'

// Mock inbox feature components
vi.mock('@/features/inbox', () => ({
  InboxList: () => <div data-testid="inbox-list">InboxList</div>,
}))

vi.mock('@/features/inbox/hooks/use-inbox-message', () => ({
  useInboxMessage: vi.fn(),
}))

vi.mock('@/features/inbox/components/InboxMessageView', () => ({
  InboxMessageView: ({ message }: { message: { subject: string } }) => (
    <div data-testid="inbox-message-view">Message: {message.subject}</div>
  ),
  InboxMessageSkeleton: () => <div data-testid="inbox-skeleton">Loading...</div>,
}))

import { useInboxMessage } from '@/features/inbox/hooks/use-inbox-message'
const mockUseInboxMessage = vi.mocked(useInboxMessage)

describe('InboxListPage', () => {
  it('renders InboxList component', () => {
    render(
      <MemoryRouter>
        <InboxListPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('inbox-list')).toBeInTheDocument()
  })
})

describe('InboxDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders skeleton when loading', () => {
    mockUseInboxMessage.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as ReturnType<typeof useInboxMessage>)

    render(
      <MemoryRouter initialEntries={['/admin/inbox/1']}>
        <Routes>
          <Route path="/admin/inbox/:id" element={<InboxDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByTestId('inbox-skeleton')).toBeInTheDocument()
  })

  it('renders error state when message not found', () => {
    mockUseInboxMessage.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error('Not found'),
    } as ReturnType<typeof useInboxMessage>)

    render(
      <MemoryRouter initialEntries={['/admin/inbox/1']}>
        <Routes>
          <Route path="/admin/inbox/:id" element={<InboxDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByText('消息不存在或加载失败')).toBeInTheDocument()
  })

  it('renders message when loaded', () => {
    mockUseInboxMessage.mockReturnValue({
      data: { id: '1', subject: 'Test Message' },
      isLoading: false,
      error: null,
    } as ReturnType<typeof useInboxMessage>)

    render(
      <MemoryRouter initialEntries={['/admin/inbox/1']}>
        <Routes>
          <Route path="/admin/inbox/:id" element={<InboxDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByTestId('inbox-message-view')).toBeInTheDocument()
    expect(screen.getByText('Message: Test Message')).toBeInTheDocument()
  })
})
