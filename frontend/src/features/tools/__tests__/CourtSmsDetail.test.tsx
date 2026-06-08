import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { CourtSmsDetail } from '../components/CourtSmsDetail'

vi.mock('lucide-react', () => ({
  ArrowLeft: () => <svg data-testid="arrow-left" />,
  Trash2: () => <svg data-testid="trash" />,
  FileWarning: () => <svg data-testid="file-warning" />,
  Link2: () => <svg data-testid="link2" />,
  AlertTriangle: () => <svg data-testid="alert-triangle" />,
  CheckCircle2: () => <svg data-testid="check-circle" />,
  XCircle: () => <svg data-testid="x-circle" />,
  Clock: () => <svg data-testid="clock" />,
  Download: () => <svg data-testid="download" />,
  Pencil: () => <svg data-testid="pencil" />,
  FolderDown: () => <svg data-testid="folder-down" />,
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

vi.mock('@/lib/date', () => ({ formatDate: (d: string) => d ?? '' }))

vi.mock('@/lib/token', () => ({ getAccessToken: () => 'test-token' }))

vi.mock('../hooks/use-court-sms', () => ({
  useCourtSms: () => ({
    data: null,
    isLoading: false,
    error: null,
  }),
}))

vi.mock('../api/court-sms', () => ({
  courtSmsApi: {
    deleteSms: vi.fn(),
    parseSms: vi.fn(),
    retryDownload: vi.fn(),
  },
}))

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}))

vi.mock('@/routes/paths', () => ({
  PATHS: { ADMIN_COURT_SMS: '/admin/tools/court-sms' },
  generatePath: { courtSmsDetail: (id: number) => `/admin/tools/court-sms/${id}` },
}))

vi.mock('@/components/shared', () => ({
  DetailField: ({ label, value }: { label: string; value: React.ReactNode }) => (
    <div data-testid="detail-field"><span>{label}</span><span>{value}</span></div>
  ),
  DetailCard: ({ title, children }: { title: string; children: React.ReactNode }) => (
    <div data-testid="detail-card"><h3>{title}</h3>{children}</div>
  ),
  StatusBadge: ({ children, variant }: { children: React.ReactNode; variant: string }) => (
    <span data-testid="status-badge" data-variant={variant}>{children}</span>
  ),
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
}))
vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, ...props }: Record<string, unknown>) => <span {...props}>{children}</span>,
}))
vi.mock('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogAction: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
  AlertDialogCancel: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
  AlertDialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

describe('CourtSmsDetail', () => {
  it('renders back button', () => {
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getByText('返回列表')).toBeInTheDocument()
  })

  it('renders not found when data is null', () => {
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getByText('短信不存在')).toBeInTheDocument()
  })


})
