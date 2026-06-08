import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { TaskDetail } from '../components/TaskDetail'

vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  },
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

vi.mock('@/lib/utils', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

vi.mock('../hooks/use-content-ops', () => ({
  useTaskDetail: () => ({ data: null, isLoading: true }),
  useTaskArticles: () => ({ data: [] }),
  useTaskEpisodes: () => ({ data: [] }),
  useTaskDiscussions: () => ({ data: [] }),
  useRetryTask: () => ({ mutate: vi.fn() }),
  useCancelTask: () => ({ mutate: vi.fn() }),
  useDeleteTask: () => ({ mutate: vi.fn() }),
  useReviewArticle: () => ({ mutate: vi.fn() }),
  useReviewEpisode: () => ({ mutate: vi.fn() }),
  useReviewDiscussion: () => ({ mutate: vi.fn() }),
  useUpdateArticle: () => ({ mutate: vi.fn() }),
  useRegenerateArticle: () => ({ mutate: vi.fn() }),
  useUpdateDiscussionTurn: () => ({ mutate: vi.fn() }),
  useRegenerateDiscussion: () => ({ mutate: vi.fn() }),
  useSynthesizeDiscussion: () => ({ mutate: vi.fn() }),
}))

vi.mock('../types', () => ({
  STATUS_LABEL: { pending: '待处理', running: '运行中', completed: '已完成', failed: '失败' },
  REVIEW_STATUS_LABEL: { pending: '待审核', approved: '已通过', rejected: '已拒绝' },
}))

vi.mock('../api', () => ({
  contentOpsApi: { getTask: vi.fn() },
}))

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
}))
vi.mock('@/components/ui/card', () => ({
  Card: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  CardContent: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  CardDescription: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  CardHeader: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  CardTitle: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
}))
vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, ...props }: Record<string, unknown>) => <span {...props}>{children}</span>,
}))
vi.mock('@/components/ui/progress', () => ({
  Progress: (props: Record<string, unknown>) => <div data-testid="progress" {...props} />,
}))
vi.mock('@/components/ui/tabs', () => ({
  Tabs: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TabsContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TabsList: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TabsTrigger: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
}))
vi.mock('@/components/ui/textarea', () => ({
  Textarea: (props: Record<string, unknown>) => <textarea {...props} />,
}))
vi.mock('@/components/ui/input', () => ({
  Input: (props: Record<string, unknown>) => <input {...props} />,
}))
vi.mock('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogAction: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
  AlertDialogCancel: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
  AlertDialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

describe('TaskDetail', () => {
  it('shows loading state when loading', () => {
    const { container } = render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    // The component renders a loader spinner when isLoading is true
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('renders without crashing', () => {
    const { container } = render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(container).toBeTruthy()
  })
})
