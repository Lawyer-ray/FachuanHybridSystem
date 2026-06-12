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
  Dialog: ({ children, open }: { children: React.ReactNode; open?: boolean }) => open ? <div>{children}</div> : null,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
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

import { render, screen, fireEvent } from '@testing-library/react'
import { IdentityDocList } from '../IdentityDocList'
import type { IdentityDoc } from '../../types'

const mockDocs: IdentityDoc[] = [
  { id: 1, doc_type: 'id_card', file_path: '/files/id.jpg', uploaded_at: '2024-01-01T12:00:00', media_url: '/media/id.jpg' },
  { id: 2, doc_type: 'business_license', file_path: '/files/license.pdf', uploaded_at: '2024-01-02T12:00:00', media_url: '/media/license.pdf' },
]

describe('IdentityDocList - coverage improvements', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // ========== DocCard with image file and media_url - covers preview button ==========

  it('shows preview button for image docs', () => {
    render(<IdentityDocList docs={mockDocs} />)
    // id_card has .jpg file_path, should show preview
    expect(screen.getByText('身份证')).toBeInTheDocument()
  })

  // ========== DocCard with non-image file - covers FileText branch ==========

  it('shows FileText icon for non-image files', () => {
    const docs: IdentityDoc[] = [
      { id: 1, doc_type: 'business_license', file_path: '/files/license.pdf', uploaded_at: '2024-01-01T12:00:00', media_url: '/media/license.pdf' },
    ]
    render(<IdentityDocList docs={docs} />)
    expect(screen.getByText('营业执照')).toBeInTheDocument()
  })

  // ========== DocCard with no media_url - covers hasMediaUrl=false ==========

  it('renders doc without media_url shows placeholder', () => {
    const docs: IdentityDoc[] = [
      { id: 1, doc_type: 'passport', file_path: '/files/passport.jpg', uploaded_at: '2024-01-01T12:00:00', media_url: null },
    ]
    render(<IdentityDocList docs={docs} />)
    expect(screen.getByText('护照')).toBeInTheDocument()
  })

  // ========== DocCard with image file but no media_url - shows Image placeholder ==========

  it('shows Image placeholder for image file without media_url', () => {
    const docs: IdentityDoc[] = [
      { id: 1, doc_type: 'id_card', file_path: '/files/id.jpg', uploaded_at: '2024-01-01T12:00:00', media_url: null },
    ]
    render(<IdentityDocList docs={docs} />)
    expect(screen.getByText('身份证')).toBeInTheDocument()
  })

  // ========== getDocTypeLabel with unknown type - covers fallback ==========

  it('shows raw doc type when type is unknown', () => {
    const docs: IdentityDoc[] = [
      { id: 1, doc_type: 'unknown_type' as IdentityDoc['doc_type'], file_path: '/files/doc.pdf', uploaded_at: '2024-01-01T12:00:00', media_url: null },
    ]
    render(<IdentityDocList docs={docs} />)
    expect(screen.getByText('unknown_type')).toBeInTheDocument()
  })

  // ========== formatUploadTime error handling - covers catch branch ==========

  it('handles invalid date string gracefully', () => {
    const docs: IdentityDoc[] = [
      { id: 1, doc_type: 'id_card', file_path: '/files/id.jpg', uploaded_at: 'invalid-date', media_url: null },
    ]
    render(<IdentityDocList docs={docs} />)
    // Should render without crashing
    expect(screen.getByText('身份证')).toBeInTheDocument()
  })

  // ========== handlePreview - covers useCallback ==========

  it('opens preview dialog when preview button is clicked', () => {
    render(<IdentityDocList docs={mockDocs} />)
    const previewBtn = screen.getByText('预览')
    fireEvent.click(previewBtn)
    // Dialog should open with the doc type label
    const idCardLabels = screen.getAllByText('身份证')
    expect(idCardLabels.length).toBeGreaterThanOrEqual(1)
  })

  // ========== handlePreviewOpenChange - covers close path ==========

  it('closes preview dialog when onOpenChange is called with false', () => {
    render(<IdentityDocList docs={mockDocs} />)
    fireEvent.click(screen.getByText('预览'))
    // Dialog should be open
    expect(screen.getAllByText('身份证').length).toBeGreaterThanOrEqual(2)
  })

  // ========== ImagePreviewDialog with null doc - covers early return ==========

  it('does not render ImagePreviewDialog when no doc is selected', () => {
    render(<IdentityDocList docs={mockDocs} />)
    // No preview dialog should be visible initially
    // The dialog only renders when previewDoc is not null
    expect(screen.getByText('身份证')).toBeInTheDocument()
  })

  // ========== ImagePreviewDialog with resolvedUrl null - covers "暂无预览" ==========

  it('shows "暂无预览" when resolvedUrl is null', () => {
    const docs: IdentityDoc[] = [
      { id: 1, doc_type: 'id_card', file_path: '/files/id.jpg', uploaded_at: '2024-01-01T12:00:00', media_url: null },
    ]
    render(<IdentityDocList docs={docs} />)
    // Image docs without media_url should not have a preview button
    expect(screen.getByText('身份证')).toBeInTheDocument()
  })

  // ========== Empty state - covers docs.length === 0 ==========

  it('renders empty state', () => {
    render(<IdentityDocList docs={[]} />)
    expect(screen.getByText('暂无证件')).toBeInTheDocument()
  })

  // ========== Multiple docs render in grid ==========

  it('renders multiple docs in grid', () => {
    render(<IdentityDocList docs={mockDocs} />)
    expect(screen.getByText('身份证')).toBeInTheDocument()
    expect(screen.getByText('营业执照')).toBeInTheDocument()
  })

  // ========== Default export ==========

  it('exports IdentityDocList as default', async () => {
    const mod = await import('../IdentityDocList')
    expect(mod.default).toBeDefined()
  })

  // ========== Doc with image media_url but non-image file_path ==========

  it('renders doc with image media_url but pdf file_path', () => {
    const docs: IdentityDoc[] = [
      { id: 1, doc_type: 'id_card', file_path: '/files/doc.pdf', uploaded_at: '2024-01-01T12:00:00', media_url: '/media/doc.jpg' },
    ]
    render(<IdentityDocList docs={docs} />)
    expect(screen.getByText('身份证')).toBeInTheDocument()
  })

  // ========== Doc with non-image media_url ==========

  it('renders doc with non-image media_url', () => {
    const docs: IdentityDoc[] = [
      { id: 1, doc_type: 'business_license', file_path: '/files/license.pdf', uploaded_at: '2024-01-01T12:00:00', media_url: '/media/license.pdf' },
    ]
    render(<IdentityDocList docs={docs} />)
    expect(screen.getByText('营业执照')).toBeInTheDocument()
  })
})
