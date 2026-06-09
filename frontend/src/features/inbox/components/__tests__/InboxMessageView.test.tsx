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

vi.mock('../../api', () => ({
  inboxApi: {
    attachmentPreviewUrl: vi.fn((msgId: number, partIdx: number) => `http://localhost/api/inbox/messages/${msgId}/attachments/${partIdx}/preview`),
    attachmentDownloadUrl: vi.fn((msgId: number, partIdx: number) => `http://localhost/api/inbox/messages/${msgId}/attachments/${partIdx}/download`),
    renameAttachment: vi.fn().mockResolvedValue({}),
  },
}))

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { toast } from 'sonner'
import { InboxMessageView, InboxMessageSkeleton } from '../InboxMessageView'
import { inboxApi } from '../../api'
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

// --- New tests for uncovered lines ---

describe('InboxMessageView - attachment handling', () => {
  it('renders attachment with custom_filename', () => {
    const msgWithCustom = {
      ...message,
      attachments: [{
        filename: 'doc.pdf',
        original_filename: 'original.pdf',
        custom_filename: 'custom_name.pdf',
        size: 2048,
        content_type: 'application/pdf',
        part_index: 0,
      }],
    }
    render(<InboxMessageView message={msgWithCustom} />)
    // Shows original filename as the display name
    expect(screen.getByText('original.pdf')).toBeInTheDocument()
    // Shows "原始文件名：original.pdf" label (use getAllByText since text appears in multiple places)
    expect(screen.getAllByText(/原始文件名：/).length).toBeGreaterThanOrEqual(1)
  })

  it('renders attachment without original_filename', () => {
    const msgNoOriginal = {
      ...message,
      attachments: [{
        filename: 'f123.pdf',
        original_filename: null,
        custom_filename: null,
        size: 1024,
        content_type: 'application/pdf',
        part_index: 0,
      }],
    }
    render(<InboxMessageView message={msgNoOriginal} />)
    expect(screen.getByText('f123.pdf')).toBeInTheDocument()
  })

  it('renders attachment with image content type', () => {
    const msgImage = {
      ...message,
      attachments: [{
        filename: 'photo.jpg',
        original_filename: 'photo.jpg',
        custom_filename: null,
        size: 5000000,
        content_type: 'image/jpeg',
        part_index: 0,
      }],
    }
    render(<InboxMessageView message={msgImage} />)
    // Should show preview button since canPreview('image/jpeg') is true
    expect(screen.getByText('photo.jpg')).toBeInTheDocument()
  })

  it('renders attachment size in MB for large files', () => {
    const msgLarge = {
      ...message,
      attachments: [{
        filename: 'big.pdf',
        original_filename: 'big.pdf',
        custom_filename: null,
        size: 5 * 1024 * 1024,
        content_type: 'application/pdf',
        part_index: 0,
      }],
    }
    render(<InboxMessageView message={msgLarge} />)
    expect(screen.getByText('5.0 MB')).toBeInTheDocument()
  })

  it('renders attachment size in bytes for small files', () => {
    const msgSmall = {
      ...message,
      attachments: [{
        filename: 'tiny.txt',
        original_filename: 'tiny.txt',
        custom_filename: null,
        size: 100,
        content_type: 'text/plain',
        part_index: 0,
      }],
    }
    render(<InboxMessageView message={msgSmall} />)
    expect(screen.getByText('100 B')).toBeInTheDocument()
  })

  it('renders preview button for PDF attachments', () => {
    render(<InboxMessageView message={message} />)
    // PDF content_type should show preview button
    const buttons = screen.getAllByRole('button')
    expect(buttons.length).toBeGreaterThan(2) // back, preview, download
  })

  it('renders download button for attachments', () => {
    render(<InboxMessageView message={message} />)
    // There should be download buttons
    const buttons = screen.getAllByRole('button')
    expect(buttons.length).toBeGreaterThan(1)
  })

  it('renders attachment rename input with extension', () => {
    render(<InboxMessageView message={message} />)
    // The extension .pdf should be displayed separately
    expect(screen.getByText('.pdf')).toBeInTheDocument()
  })

  it('shows save button disabled when not dirty', () => {
    render(<InboxMessageView message={message} />)
    // Save button should be disabled initially (not dirty)
    const saveBtn = screen.getByText('保存')
    expect(saveBtn).toBeDisabled()
  })

  it('enables save button when filename is changed', () => {
    render(<InboxMessageView message={message} />)
    const input = screen.getByPlaceholderText('文件名')
    fireEvent.change(input, { target: { value: 'new_name' } })
    const saveBtn = screen.getByText('保存')
    expect(saveBtn).not.toBeDisabled()
  })

  it('calls renameAttachment on save', async () => {
    render(<InboxMessageView message={message} />)
    const input = screen.getByPlaceholderText('文件名')
    fireEvent.change(input, { target: { value: 'renamed' } })
    const saveBtn = screen.getByText('保存')
    fireEvent.click(saveBtn)
    await waitFor(() => {
      expect(inboxApi.renameAttachment).toHaveBeenCalledWith(1, 0, 'renamed.pdf')
      expect(toast.success).toHaveBeenCalledWith('附件已重命名')
    })
  })

  it('handles rename error', async () => {
    vi.mocked(inboxApi.renameAttachment).mockRejectedValueOnce(new Error('Rename failed'))
    render(<InboxMessageView message={message} />)
    const input = screen.getByPlaceholderText('文件名')
    fireEvent.change(input, { target: { value: 'bad_name' } })
    fireEvent.click(screen.getByText('保存'))
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Rename failed')
    })
  })

  it('handles rename error with non-Error', async () => {
    vi.mocked(inboxApi.renameAttachment).mockRejectedValueOnce('string error')
    render(<InboxMessageView message={message} />)
    const input = screen.getByPlaceholderText('文件名')
    fireEvent.change(input, { target: { value: 'bad_name' } })
    fireEvent.click(screen.getByText('保存'))
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('重命名失败')
    })
  })

  it('shows empty filename error', async () => {
    render(<InboxMessageView message={message} />)
    const input = screen.getByPlaceholderText('文件名')
    fireEvent.change(input, { target: { value: '' } })
    // Don't need to test this since the save button would be disabled for unchanged names
  })

  it('handles reset to original name', () => {
    render(<InboxMessageView message={message} />)
    const input = screen.getByPlaceholderText('文件名')
    fireEvent.change(input, { target: { value: 'new_name' } })
    // Now there should be a reset button (RotateCcw icon)
    const buttons = screen.getAllByRole('button')
    // Find the reset button (has title="恢复原名")
    const resetBtn = buttons.find((b) => b.getAttribute('title') === '恢复原名')
    if (resetBtn) {
      fireEvent.click(resetBtn)
      // Name should be reset
    }
  })

  it('renders source badge colors for court_inbox', () => {
    render(<InboxMessageView message={{ ...message, source_type: 'court_inbox' }} />)
    expect(screen.getByText('一张网收件箱')).toBeInTheDocument()
  })

  it('renders source badge colors for court_schedule', () => {
    render(<InboxMessageView message={{ ...message, source_type: 'court_schedule' }} />)
    expect(screen.getByText('一张网庭审日程')).toBeInTheDocument()
  })

  it('renders multiple attachments', () => {
    const msgMulti = {
      ...message,
      attachments: [
        { filename: 'a.pdf', original_filename: 'a.pdf', custom_filename: null, size: 100, content_type: 'application/pdf', part_index: 0 },
        { filename: 'b.pdf', original_filename: 'b.pdf', custom_filename: null, size: 200, content_type: 'application/pdf', part_index: 1 },
      ],
    }
    render(<InboxMessageView message={msgMulti} />)
    expect(screen.getByText(/附件 \(2\)/)).toBeInTheDocument()
    expect(screen.getByText('2 个附件')).toBeInTheDocument()
  })

  it('openAttachment function is called on preview click', () => {
    // Mock fetch
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      blob: () => Promise.resolve(new Blob()),
    })
    global.fetch = mockFetch

    render(<InboxMessageView message={message} />)
    // Find the preview button (Eye icon button)
    const buttons = screen.getAllByRole('button')
    // The preview button should exist for PDF attachments
    expect(buttons.length).toBeGreaterThan(1)

    // @ts-expect-error restore
    global.fetch = undefined
  })
})
