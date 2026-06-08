import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { TeamSettings } from '../components/TeamSettings'

vi.mock('lucide-react', () => ({
  ArrowLeft: (props: Record<string, unknown>) => <svg data-testid="arrow-left" {...props} />,
  Plus: (props: Record<string, unknown>) => <svg data-testid="plus-icon" {...props} />,
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/features/organization/hooks/use-teams', () => ({
  useTeams: () => ({ data: [], isLoading: false }),
}))

vi.mock('@/features/organization/hooks/use-team-mutations', () => ({
  useTeamMutations: () => ({
    deleteTeam: { mutateAsync: vi.fn() },
  }),
}))

vi.mock('@/features/organization/hooks/use-lawfirms', () => ({
  useLawFirms: () => ({ data: [] }),
}))

vi.mock('@/features/organization/components/TeamTable', () => ({
  TeamTable: (props: Record<string, unknown>) => <div data-testid="team-table">TeamTable</div>,
}))

vi.mock('@/features/organization/components/TeamFormDialog', () => ({
  TeamFormDialog: (props: Record<string, unknown>) => <div data-testid="team-form-dialog">TeamFormDialog</div>,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
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
}))

vi.mock('@/routes/paths', () => ({
  PATHS: {
    ADMIN_SETTINGS: '/admin/settings',
  },
}))

describe('TeamSettings', () => {
  it('renders page title', () => {
    render(<MemoryRouter><TeamSettings /></MemoryRouter>)
    expect(screen.getByText('团队设置')).toBeInTheDocument()
  })

  it('renders description text', () => {
    render(<MemoryRouter><TeamSettings /></MemoryRouter>)
    expect(screen.getByText(/创建和管理业务团队/)).toBeInTheDocument()
  })

  it('renders back button', () => {
    render(<MemoryRouter><TeamSettings /></MemoryRouter>)
    expect(screen.getByText('返回设置')).toBeInTheDocument()
  })

  it('renders new team button', () => {
    render(<MemoryRouter><TeamSettings /></MemoryRouter>)
    expect(screen.getByText('新建团队')).toBeInTheDocument()
  })

  it('renders team table', () => {
    render(<MemoryRouter><TeamSettings /></MemoryRouter>)
    expect(screen.getByTestId('team-table')).toBeInTheDocument()
  })

  it('renders team form dialog', () => {
    render(<MemoryRouter><TeamSettings /></MemoryRouter>)
    expect(screen.getByTestId('team-form-dialog')).toBeInTheDocument()
  })
})
