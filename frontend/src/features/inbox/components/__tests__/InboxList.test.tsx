vi.mock('react-router', () => ({
  useNavigate: () => vi.fn(),
}))

vi.mock('../api', () => ({
  inboxApi: {
    list: vi.fn().mockResolvedValue([]),
    get: vi.fn().mockResolvedValue({}),
    attachmentDownloadUrl: vi.fn(),
    attachmentPreviewUrl: vi.fn(),
    renameAttachment: vi.fn(),
  },
}))

vi.mock('@/hooks/use-paginated-list', () => ({
  usePaginatedList: vi.fn().mockReturnValue({
    data: { items: [], total: 0 },
    isLoading: false,
    page: 1,
    setPage: vi.fn(),
    withPageReset: (fn: Function) => fn,
  }),
}))

import { render, screen } from '@testing-library/react'
import { InboxList } from '../InboxList'

describe('InboxList', () => {
  it('renders page title', () => {
    render(<InboxList />)
    expect(screen.getByText('收件箱')).toBeInTheDocument()
  })

  it('renders page description', () => {
    render(<InboxList />)
    expect(screen.getByText('查看来自各消息平台的来信')).toBeInTheDocument()
  })

  it('renders message source management button', () => {
    render(<InboxList />)
    expect(screen.getByText('消息来源管理')).toBeInTheDocument()
  })

  it('renders sync button', () => {
    render(<InboxList />)
    expect(screen.getByText('立即同步')).toBeInTheDocument()
  })

  it('renders footer stats', () => {
    render(<InboxList />)
    expect(screen.getByText('共：')).toBeInTheDocument()
    expect(screen.getByText('0 条')).toBeInTheDocument()
  })
})
