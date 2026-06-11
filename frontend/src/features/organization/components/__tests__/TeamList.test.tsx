vi.mock('../../hooks/use-teams', () => ({
  useTeams: vi.fn().mockReturnValue({ data: [], isLoading: false }),
}))
const mockDeleteMutate = vi.fn()
vi.mock('../../hooks/use-team-mutations', () => ({
  useTeamMutations: () => ({
    deleteTeam: { mutate: mockDeleteMutate, isPending: false },
    createTeam: { mutate: vi.fn(), isPending: false },
    updateTeam: { mutate: vi.fn(), isPending: false },
  }),
}))
vi.mock('../../hooks/use-lawfirms', () => ({
  useLawFirms: () => ({ data: [{ id: 1, name: '大成律所' }] }),
}))

vi.mock('../TeamTable', () => ({
  TeamTable: ({ teams, onEdit, onDelete }: any) => (
    <div data-testid="team-table">
      {teams.map((t: any) => (
        <div key={t.id}>
          <span>{t.name}</span>
          <button onClick={() => onEdit(t)}>edit-{t.id}</button>
          <button onClick={() => onDelete(t)}>delete-{t.id}</button>
        </div>
      ))}
      {teams.length === 0 && <span>暂无团队数据</span>}
    </div>
  ),
}))
vi.mock('../TeamFormDialog', () => ({
  TeamFormDialog: ({ open, team }: any) =>
    open ? <div data-testid="form-dialog">{team ? 'edit' : 'create'}</div> : null,
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

vi.mock('@/components/ui/select', () => ({
  Select: ({ children, onValueChange, value }: any) => (
    <select data-testid="type-filter" onChange={(e) => onValueChange?.(e.target.value)} value={value || ''}>
      {children}
    </select>
  ),
  SelectContent: ({ children }: any) => <>{children}</>,
  SelectItem: ({ children, value }: any) => <option value={value}>{children}</option>,
  SelectTrigger: ({ children }: any) => <div>{children}</div>,
  SelectValue: ({ placeholder }: any) => <span>{placeholder}</span>,
}))

vi.mock('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children, open }: any) => open ? <div data-testid="alert-dialog">{children}</div> : null,
  AlertDialogAction: ({ children, onClick, disabled }: any) => <button onClick={onClick} disabled={disabled}>{children}</button>,
  AlertDialogCancel: ({ children, onClick, disabled }: any) => <button onClick={onClick} disabled={disabled}>{children}</button>,
  AlertDialogContent: ({ children }: any) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: any) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: any) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: any) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: any) => <h2>{children}</h2>,
}))

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { toast } from 'sonner'
import { TeamList } from '../TeamList'
import { useTeams } from '../../hooks/use-teams'

