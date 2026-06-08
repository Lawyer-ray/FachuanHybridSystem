// Mock all child components
vi.mock('../TopicInspiration', () => ({ TopicInspiration: () => <div data-testid="topic-inspiration" /> }))
vi.mock('../DirectInput', () => ({ DirectInput: () => <div data-testid="direct-input" /> }))
vi.mock('../TaskList', () => ({ TaskList: () => <div data-testid="task-list" /> }))
vi.mock('../TaskDetail', () => ({ TaskDetail: () => <div data-testid="task-detail" /> }))
vi.mock('../CreateTaskDialog', () => ({ CreateTaskDialog: () => <div data-testid="create-dialog" /> }))

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})

vi.mock('@/routes/paths', () => ({
  PATHS: { ADMIN_TOOLS_CONTENT_OPS_INSPIRATION: '/inspiration' },
}))

vi.mock('framer-motion', () => ({
  motion: { div: ({ children, ...props }: any) => <div {...props}>{children}</div> },
  AnimatePresence: ({ children }: any) => <>{children}</>,
}))

vi.mock('@/components/shared/ErrorBoundary', () => ({
  ErrorBoundary: ({ children }: any) => <>{children}</>,
}))

import { render, screen } from '@testing-library/react'
import { ContentWorkbench } from '../ContentWorkbench'

describe('ContentWorkbench', () => {
  it('renders page title', () => {
    render(<ContentWorkbench />)
    expect(screen.getByText('内容运营')).toBeInTheDocument()
  })

  it('renders new task button', () => {
    render(<ContentWorkbench />)
    expect(screen.getByText('新建任务')).toBeInTheDocument()
  })

  it('renders tab triggers', () => {
    render(<ContentWorkbench />)
    expect(screen.getByText('选题灵感')).toBeInTheDocument()
    expect(screen.getByText('直投内容')).toBeInTheDocument()
  })

  it('renders TaskList child', () => {
    render(<ContentWorkbench />)
    expect(screen.getByTestId('task-list')).toBeInTheDocument()
  })
})
