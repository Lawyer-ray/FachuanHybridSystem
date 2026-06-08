import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { CourtFilingSection } from '../components/CourtFilingSection'

vi.mock('lucide-react', () => ({
  Landmark: () => <svg data-testid="landmark" />,
  Loader2: () => <svg data-testid="loader" />,
  RefreshCw: () => <svg data-testid="refresh" />,
}))

vi.mock('@/lib/format', () => ({
  formatAmount: (v: number) => `¥${v}`,
}))

vi.mock('../api', () => ({
  caseApi: {},
}))

vi.mock('../api/court-filing', () => ({}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
}))
vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, ...props }: Record<string, unknown>) => <span {...props}>{children}</span>,
}))
vi.mock('@/components/shared', () => ({
  DetailCard: ({ title, children, extra }: { title: string; children: React.ReactNode; extra?: React.ReactNode }) => (
    <div data-testid="detail-card">
      <h3>{title}</h3>
      {extra}
      {children}
    </div>
  ),
}))

const mockCaseData = {
  id: 1,
  name: '测试案件',
  supervising_authorities: [{ authority_type: 'trial', name: '朝阳法院' }],
}

describe('CourtFilingSection', () => {
  it('renders the detail card title', () => {
    render(<MemoryRouter><CourtFilingSection caseId={1} caseData={mockCaseData as never} /></MemoryRouter>)
    expect(screen.getByText('法院一张网在线立案')).toBeInTheDocument()
  })

  it('renders landmark icon', () => {
    render(<MemoryRouter><CourtFilingSection caseId={1} caseData={mockCaseData as never} /></MemoryRouter>)
    expect(screen.getByTestId('landmark')).toBeInTheDocument()
  })

  it('renders Playwright text', () => {
    render(<MemoryRouter><CourtFilingSection caseId={1} caseData={mockCaseData as never} /></MemoryRouter>)
    expect(screen.getByText(/Playwright/)).toBeInTheDocument()
  })

  it('renders detail card', () => {
    render(<MemoryRouter><CourtFilingSection caseId={1} caseData={mockCaseData as never} /></MemoryRouter>)
    expect(screen.getByTestId('detail-card')).toBeInTheDocument()
  })

  it('renders court name from authorities', () => {
    render(<MemoryRouter><CourtFilingSection caseId={1} caseData={mockCaseData as never} /></MemoryRouter>)
    expect(screen.getByText('朝阳法院')).toBeInTheDocument()
  })
})
