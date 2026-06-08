vi.mock('../../hooks/use-content-ops', () => ({
  useCreateTask: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('@/features/organization/hooks/use-credentials', () => ({
  useCredentials: () => ({ data: [] }),
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
import { CreateTaskDialog } from '../CreateTaskDialog'

describe('CreateTaskDialog', () => {
  it('renders dialog title when open', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    expect(screen.getByText('创建内容任务')).toBeInTheDocument()
  })

  it('renders mode buttons', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    expect(screen.getByText('检索模式')).toBeInTheDocument()
    expect(screen.getByText('直投模式')).toBeInTheDocument()
  })

  it('renders voice selector', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    expect(screen.getByText('语音音色')).toBeInTheDocument()
  })

  it('renders create and cancel buttons', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    expect(screen.getByText('创建任务')).toBeInTheDocument()
    expect(screen.getByText('取消')).toBeInTheDocument()
  })

  it('shows direct mode content input by default', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    expect(screen.getByPlaceholderText('粘贴案例内容、判决书摘要或任何法律文本...')).toBeInTheDocument()
  })
})
