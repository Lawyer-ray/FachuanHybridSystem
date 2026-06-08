vi.mock('react-router', () => ({
  useNavigate: () => vi.fn(),
}))

vi.mock('@tanstack/react-query', async (importOriginal) => {
  const orig = await importOriginal<typeof import('@tanstack/react-query')>()
  return {
    ...orig,
    useQueryClient: () => ({
      invalidateQueries: vi.fn(),
    }),
  }
})

vi.mock('@/lib/token', () => ({
  getAccessToken: vi.fn().mockReturnValue('test-token'),
}))

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

import { render, screen } from '@testing-library/react'
import { InboxMessageView, InboxMessageSkeleton } from '../InboxMessageView'
import type { InboxMessageDetail } from '../../types'

const message: InboxMessageDetail = {
  id: 1,
  source_name: 'IMAP',
  source_type: 'imap',
  message_id: 'msg-1',
  subject: 'Test Subject',
  sender: 'sender@example.com',
  recipient: 'recv@example.com',
  received_at: '2024-01-01T10:00:00Z',
  has_attachments: true,
  attachment_count: 1,
  created_at: '2024-01-01T10:00:00Z',
  body_text: 'Hello world',
  body_html: '',
  attachments: [
    {
      filename: 'doc.pdf',
      original_filename: 'original.pdf',
      custom_filename: null,
      size: 1024,
      content_type: 'application/pdf',
      part_index: 0,
    },
  ],
}

describe('InboxMessageView', () => {
  it('renders back button', () => {
    render(<InboxMessageView message={message} />)
    expect(screen.getByText('返回列表')).toBeInTheDocument()
  })

  it('renders message subject', () => {
    render(<InboxMessageView message={message} />)
    expect(screen.getByText('Test Subject')).toBeInTheDocument()
  })

  it('shows (无主题) for empty subject', () => {
    render(<InboxMessageView message={{ ...message, subject: '' }} />)
    expect(screen.getByText('(无主题)')).toBeInTheDocument()
  })

  it('renders source label', () => {
    render(<InboxMessageView message={message} />)
    expect(screen.getByText('IMAP 邮箱')).toBeInTheDocument()
  })

  it('renders unknown source type as-is', () => {
    render(<InboxMessageView message={{ ...message, source_type: 'unknown' }} />)
    expect(screen.getByText('unknown')).toBeInTheDocument()
  })

  it('renders basic info section', () => {
    render(<InboxMessageView message={message} />)
    expect(screen.getByText('基本信息')).toBeInTheDocument()
    expect(screen.getByText('sender@example.com')).toBeInTheDocument()
    expect(screen.getByText('recv@example.com')).toBeInTheDocument()
    expect(screen.getByText('IMAP')).toBeInTheDocument()
  })

  it('renders body_text when body_html is empty', () => {
    render(<InboxMessageView message={message} />)
    expect(screen.getByText('Hello world')).toBeInTheDocument()
  })

  it('renders body_html as iframe when available', () => {
    const htmlMessage = { ...message, body_html: '<p>HTML content</p>', body_text: '' }
    const { container } = render(<InboxMessageView message={htmlMessage} />)
    const iframe = container.querySelector('iframe')
    expect(iframe).toBeTruthy()
    expect(iframe?.getAttribute('srcdoc')).toContain('HTML content')
  })

  it('shows no content message when both body fields empty', () => {
    render(<InboxMessageView message={{ ...message, body_text: '', body_html: '' }} />)
    expect(screen.getByText('无正文内容')).toBeInTheDocument()
  })

  it('renders attachment section with count', () => {
    render(<InboxMessageView message={message} />)
    expect(screen.getByText(/附件 \(1\)/)).toBeInTheDocument()
  })

  it('renders attachment filename', () => {
    render(<InboxMessageView message={message} />)
    expect(screen.getByText('original.pdf')).toBeInTheDocument()
  })

  it('shows no attachments message when empty', () => {
    render(<InboxMessageView message={{ ...message, attachments: [] }} />)
    expect(screen.getByText('无附件')).toBeInTheDocument()
  })

  it('renders attachment count badge', () => {
    render(<InboxMessageView message={message} />)
    expect(screen.getByText('1 个附件')).toBeInTheDocument()
  })

  it('renders attachment size', () => {
    render(<InboxMessageView message={message} />)
    expect(screen.getByText('1 KB')).toBeInTheDocument()
  })

  it('renders download button for attachments', () => {
    render(<InboxMessageView message={message} />)
    // At least the download button should exist
    const downloadButtons = screen.getAllByRole('button')
    expect(downloadButtons.length).toBeGreaterThan(1)
  })
})

describe('InboxMessageSkeleton', () => {
  it('renders without errors', () => {
    const { container } = render(<InboxMessageSkeleton />)
    expect(container.firstChild).toBeTruthy()
  })
})
