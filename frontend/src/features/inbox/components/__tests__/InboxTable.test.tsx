vi.mock('react-router', () => ({
  useNavigate: () => vi.fn(),
}))

vi.mock('@/routes/paths', async (importOriginal) => {
  const orig = await importOriginal<typeof import('@/routes/paths')>()
  return {
    ...orig,
    generatePath: {
      ...orig.generatePath,
      inboxDetail: (id: number) => `/admin/inbox/${id}`,
    },
  }
})

import { render, screen } from '@testing-library/react'
import { InboxTable } from '../InboxTable'
import type { InboxMessage } from '../../types'

const messages: InboxMessage[] = [
  {
    id: 1,
    source_name: 'IMAP',
    source_type: 'imap',
    message_id: 'msg-1',
    subject: 'Test Subject',
    sender: 'sender@example.com',
    recipient: 'recv@example.com',
    received_at: '2024-01-01T10:00:00Z',
    has_attachments: true,
    attachment_count: 2,
    created_at: '2024-01-01T10:00:00Z',
  },
  {
    id: 2,
    source_name: 'Court',
    source_type: 'court_inbox',
    message_id: 'msg-2',
    subject: '',
    sender: '',
    recipient: 'recv2@example.com',
    received_at: '2024-01-02T10:00:00Z',
    has_attachments: false,
    attachment_count: 0,
    created_at: '2024-01-02T10:00:00Z',
  },
]

describe('InboxTable', () => {
  it('renders table headers', () => {
    render(<InboxTable messages={[]} />)
    expect(screen.getByText('ID')).toBeInTheDocument()
    expect(screen.getByText('来源')).toBeInTheDocument()
    expect(screen.getByText('主题')).toBeInTheDocument()
    expect(screen.getByText('发件人')).toBeInTheDocument()
    expect(screen.getByText('收件人')).toBeInTheDocument()
    expect(screen.getByText('时间')).toBeInTheDocument()
    expect(screen.getByText('附件')).toBeInTheDocument()
  })

  it('renders message rows', () => {
    render(<InboxTable messages={messages} />)
    expect(screen.getByText('Test Subject')).toBeInTheDocument()
    expect(screen.getByText('sender@example.com')).toBeInTheDocument()
  })

  it('shows empty state when no messages', () => {
    render(<InboxTable messages={[]} />)
    expect(screen.getByText('暂无消息')).toBeInTheDocument()
  })

  it('shows loading skeleton when isLoading', () => {
    const { container } = render(<InboxTable messages={[]} isLoading />)
    // Should render skeleton rows (animated-pulse elements)
    expect(container.querySelectorAll('.animate-pulse')).toHaveLength(30) // 5 rows * 6 cells
  })

  it('shows (无主题) for empty subject', () => {
    render(<InboxTable messages={messages} />)
    expect(screen.getByText('(无主题)')).toBeInTheDocument()
  })

  it('shows attachment badge with count', () => {
    render(<InboxTable messages={messages} />)
    // The attachment count appears inside a badge with a paperclip icon
    const badges = screen.getAllByText('2')
    expect(badges.length).toBeGreaterThan(0)
  })

  it('shows dash for messages without attachments', () => {
    render(<InboxTable messages={messages} />)
    // The second message has no attachments, shows '—'
    const dashes = screen.getAllByText('—')
    expect(dashes.length).toBeGreaterThan(0)
  })
})
