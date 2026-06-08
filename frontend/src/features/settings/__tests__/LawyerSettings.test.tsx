import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { LawyerSettings } from '../components/LawyerSettings'

vi.mock('lucide-react', () => ({
  ArrowLeft: (props: Record<string, unknown>) => <svg data-testid="arrow-left" {...props} />,
  Plus: (props: Record<string, unknown>) => <svg data-testid="plus-icon" {...props} />,
}))

vi.mock('@/features/organization/hooks/use-lawyers', () => ({
  useLawyers: () => ({ data: [], isLoading: false }),
}))

vi.mock('@/features/organization/components/LawyerTable', () => ({
  LawyerTable: ({ lawyers, isLoading }: { lawyers: unknown[]; isLoading: boolean }) => (
    <div data-testid="lawyer-table">LawyerTable ({lawyers.length} items, loading: {String(isLoading)})</div>
  ),
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
}))

vi.mock('@/routes/paths', () => ({
  PATHS: {
    ADMIN_SETTINGS: '/admin/settings',
    ADMIN_LAWYER_NEW: '/admin/lawyers/new',
  },
}))

describe('LawyerSettings', () => {
  it('renders page title', () => {
    render(<MemoryRouter><LawyerSettings /></MemoryRouter>)
    expect(screen.getByText('律师设置')).toBeInTheDocument()
  })

  it('renders description text', () => {
    render(<MemoryRouter><LawyerSettings /></MemoryRouter>)
    expect(screen.getByText(/管理律师账号/)).toBeInTheDocument()
  })

  it('renders back button', () => {
    render(<MemoryRouter><LawyerSettings /></MemoryRouter>)
    expect(screen.getByText('返回设置')).toBeInTheDocument()
  })

  it('renders new lawyer button', () => {
    render(<MemoryRouter><LawyerSettings /></MemoryRouter>)
    expect(screen.getByText('新建律师')).toBeInTheDocument()
  })

  it('renders lawyer table', () => {
    render(<MemoryRouter><LawyerSettings /></MemoryRouter>)
    expect(screen.getByTestId('lawyer-table')).toBeInTheDocument()
  })
})
