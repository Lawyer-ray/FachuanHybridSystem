vi.mock('../../hooks/use-team-mutations', () => ({
  useTeamMutations: () => ({
    createTeam: { mutate: vi.fn(), isPending: false },
    updateTeam: { mutate: vi.fn(), isPending: false },
  }),
}))

vi.mock('../../hooks/use-lawfirms', () => ({
  useLawFirms: () => ({ data: [{ id: 1, name: '大成律所' }], isLoading: false }),
}))

vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children }: any) => <div>{children}</div>,
  DialogContent: ({ children }: any) => <div>{children}</div>,
  DialogDescription: ({ children }: any) => <p>{children}</p>,
  DialogFooter: ({ children }: any) => <div>{children}</div>,
  DialogHeader: ({ children }: any) => <div>{children}</div>,
  DialogTitle: ({ children }: any) => <h2>{children}</h2>,
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import { render, screen } from '@testing-library/react'
import { TeamFormDialog } from '../TeamFormDialog'

describe('TeamFormDialog', () => {
  it('renders create mode title when open', () => {
    render(<TeamFormDialog open onOpenChange={vi.fn()} />)
    expect(screen.getByText('新建团队')).toBeInTheDocument()
  })

  it('renders edit mode title with team data', () => {
    const team = { id: 1, name: '诉讼组', team_type: 'lawyer' as const, law_firm: 1 }
    render(<TeamFormDialog open onOpenChange={vi.fn()} team={team} />)
    expect(screen.getByText('编辑团队')).toBeInTheDocument()
  })

  it('renders form fields when open', () => {
    render(<TeamFormDialog open onOpenChange={vi.fn()} />)
    expect(screen.getByPlaceholderText('请输入团队名称')).toBeInTheDocument()
  })

  it('renders save and cancel buttons', () => {
    render(<TeamFormDialog open onOpenChange={vi.fn()} />)
    expect(screen.getByText('保存')).toBeInTheDocument()
    expect(screen.getByText('取消')).toBeInTheDocument()
  })
})
