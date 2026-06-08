import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { InspirationPage } from '../components/InspirationPage'

vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  },
}))

vi.mock('@/components/ui/separator', () => ({
  Separator: () => <hr data-testid="separator" />,
}))

vi.mock('@/components/shared/ErrorBoundary', () => ({
  ErrorBoundary: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('../components/HotTopicList', () => ({
  HotTopicList: () => <div data-testid="hot-topic-list">HotTopicList</div>,
}))

vi.mock('../components/InspirationSection', () => ({
  InspirationSection: (props: Record<string, unknown>) => <div data-testid="inspiration-section" {...props}>InspirationSection</div>,
}))

vi.mock('../components/CreateTaskDialog', () => ({
  CreateTaskDialog: (props: Record<string, unknown>) => <div data-testid="create-task-dialog" {...props}>CreateTaskDialog</div>,
}))

describe('InspirationPage', () => {
  it('renders the page', () => {
    render(<MemoryRouter><InspirationPage /></MemoryRouter>)
    expect(screen.getByTestId('hot-topic-list')).toBeInTheDocument()
  })

  it('renders inspiration section', () => {
    render(<MemoryRouter><InspirationPage /></MemoryRouter>)
    expect(screen.getByTestId('inspiration-section')).toBeInTheDocument()
  })

  it('renders separator between sections', () => {
    render(<MemoryRouter><InspirationPage /></MemoryRouter>)
    expect(screen.getByTestId('separator')).toBeInTheDocument()
  })

  it('renders create task dialog', () => {
    render(<MemoryRouter><InspirationPage /></MemoryRouter>)
    expect(screen.getByTestId('create-task-dialog')).toBeInTheDocument()
  })
})
