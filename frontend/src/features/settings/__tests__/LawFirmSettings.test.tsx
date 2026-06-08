import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { LawFirmSettings } from '../components/LawFirmSettings'

vi.mock('lucide-react', () => ({
  ArrowLeft: (props: Record<string, unknown>) => <svg data-testid="arrow-left" {...props} />,
  Plus: (props: Record<string, unknown>) => <svg data-testid="plus-icon" {...props} />,
}))

vi.mock('@/features/organization/hooks/use-lawfirms', () => ({
  useLawFirms: () => ({ data: [], isLoading: false }),
}))

vi.mock('@/features/organization/components/LawFirmTable', () => ({
  LawFirmTable: ({ lawFirms, isLoading }: { lawFirms: unknown[]; isLoading: boolean }) => (
    <div data-testid="lawfirm-table">LawFirmTable ({lawFirms.length} items, loading: {String(isLoading)})</div>
  ),
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
}))

vi.mock('@/routes/paths', () => ({
  PATHS: {
    ADMIN_SETTINGS: '/admin/settings',
    ADMIN_LAWFIRM_NEW: '/admin/lawfirms/new',
  },
}))

describe('LawFirmSettings', () => {
  it('renders page title', () => {
    render(<MemoryRouter><LawFirmSettings /></MemoryRouter>)
    expect(screen.getByText('律所设置')).toBeInTheDocument()
  })

  it('renders description text', () => {
    render(<MemoryRouter><LawFirmSettings /></MemoryRouter>)
    expect(screen.getByText(/管理律所名称/)).toBeInTheDocument()
  })

  it('renders back button', () => {
    render(<MemoryRouter><LawFirmSettings /></MemoryRouter>)
    expect(screen.getByText('返回设置')).toBeInTheDocument()
  })

  it('renders new law firm button', () => {
    render(<MemoryRouter><LawFirmSettings /></MemoryRouter>)
    expect(screen.getByText('新建律所')).toBeInTheDocument()
  })

  it('renders law firm table', () => {
    render(<MemoryRouter><LawFirmSettings /></MemoryRouter>)
    expect(screen.getByTestId('lawfirm-table')).toBeInTheDocument()
  })
})