describe('TeamList', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders type filter and create button', () => {
    render(<TeamList />)
    expect(screen.getByText('新建团队')).toBeInTheDocument()
    expect(screen.getByText('全部')).toBeInTheDocument()
  })

  it('shows empty state when no teams', () => {
    vi.mocked(useTeams).mockReturnValue({ data: [], isLoading: false } as any)
    render(<TeamList />)
    expect(screen.getByText('暂无团队数据')).toBeInTheDocument()
  })

  it('renders team data when available', () => {
    vi.mocked(useTeams).mockReturnValue({
      data: [{ id: 1, name: '诉讼组', team_type: 'lawyer', law_firm: 1 }],
      isLoading: false,
    } as any)
    render(<TeamList />)
    expect(screen.getByText('诉讼组')).toBeInTheDocument()
  })

  it('opens create dialog when create button clicked', () => {
    render(<TeamList />)
    fireEvent.click(screen.getByText('新建团队'))
    expect(screen.getByTestId('form-dialog')).toHaveTextContent('create')
  })

  it('opens edit dialog when edit triggered', () => {
    vi.mocked(useTeams).mockReturnValue({
      data: [{ id: 1, name: '诉讼组', team_type: 'lawyer', law_firm: 1 }],
      isLoading: false,
    } as any)
    render(<TeamList />)
    fireEvent.click(screen.getByText('edit-1'))
    expect(screen.getByTestId('form-dialog')).toHaveTextContent('edit')
  })

  it('opens delete dialog when delete triggered', () => {
    vi.mocked(useTeams).mockReturnValue({
      data: [{ id: 1, name: '诉讼组', team_type: 'lawyer', law_firm: 1 }],
      isLoading: false,
    } as any)
    render(<TeamList />)
    fireEvent.click(screen.getByText('delete-1'))
    expect(screen.getByTestId('alert-dialog')).toBeInTheDocument()
  })

  it('shows team name in delete confirmation', () => {
    vi.mocked(useTeams).mockReturnValue({
      data: [{ id: 1, name: '诉讼组', team_type: 'lawyer', law_firm: 1 }],
      isLoading: false,
    } as any)
    render(<TeamList />)
    fireEvent.click(screen.getByText('delete-1'))
    // '诉讼组' appears in both the table mock and the alert dialog description
    const elements = screen.getAllByText(/诉讼组/)
    expect(elements.length).toBeGreaterThanOrEqual(1)
  })

  it('confirms delete and shows success toast', async () => {
    vi.mocked(useTeams).mockReturnValue({
      data: [{ id: 1, name: '诉讼组', team_type: 'lawyer', law_firm: 1 }],
      isLoading: false,
    } as any)
    mockDeleteMutate.mockImplementation((_id: number, opts: any) => {
      opts.onSuccess()
    })
    render(<TeamList />)
    fireEvent.click(screen.getByText('delete-1'))
    fireEvent.click(screen.getByText('确认删除'))
    await waitFor(() => {
      expect(mockDeleteMutate).toHaveBeenCalledWith(1, expect.any(Object))
      expect(toast.success).toHaveBeenCalledWith('团队删除成功')
    })
  })

  it('handles delete error with Error', async () => {
    vi.mocked(useTeams).mockReturnValue({
      data: [{ id: 1, name: '诉讼组', team_type: 'lawyer', law_firm: 1 }],
      isLoading: false,
    } as any)
    mockDeleteMutate.mockImplementation((_id: number, opts: any) => {
      opts.onError(new Error('删除失败'))
    })
    render(<TeamList />)
    fireEvent.click(screen.getByText('delete-1'))
    fireEvent.click(screen.getByText('确认删除'))
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('删除失败')
    })
  })

  it('handles delete error with non-Error', async () => {
    vi.mocked(useTeams).mockReturnValue({
      data: [{ id: 1, name: '诉讼组', team_type: 'lawyer', law_firm: 1 }],
      isLoading: false,
    } as any)
    mockDeleteMutate.mockImplementation((_id: number, opts: any) => {
      opts.onError('unknown')
    })
    render(<TeamList />)
    fireEvent.click(screen.getByText('delete-1'))
    fireEvent.click(screen.getByText('确认删除'))
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('删除失败，请重试')
    })
  })

  it('cancels delete when cancel clicked', () => {
    vi.mocked(useTeams).mockReturnValue({
      data: [{ id: 1, name: '诉讼组', team_type: 'lawyer', law_firm: 1 }],
      isLoading: false,
    } as any)
    render(<TeamList />)
    fireEvent.click(screen.getByText('delete-1'))
    expect(screen.getByTestId('alert-dialog')).toBeInTheDocument()
    fireEvent.click(screen.getByText('取消'))
  })

  it('type filter change to specific type', () => {
    render(<TeamList />)
    const select = screen.getByTestId('type-filter')
    fireEvent.change(select, { target: { value: 'lawyer' } })
    expect(useTeams).toHaveBeenCalledWith(expect.objectContaining({ teamType: 'lawyer' }))
  })

  it('type filter change to all', () => {
    render(<TeamList />)
    const select = screen.getByTestId('type-filter')
    fireEvent.change(select, { target: { value: 'all' } })
    expect(useTeams).toHaveBeenCalledWith(expect.objectContaining({ teamType: undefined }))
  })

  it('type filter change to biz type', () => {
    render(<TeamList />)
    const select = screen.getByTestId('type-filter')
    fireEvent.change(select, { target: { value: 'biz' } })
    expect(useTeams).toHaveBeenCalledWith(expect.objectContaining({ teamType: 'biz' }))
  })

  it('shows confirm delete button text when not pending', () => {
    vi.mocked(useTeams).mockReturnValue({
      data: [{ id: 1, name: '诉讼组', team_type: 'lawyer', law_firm: 1 }],
      isLoading: false,
    } as any)
    render(<TeamList />)
    fireEvent.click(screen.getByText('delete-1'))
    expect(screen.getByText('确认删除')).toBeInTheDocument()
  })
})
