vi.mock('@/lib/api', () => ({
  resolveMediaUrl: vi.fn((url: string | null) => url),
  API_BASE_URL: 'http://localhost:8002/api/v1',
  BACKEND_URL: 'http://localhost:8002',
  createFeatureApiClient: vi.fn(),
}))

vi.mock('@/components/ui/card', () => ({
  Card: ({ children, ...p }: Record<string, unknown>) => <div {...p}>{children}</div>,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...p }: Record<string, unknown>) => <button {...p}>{children}</button>,
}))

vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  DialogContent: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  DialogHeader: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  DialogTitle: ({ children }: Record<string, unknown>) => <h2>{children}</h2>,
}))

vi.mock('lucide-react', () => {
  const Icon = (p: Record<string, unknown>) => <svg data-testid="icon" {...p} />
  return {
    FileText: Icon, Image: Icon, Eye: Icon, Calendar: Icon,
  }
})

vi.mock('date-fns', () => ({
  format: vi.fn(() => '2024年01月01日 12:00'),
}))

vi.mock('date-fns/locale', () => ({
  zhCN: {},
}))

import { render, screen } from '@testing-library/react'
import { IdentityDocList } from '../IdentityDocList'
import type { IdentityDoc } from '../../types'

const mockDocs: IdentityDoc[] = [
  { id: 1, doc_type: 'id_card', file_path: '/files/id.jpg', uploaded_at: '2024-01-01T12:00:00', media_url: '/media/id.jpg' },
  { id: 2, doc_type: 'business_license', file_path: '/files/license.pdf', uploaded_at: '2024-01-02T12:00:00', media_url: '/media/license.pdf' },
]

describe('IdentityDocList', () => {
  it('renders empty state when no docs', () => {
    render(<IdentityDocList docs={[]} />)
    expect(screen.getByText('暂无证件')).toBeInTheDocument()
  })

  it('renders doc cards when docs are provided', () => {
    render(<IdentityDocList docs={mockDocs} />)
    expect(screen.getByText('身份证')).toBeInTheDocument()
    expect(screen.getByText('营业执照')).toBeInTheDocument()
  })

  it('renders upload time for each doc', () => {
    render(<IdentityDocList docs={mockDocs} />)
    const times = screen.getAllByText('2024年01月01日 12:00')
    expect(times.length).toBeGreaterThanOrEqual(1)
  })

  it('renders multiple doc cards', () => {
    render(<IdentityDocList docs={mockDocs} />)
    // Both doc types should be shown
    expect(screen.getByText('身份证')).toBeInTheDocument()
    expect(screen.getByText('营业执照')).toBeInTheDocument()
  })

  it('displays doc type labels', () => {
    const docs: IdentityDoc[] = [
      { id: 1, doc_type: 'passport', file_path: '/files/passport.jpg', uploaded_at: '2024-01-01T12:00:00', media_url: null },
    ]
    render(<IdentityDocList docs={docs} />)
    expect(screen.getByText('护照')).toBeInTheDocument()
  })
})
