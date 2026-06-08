import { render, screen, act, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { TeamSettings } from '../components/TeamSettings'
import { toast } from 'sonner'

const { mockDeleteTeamMutateAsync, mockNavigate } = vi.hoisted(() => ({
  mockDeleteTeamMutateAsync: vi.fn(),
  mockNavigate: vi.fn(),
}))

vi.mock('react-router', async () => {
  const actual = await vi.importActual('react-router')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

vi.mock('lucide-react', () => ({
  ArrowLeft: (props: Record<string, unknown>) => <svg data-testid="arrow-left" {...props} />,
  Plus: (props: Record<string, unknown>) => <svg data-testid="plus-icon" {...props} />,
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/features/organization/hooks/use-teams', () => ({
  useTeams: vi.fn().mockReturnValue({ data: [], isLoading: false }),
}))

vi.mock('@/features/organization/hooks/use-team-mutations', () => ({
  useTeamMutations: vi.fn().mockReturnValue({
    deleteTeam: { mutateAsync: mockDeleteTeamMutateAsync },
  }),
}))

vi.mock('@/features/organization/hooks/use-lawfirms', () => ({
  useLawFirms: vi.fn().mockReturnValue({ data: [] }),
}))

// Track props passed to TeamTable so we can invoke callbacks
let teamTableProps: Record<string, unknown> = {}
vi.mock('@/features/organization/components/TeamTable', () => ({
  TeamTable: (props: Record<string, unknown>) => {
    teamTableProps = props
    return <div data-testid="team-table">TeamTable</div>
  },
}))

// Track props passed to TeamFormDialog
let teamFormDialogProps: Record<string, unknown> = {}
vi.mock('@/features/organization/components/TeamFormDialog', () => ({
  TeamFormDialog: (props: Record<string, unknown>) => {
    teamFormDialogProps = props
    return <div data-testid="team-form-dialog">TeamFormDialog</div>
  },
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
}))

vi.mock('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children, open }: { children: React.ReactNode; open?: boolean }) => (
    <div data-testid="alert-dialog" data-open={open}>{children}</div>
  ),
  AlertDialogAction: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
  AlertDialogCancel: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
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
  beforeEach(() => {
    vi.clearAllMocks()
    teamTableProps = {}
    teamFormDialogProps = {}
  })

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

  it('navigates to settings on back button click', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter><TeamSettings /></MemoryRouter>)
    await user.click(screen.getByText('返回设置'))
    expect(mockNavigate).toHaveBeenCalledWith('/admin/settings')
  })

  it('opens form dialog when new team button is clicked', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter><TeamSettings /></MemoryRouter>)
    await user.click(screen.getByText('新建团队'))
    expect(teamFormDialogProps.open).toBe(true)
    expect(teamFormDialogProps.team).toBeUndefined()
  })

  it('opens form dialog in edit mode when handleEdit is called', async () => {
    render(<MemoryRouter><TeamSettings /></MemoryRouter>)
    const mockTeam = { id: 1, name: 'Team A' }
    act(() => {
      (teamTableProps.onEdit as (team: unknown) => void)(mockTeam)
    })
    await waitFor(() => {
      expect(teamFormDialogProps.open).toBe(true)
      expect(teamFormDialogProps.team).toEqual(mockTeam)
    })
  })

  it('opens delete dialog when handleDelete is called', async () => {
    render(<MemoryRouter><TeamSettings /></MemoryRouter>)
    const mockTeam = { id: 1, name: 'Team A' }
    act(() => {
      (teamTableProps.onDelete as (team: unknown) => void)(mockTeam)
    })
    await waitFor(() => {
      expect(screen.getByText(/确认删除团队/)).toBeInTheDocument()
    })
  })

  it('calls deleteTeam.mutateAsync on confirm delete', async () => {
    mockDeleteTeamMutateAsync.mockResolvedValue(undefined)
    render(<MemoryRouter><TeamSettings /></MemoryRouter>)
    const mockTeam = { id: 1, name: 'Team A' }
    act(() => {
      (teamTableProps.onDelete as (team: unknown) => void)(mockTeam)
    })

    await waitFor(() => {
      expect(screen.getByText('确认删除')).toBeInTheDocument()
    })
    await userEvent.setup().click(screen.getByText('确认删除'))
    expect(mockDeleteTeamMutateAsync).toHaveBeenCalledWith(1)
    expect(toast.success).toHaveBeenCalledWith('团队已删除')
  })

  it('shows error toast when delete fails', async () => {
    mockDeleteTeamMutateAsync.mockRejectedValue(new Error('fail'))
    render(<MemoryRouter><TeamSettings /></MemoryRouter>)
    const mockTeam = { id: 1, name: 'Team A' }
    act(() => {
      (teamTableProps.onDelete as (team: unknown) => void)(mockTeam)
    })

    await waitFor(() => {
      expect(screen.getByText('确认删除')).toBeInTheDocument()
    })
    await userEvent.setup().click(screen.getByText('确认删除'))
    expect(toast.error).toHaveBeenCalledWith('删除失败')
  })

  it('closes form dialog and clears editing team on close', () => {
    render(<MemoryRouter><TeamSettings /></MemoryRouter>)
    // Open edit mode
    const mockTeam = { id: 1, name: 'Team A' }
    act(() => {
      (teamTableProps.onEdit as (team: unknown) => void)(mockTeam)
    })
    // Close dialog
    act(() => {
      (teamFormDialogProps.onOpenChange as (open: boolean) => void)(false)
    })
  })

  it('handles cancel delete', async () => {
    render(<MemoryRouter><TeamSettings /></MemoryRouter>)
    const mockTeam = { id: 1, name: 'Team A' }
    act(() => {
      (teamTableProps.onDelete as (team: unknown) => void)(mockTeam)
    })
    await waitFor(() => {
      expect(screen.getByText('取消')).toBeInTheDocument()
    })
    await userEvent.setup().click(screen.getByText('取消'))
    expect(mockDeleteTeamMutateAsync).not.toHaveBeenCalled()
  })
})
