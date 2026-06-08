import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { WorkbenchWelcome } from '../WorkbenchWelcome'

describe('WorkbenchWelcome', () => {
  it('renders the welcome heading', () => {
    render(<WorkbenchWelcome onCreateSession={vi.fn()} isCreating={false} />)
    expect(screen.getByText('欢迎使用法穿工作台')).toBeInTheDocument()
  })

  it('renders the description text', () => {
    render(<WorkbenchWelcome onCreateSession={vi.fn()} isCreating={false} />)
    expect(screen.getByText(/AI 驱动的法律事务助手/)).toBeInTheDocument()
  })

  it('renders the create session button', () => {
    render(<WorkbenchWelcome onCreateSession={vi.fn()} isCreating={false} />)
    expect(screen.getByRole('button', { name: /新建会话/ })).toBeInTheDocument()
  })

  it('calls onCreateSession when button is clicked', async () => {
    const onCreateSession = vi.fn()
    const user = userEvent.setup()
    render(<WorkbenchWelcome onCreateSession={onCreateSession} isCreating={false} />)
    await user.click(screen.getByRole('button', { name: /新建会话/ }))
    expect(onCreateSession).toHaveBeenCalledTimes(1)
  })

  it('disables button when creating', () => {
    render(<WorkbenchWelcome onCreateSession={vi.fn()} isCreating={true} />)
    expect(screen.getByRole('button', { name: /新建会话/ })).toBeDisabled()
  })

  it('shows bot icon', () => {
    const { container } = render(<WorkbenchWelcome onCreateSession={vi.fn()} isCreating={false} />)
    expect(container.querySelector('svg')).toBeInTheDocument()
  })
})
