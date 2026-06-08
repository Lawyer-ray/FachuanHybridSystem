import { render, screen, fireEvent } from '@testing-library/react'
import { TeamTable } from '../TeamTable'
import type { Team, LawFirm } from '../../types'

describe('TeamTable', () => {
  const mockLawFirms: LawFirm[] = [
    { id: 1, name: '大成律所', address: '', phone: '', social_credit_code: '' },
  ]

  const mockTeams: Team[] = [
    { id: 1, name: '民事诉讼组', team_type: 'lawyer', law_firm: 1 },
    { id: 2, name: '市场推广组', team_type: 'biz', law_firm: 1 },
  ]

  it('renders table headers', () => {
    render(<TeamTable teams={[]} lawFirms={[]} onEdit={vi.fn()} onDelete={vi.fn()} />)
    expect(screen.getByText('团队名称')).toBeInTheDocument()
    expect(screen.getByText('团队类型')).toBeInTheDocument()
    expect(screen.getByText('所属律所')).toBeInTheDocument()
    expect(screen.getByText('操作')).toBeInTheDocument()
  })

  it('renders team data rows', () => {
    render(<TeamTable teams={mockTeams} lawFirms={mockLawFirms} onEdit={vi.fn()} onDelete={vi.fn()} />)
    expect(screen.getByText('民事诉讼组')).toBeInTheDocument()
    expect(screen.getByText('市场推广组')).toBeInTheDocument()
    expect(screen.getByText('律师团队')).toBeInTheDocument()
    expect(screen.getByText('业务团队')).toBeInTheDocument()
  })

  it('shows empty state when no teams', () => {
    render(<TeamTable teams={[]} lawFirms={[]} onEdit={vi.fn()} onDelete={vi.fn()} />)
    expect(screen.getByText('暂无团队数据')).toBeInTheDocument()
  })

  it('calls onEdit when edit button clicked', () => {
    const onEdit = vi.fn()
    render(<TeamTable teams={mockTeams} lawFirms={mockLawFirms} onEdit={onEdit} onDelete={vi.fn()} />)
    fireEvent.click(screen.getByLabelText('编辑团队 民事诉讼组'))
    expect(onEdit).toHaveBeenCalledWith(mockTeams[0])
  })

  it('calls onDelete when delete button clicked', () => {
    const onDelete = vi.fn()
    render(<TeamTable teams={mockTeams} lawFirms={mockLawFirms} onEdit={vi.fn()} onDelete={onDelete} />)
    fireEvent.click(screen.getByLabelText('删除团队 民事诉讼组'))
    expect(onDelete).toHaveBeenCalledWith(mockTeams[0])
  })
})
