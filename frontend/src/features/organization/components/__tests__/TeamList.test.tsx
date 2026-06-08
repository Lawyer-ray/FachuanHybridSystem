vi.mock('../../hooks/use-teams', () => ({
  useTeams: vi.fn().mockReturnValue({ data: [], isLoading: false }),
}))
vi.mock('../../hooks/use-team-mutations', () => ({
  useTeamMutations: () => ({
    deleteTeam: { mutate: vi.fn(), isPending: false },
    createTeam: { mutate: vi.fn(), isPending: false },
    updateTeam: { mutate: vi.fn(), isPending: false },
  }),
}))
vi.mock('../../hooks/use-lawfirms', () => ({
  useLawFirms: () => ({ data: [{ id: 1, name: '大成律所' }] }),
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import { render, screen } from '@testing-library/react'
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
})
