import { render, screen } from '@testing-library/react'
import { AuthoritySection } from '../components/AuthoritySection'
import type { SupervisingAuthority } from '../types'

vi.mock('lucide-react', () => ({
  Landmark: (props: Record<string, unknown>) => <svg data-testid="landmark-icon" {...props} />,
}))

const makeAuth = (overrides: Partial<SupervisingAuthority> = {}): SupervisingAuthority => ({
  id: 1,
  name: '北京市朝阳区人民法院',
  authority_type_display: '基层法院',
  ...overrides,
} as SupervisingAuthority)

describe('AuthoritySection', () => {
  it('renders empty state when no authorities', () => {
    render(<AuthoritySection authorities={[]} />)
    expect(screen.getByText('暂无主管机关')).toBeInTheDocument()
  })

  it('renders authority name', () => {
    render(<AuthoritySection authorities={[makeAuth()]} />)
    expect(screen.getByText('北京市朝阳区人民法院')).toBeInTheDocument()
  })

  it('renders authority type display', () => {
    render(<AuthoritySection authorities={[makeAuth()]} />)
    expect(screen.getByText('(基层法院)')).toBeInTheDocument()
  })

  it('renders "未命名机关" when name is empty', () => {
    render(<AuthoritySection authorities={[makeAuth({ name: '' })]} />)
    expect(screen.getByText('未命名机关')).toBeInTheDocument()
  })

  it('does not render type display when not provided', () => {
    render(<AuthoritySection authorities={[makeAuth({ authority_type_display: undefined })]} />)
    expect(screen.queryByText(/\(/)).not.toBeInTheDocument()
  })

  it('renders multiple authorities', () => {
    const auths = [
      makeAuth({ id: 1, name: '法院A' }),
      makeAuth({ id: 2, name: '法院B' }),
    ]
    render(<AuthoritySection authorities={auths} />)
    expect(screen.getByText('法院A')).toBeInTheDocument()
    expect(screen.getByText('法院B')).toBeInTheDocument()
  })

  it('renders landmark icons for each authority', () => {
    const auths = [
      makeAuth({ id: 1, name: '法院A' }),
      makeAuth({ id: 2, name: '法院B' }),
    ]
    render(<AuthoritySection authorities={auths} />)
    expect(screen.getAllByTestId('landmark-icon')).toHaveLength(2)
  })
})
