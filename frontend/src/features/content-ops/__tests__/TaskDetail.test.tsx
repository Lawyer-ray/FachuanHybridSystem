import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TaskDetail } from '../components/TaskDetail'
import { toast } from 'sonner'
import type { ContentTask, GeneratedArticle, PodcastEpisode, DiscussionScript } from '../types'

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

vi.mock('lucide-react', () => {
  const icons = [
    'Loader2', 'FileText', 'Volume2', 'Play', 'Pause', 'Download',
    'ThumbsUp', 'ThumbsDown', 'Copy', 'Check', 'AlertCircle',
    'RotateCcw', 'XCircle', 'Pencil', 'RefreshCw', 'Trash2',
  ]
  const map: Record<string, React.FC> = {}
  for (const name of icons) {
    map[name] = (props: Record<string, unknown>) => <svg data-testid={`${name.toLowerCase()}-icon`} {...props} />
  }
  return map
})

vi.mock('@/lib/utils', () => ({ cn: (...args: string[]) => args.filter(Boolean).join(' ') }))

vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children as React.ReactNode}</div>,
  },
}))

vi.mock('@/components/ui/tabs', () => ({
  Tabs: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TabsList: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TabsTrigger: ({ children, value }: { children: React.ReactNode; value: string }) => <button data-value={value}>{children}</button>,
  TabsContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/ui/card', () => ({
  Card: ({ children, className }: { children: React.ReactNode; className?: string }) => <div className={className}>{children}</div>,
  CardContent: ({ children, className }: { children: React.ReactNode; className?: string }) => <div className={className}>{children}</div>,
  CardHeader: ({ children, className }: { children: React.ReactNode; className?: string }) => <div className={className}>{children}</div>,
  CardTitle: ({ children, className }: { children: React.ReactNode; className?: string }) => <h3 className={className}>{children}</h3>,
  CardDescription: ({ children, className }: { children: React.ReactNode; className?: string }) => <p className={className}>{children}</p>,
}))

vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, variant }: { children: React.ReactNode; variant?: string }) => <span data-variant={variant}>{children}</span>,
}))

vi.mock('@/components/ui/progress', () => ({
  Progress: ({ value }: { value?: number }) => <div role="progressbar" data-value={value} />,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, disabled, variant, size, className }: Record<string, unknown>) => (
    <button onClick={onClick as React.MouseEventHandler} disabled={disabled as boolean} className={className as string}>{children}</button>
  ),
}))

vi.mock('@/components/ui/textarea', () => ({
  Textarea: ({ value, onChange, placeholder, rows, className }: Record<string, unknown>) => (
    <textarea value={value as string} onChange={onChange as React.ChangeEventHandler} placeholder={placeholder as string} rows={rows as number} className={className as string} />
  ),
}))

vi.mock('@/components/ui/input', () => ({
  Input: (props: Record<string, unknown>) => <input {...props} />,
}))

vi.mock('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogAction: ({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) => <button onClick={onClick}>{children}</button>,
  AlertDialogCancel: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
  AlertDialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
  AlertDialogTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

const mockTaskDetail = vi.fn()
const mockTaskArticles = vi.fn()
const mockTaskEpisodes = vi.fn()
const mockTaskDiscussions = vi.fn()
const mockRetryMutate = vi.fn()
const mockCancelMutate = vi.fn()
const mockDeleteMutate = vi.fn()
const mockReviewArticleMutate = vi.fn()
const mockReviewEpisodeMutate = vi.fn()
const mockReviewDiscussionMutate = vi.fn()
const mockUpdateArticleMutate = vi.fn()
const mockRegenerateArticleMutate = vi.fn()
const mockUpdateDiscussionTurnMutate = vi.fn()
const mockRegenerateDiscussionMutate = vi.fn()
const mockSynthesizeDiscussionMutate = vi.fn()

vi.mock('../hooks/use-content-ops', () => ({
  useTaskDetail: (...args: unknown[]) => mockTaskDetail(...args),
  useTaskArticles: (...args: unknown[]) => mockTaskArticles(...args),
  useTaskEpisodes: (...args: unknown[]) => mockTaskEpisodes(...args),
  useTaskDiscussions: (...args: unknown[]) => mockTaskDiscussions(...args),
  useReviewArticle: () => ({ mutate: mockReviewArticleMutate, isPending: false }),
  useReviewEpisode: () => ({ mutate: mockReviewEpisodeMutate, isPending: false }),
  useReviewDiscussion: () => ({ mutate: mockReviewDiscussionMutate, isPending: false }),
  useRetryTask: () => ({ mutate: mockRetryMutate, isPending: false }),
  useCancelTask: () => ({ mutate: mockCancelMutate, isPending: false }),
  useDeleteTask: () => ({ mutate: mockDeleteMutate, isPending: false }),
  useUpdateArticle: () => ({ mutate: mockUpdateArticleMutate, isPending: false }),
  useRegenerateArticle: () => ({ mutate: mockRegenerateArticleMutate, isPending: false }),
  useUpdateDiscussionTurn: () => ({ mutate: mockUpdateDiscussionTurnMutate, isPending: false }),
  useRegenerateDiscussion: () => ({ mutate: mockRegenerateDiscussionMutate, isPending: false }),
  useSynthesizeDiscussion: () => ({ mutate: mockSynthesizeDiscussionMutate, isPending: false }),
}))

vi.mock('../api', () => ({
  contentOpsApi: {
    getAudioUrl: vi.fn((id: number) => `http://test/audio/${id}`),
    batchApproveArticles: vi.fn().mockResolvedValue({ results: [] }),
    batchApproveEpisodes: vi.fn().mockResolvedValue({ results: [] }),
    approveDiscussion: vi.fn().mockResolvedValue({}),
  },
}))

function makeTask(overrides: Partial<ContentTask> = {}): ContentTask {
  return {
    id: 1, mode: 'search', keyword: 'test-keyword', case_summary: '', voice: '冰糖',
    tts_style_prompt: '', output_mode: 'narration', discussion_speakers: [],
    source_title: '', source_court_text: '', source_judgment_date: '',
    status: 'completed', progress: 100, message: '', error: '',
    created_at: '2025-01-01', updated_at: '2025-01-01', ...overrides,
  }
}

function makeArticle(overrides: Partial<GeneratedArticle> = {}): GeneratedArticle {
  return {
    id: 1, title: 'Test Article', content: 'Test content body here', source_summary: '',
    review_status: 'draft', reviewer_notes: '', llm_model: 'gpt-4o',
    token_usage: { prompt_tokens: 100, completion_tokens: 200, total_tokens: 300 },
    created_at: '2025-01-01', updated_at: '2025-01-01', ...overrides,
  }
}

function makeEpisode(overrides: Partial<PodcastEpisode> = {}): PodcastEpisode {
  return {
    id: 1, article_id: 1, discussion_script_id: null, content_source: 'article',
    voice: '冰糖', audio_url: 'http://test/audio.mp3', duration_seconds: 120,
    file_size_bytes: 1024000, review_status: 'draft', reviewer_notes: '',
    created_at: '2025-01-01', updated_at: '2025-01-01', ...overrides,
  }
}

function makeDiscussion(overrides: Partial<DiscussionScript> = {}): DiscussionScript {
  return {
    id: 1, title: 'Test Discussion', topic: 'Legal topic', review_status: 'draft',
    reviewer_notes: '',
    turns: [
      { id: 1, speaker_name: 'Alice', speaker_style_prompt: '', text: 'Hello', order: 0 },
      { id: 2, speaker_name: 'Bob', speaker_style_prompt: '', text: 'Hi there', order: 1 },
    ],
    llm_model: 'gpt-4o',
    token_usage: { prompt_tokens: 50, completion_tokens: 100, total_tokens: 150 },
    created_at: '2025-01-01', updated_at: '2025-01-01', ...overrides,
  }
}

function renderWithProviders(ui: React.ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('TaskDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockTaskDetail.mockReturnValue({ data: undefined, isLoading: true })
    mockTaskArticles.mockReturnValue({ data: [] })
    mockTaskEpisodes.mockReturnValue({ data: [] })
    mockTaskDiscussions.mockReturnValue({ data: [] })
  })

  it('renders loading state', () => {
    mockTaskDetail.mockReturnValue({ data: undefined, isLoading: true })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.getByTestId('loader2-icon')).toBeInTheDocument()
  })

  it('renders loading when task is null', () => {
    mockTaskDetail.mockReturnValue({ data: null, isLoading: false })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.getByTestId('loader2-icon')).toBeInTheDocument()
  })

  it('renders completed task with title', () => {
    mockTaskDetail.mockReturnValue({ data: makeTask({ status: 'completed', source_title: 'My Title' }), isLoading: false })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.getByText('My Title')).toBeInTheDocument()
    expect(screen.getByText('已完成')).toBeInTheDocument()
  })

  it('renders keyword as fallback when no source_title', () => {
    mockTaskDetail.mockReturnValue({ data: makeTask({ status: 'completed', source_title: '', keyword: '关键词' }), isLoading: false })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.getByText('关键词')).toBeInTheDocument()
  })

  it('renders task id as fallback when no title or keyword', () => {
    mockTaskDetail.mockReturnValue({ data: makeTask({ status: 'completed', source_title: '', keyword: '' }), isLoading: false })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.getByText('任务 #1')).toBeInTheDocument()
  })

  it('renders court text and judgment date', () => {
    mockTaskDetail.mockReturnValue({
      data: makeTask({ status: 'completed', source_court_text: '最高法院', source_judgment_date: '2025-06-01' }),
      isLoading: false,
    })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.getByText(/最高法院/)).toBeInTheDocument()
  })

  it('renders court text without judgment date', () => {
    mockTaskDetail.mockReturnValue({
      data: makeTask({ status: 'completed', source_court_text: '地方法院', source_judgment_date: '' }),
      isLoading: false,
    })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.getByText('地方法院')).toBeInTheDocument()
  })

  it('renders progress bar for active task', () => {
    mockTaskDetail.mockReturnValue({ data: makeTask({ status: 'running', progress: 50, message: '处理中...' }), isLoading: false })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.getByText('处理中...')).toBeInTheDocument()
    expect(screen.getByText('50%')).toBeInTheDocument()
  })

  it('renders progress bar for pending task', () => {
    mockTaskDetail.mockReturnValue({ data: makeTask({ status: 'pending', progress: 0 }), isLoading: false })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.getByText('0%')).toBeInTheDocument()
  })

  it('renders progress bar for queued task', () => {
    mockTaskDetail.mockReturnValue({ data: makeTask({ status: 'queued', progress: 10 }), isLoading: false })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.getByText('10%')).toBeInTheDocument()
  })

  it('renders error card for failed task', () => {
    mockTaskDetail.mockReturnValue({
      data: makeTask({ status: 'failed', error: 'Something went wrong' }),
      isLoading: false,
    })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
    expect(screen.getByText('重试任务')).toBeInTheDocument()
  })

  it('does not render error card when failed but no error message', () => {
    mockTaskDetail.mockReturnValue({
      data: makeTask({ status: 'failed', error: '' }),
      isLoading: false,
    })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.queryByText('重试任务')).not.toBeInTheDocument()
  })

  it('renders cancel button for active task', () => {
    mockTaskDetail.mockReturnValue({ data: makeTask({ status: 'running' }), isLoading: false })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.getByText('取消任务')).toBeInTheDocument()
  })

  it('does not render cancel button for completed task', () => {
    mockTaskDetail.mockReturnValue({ data: makeTask({ status: 'completed' }), isLoading: false })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.queryByText('取消任务')).not.toBeInTheDocument()
  })

  it('renders delete button for inactive task', () => {
    mockTaskDetail.mockReturnValue({ data: makeTask({ status: 'completed' }), isLoading: false })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.getByText('删除任务')).toBeInTheDocument()
  })

  it('does not render delete button for active task', () => {
    mockTaskDetail.mockReturnValue({ data: makeTask({ status: 'running' }), isLoading: false })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.queryByText('删除任务')).not.toBeInTheDocument()
  })

  it('renders articles tab with content', () => {
    mockTaskDetail.mockReturnValue({ data: makeTask({ status: 'completed' }), isLoading: false })
    mockTaskArticles.mockReturnValue({ data: [makeArticle()] })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.getByText('文章 (1)')).toBeInTheDocument()
    expect(screen.getByText('Test Article')).toBeInTheDocument()
  })

  it('renders episodes tab with content', () => {
    mockTaskDetail.mockReturnValue({ data: makeTask({ status: 'completed' }), isLoading: false })
    mockTaskArticles.mockReturnValue({ data: [makeArticle({ review_status: 'approved' })] })
    mockTaskEpisodes.mockReturnValue({ data: [makeEpisode()] })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.getByText('音频 (1)')).toBeInTheDocument()
    expect(screen.getByText(/音色: 冰糖/)).toBeInTheDocument()
  })

  it('renders discussions tab with content', () => {
    mockTaskDetail.mockReturnValue({ data: makeTask({ status: 'completed' }), isLoading: false })
    mockTaskDiscussions.mockReturnValue({ data: [makeDiscussion()] })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.getByText('讨论稿 (1)')).toBeInTheDocument()
    expect(screen.getByText('Test Discussion')).toBeInTheDocument()
  })

  it('does not render tabs when no content', () => {
    mockTaskDetail.mockReturnValue({ data: makeTask({ status: 'completed' }), isLoading: false })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.queryByText('文章 (1)')).not.toBeInTheDocument()
    expect(screen.queryByText('音频 (1)')).not.toBeInTheDocument()
    expect(screen.queryByText('讨论稿 (1)')).not.toBeInTheDocument()
  })

  it('renders batch approve button when drafts exist', () => {
    mockTaskDetail.mockReturnValue({ data: makeTask({ status: 'completed' }), isLoading: false })
    mockTaskArticles.mockReturnValue({ data: [makeArticle({ review_status: 'draft' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.getByText(/一键全部通过/)).toBeInTheDocument()
  })

  it('does not render batch approve button when no drafts', () => {
    mockTaskDetail.mockReturnValue({ data: makeTask({ status: 'completed' }), isLoading: false })
    mockTaskArticles.mockReturnValue({ data: [makeArticle({ review_status: 'approved' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.queryByText(/一键全部通过/)).not.toBeInTheDocument()
  })

  it('renders secondary badge for failed status', () => {
    mockTaskDetail.mockReturnValue({ data: makeTask({ status: 'failed' }), isLoading: false })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.getByText('失败')).toBeInTheDocument()
  })

  it('renders secondary badge for cancelled status', () => {
    mockTaskDetail.mockReturnValue({ data: makeTask({ status: 'cancelled' }), isLoading: false })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.getByText('已取消')).toBeInTheDocument()
  })

  it('renders message as fallback when progress message empty', () => {
    mockTaskDetail.mockReturnValue({ data: makeTask({ status: 'running', message: '' }), isLoading: false })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.getByText('处理中...')).toBeInTheDocument()
  })
})

describe('TaskDetail - ArticleCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockTaskDetail.mockReturnValue({ data: makeTask({ status: 'completed' }), isLoading: false })
    mockTaskArticles.mockReturnValue({ data: [] })
    mockTaskEpisodes.mockReturnValue({ data: [] })
    mockTaskDiscussions.mockReturnValue({ data: [] })
  })

  it('renders article card with word count and reading time', () => {
    mockTaskArticles.mockReturnValue({ data: [makeArticle({ content: 'x'.repeat(600) })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.getByText(/600 字/)).toBeInTheDocument()
    expect(screen.getByText(/约 2 分钟/)).toBeInTheDocument()
  })

  it('renders model and token info', () => {
    mockTaskArticles.mockReturnValue({ data: [makeArticle()] })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.getByText(/模型: gpt-4o/)).toBeInTheDocument()
    expect(screen.getByText(/Token: 300/)).toBeInTheDocument()
  })

  it('renders source summary when present', () => {
    mockTaskArticles.mockReturnValue({ data: [makeArticle({ source_summary: '案件摘要' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.getByText('案件摘要')).toBeInTheDocument()
  })

  it('hides source summary when editing', () => {
    mockTaskArticles.mockReturnValue({ data: [makeArticle({ source_summary: '案件摘要' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    fireEvent.click(screen.getByText('编辑'))
    expect(screen.queryByText('案件摘要')).not.toBeInTheDocument()
  })

  it('shows expand button for long content', () => {
    mockTaskArticles.mockReturnValue({ data: [makeArticle({ content: 'x'.repeat(500) })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.getByText('展开全文')).toBeInTheDocument()
  })

  it('does not show expand button for short content', () => {
    mockTaskArticles.mockReturnValue({ data: [makeArticle({ content: 'short' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.queryByText('展开全文')).not.toBeInTheDocument()
  })

  it('toggles expand/collapse', () => {
    mockTaskArticles.mockReturnValue({ data: [makeArticle({ content: 'x'.repeat(500) })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    fireEvent.click(screen.getByText('展开全文'))
    expect(screen.getByText('收起')).toBeInTheDocument()
    fireEvent.click(screen.getByText('收起'))
    expect(screen.getByText('展开全文')).toBeInTheDocument()
  })

  it('copies article content to clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    mockTaskArticles.mockReturnValue({ data: [makeArticle()] })
    renderWithProviders(<TaskDetail taskId={1} />)
    fireEvent.click(screen.getByText('复制全文'))
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('已复制到剪贴板'))
  })

  it('handles clipboard copy failure', async () => {
    const writeText = vi.fn().mockRejectedValue(new Error('fail'))
    Object.assign(navigator, { clipboard: { writeText } })
    mockTaskArticles.mockReturnValue({ data: [makeArticle()] })
    renderWithProviders(<TaskDetail taskId={1} />)
    fireEvent.click(screen.getByText('复制全文'))
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('复制失败'))
  })

  it('opens edit mode', () => {
    mockTaskArticles.mockReturnValue({ data: [makeArticle()] })
    renderWithProviders(<TaskDetail taskId={1} />)
    fireEvent.click(screen.getByText('编辑'))
    // The input field and textarea should appear
    expect(screen.getByPlaceholderText('文章标题')).toBeInTheDocument()
  })

  it('cancels edit mode', () => {
    mockTaskArticles.mockReturnValue({ data: [makeArticle()] })
    renderWithProviders(<TaskDetail taskId={1} />)
    fireEvent.click(screen.getByText('编辑'))
    expect(screen.getByPlaceholderText('文章标题')).toBeInTheDocument()
    // Click the second 取消 button (the one inside the edit form, not AlertDialog)
    const cancelButtons = screen.getAllByText('取消')
    fireEvent.click(cancelButtons[cancelButtons.length - 1])
    // Should return to non-edit mode: "编辑" button should be visible again
    expect(screen.getByText('编辑')).toBeInTheDocument()
  })

  it('saves edited article', () => {
    mockTaskArticles.mockReturnValue({ data: [makeArticle()] })
    renderWithProviders(<TaskDetail taskId={1} />)
    fireEvent.click(screen.getByText('编辑'))
    fireEvent.click(screen.getByText('保存'))
    expect(mockUpdateArticleMutate).toHaveBeenCalled()
  })

  it('regenerates article', () => {
    mockTaskArticles.mockReturnValue({ data: [makeArticle()] })
    renderWithProviders(<TaskDetail taskId={1} />)
    fireEvent.click(screen.getByText('重新生成'))
    expect(mockRegenerateArticleMutate).toHaveBeenCalledWith(1, expect.any(Object))
  })

  it('shows reviewer notes for non-draft articles', () => {
    mockTaskArticles.mockReturnValue({ data: [makeArticle({ review_status: 'approved', reviewer_notes: 'Good article' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.getByText(/审核备注: Good article/)).toBeInTheDocument()
  })

  it('hides reviewer notes when no notes', () => {
    mockTaskArticles.mockReturnValue({ data: [makeArticle({ review_status: 'approved', reviewer_notes: '' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.queryByText(/审核备注/)).not.toBeInTheDocument()
  })

  it('shows review actions for draft articles', () => {
    mockTaskArticles.mockReturnValue({ data: [makeArticle({ review_status: 'draft' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.getByText('通过')).toBeInTheDocument()
    expect(screen.getByText('驳回')).toBeInTheDocument()
  })

  it('approves article', () => {
    mockTaskArticles.mockReturnValue({ data: [makeArticle({ review_status: 'draft' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    fireEvent.click(screen.getByText('通过'))
    expect(mockReviewArticleMutate).toHaveBeenCalledWith(
      { articleId: 1, action: 'approve', notes: undefined },
      expect.any(Object),
    )
  })

  it('rejects article', () => {
    mockTaskArticles.mockReturnValue({ data: [makeArticle({ review_status: 'draft' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    fireEvent.click(screen.getByText('驳回'))
    expect(mockReviewArticleMutate).toHaveBeenCalledWith(
      { articleId: 1, action: 'reject', notes: undefined },
      expect.any(Object),
    )
  })

  it('approves article with notes', () => {
    mockTaskArticles.mockReturnValue({ data: [makeArticle({ review_status: 'draft' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    const textarea = screen.getByPlaceholderText('审核备注（可选）')
    fireEvent.change(textarea, { target: { value: 'Good work' } })
    fireEvent.click(screen.getByText('通过'))
    expect(mockReviewArticleMutate).toHaveBeenCalledWith(
      { articleId: 1, action: 'approve', notes: 'Good work' },
      expect.any(Object),
    )
  })

  it('does not render edit/regenerate for non-draft', () => {
    mockTaskArticles.mockReturnValue({ data: [makeArticle({ review_status: 'approved' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.queryByText('编辑')).not.toBeInTheDocument()
    expect(screen.queryByText('重新生成')).not.toBeInTheDocument()
  })

  it('renders rejected badge', () => {
    mockTaskArticles.mockReturnValue({ data: [makeArticle({ review_status: 'rejected' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.getByText('已驳回')).toBeInTheDocument()
  })

  it('handles article without llm_model', () => {
    mockTaskArticles.mockReturnValue({ data: [makeArticle({ llm_model: '' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.queryByText(/模型:/)).not.toBeInTheDocument()
  })

  it('handles article without token_usage', () => {
    mockTaskArticles.mockReturnValue({ data: [makeArticle({ token_usage: null })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.queryByText(/Token:/)).not.toBeInTheDocument()
  })

  // --- New tests for uncovered lines ---

  it('triggers retry task mutation on confirm', () => {
    mockTaskDetail.mockReturnValue({
      data: makeTask({ status: 'failed', error: 'Something went wrong' }),
      isLoading: false,
    })
    renderWithProviders(<TaskDetail taskId={1} />)
    // Click "确认重试" button in the AlertDialogAction
    const retryButtons = screen.getAllByText('确认重试')
    fireEvent.click(retryButtons[0])
    expect(mockRetryMutate).toHaveBeenCalledWith(1)
  })

  it('triggers cancel task mutation on confirm', () => {
    mockTaskDetail.mockReturnValue({ data: makeTask({ status: 'running' }), isLoading: false })
    renderWithProviders(<TaskDetail taskId={1} />)
    const cancelButtons = screen.getAllByText('确认取消')
    fireEvent.click(cancelButtons[0])
    expect(mockCancelMutate).toHaveBeenCalledWith(1)
  })

  it('triggers delete task mutation on confirm', () => {
    mockTaskDetail.mockReturnValue({ data: makeTask({ status: 'completed' }), isLoading: false })
    renderWithProviders(<TaskDetail taskId={1} />)
    const deleteButtons = screen.getAllByText('确认删除')
    fireEvent.click(deleteButtons[0])
    expect(mockDeleteMutate).toHaveBeenCalledWith(1)
  })

  it('article review onSuccess callback clears notes', async () => {
    // Simulate the onSuccess callback path by testing the mutate call structure
    mockTaskArticles.mockReturnValue({ data: [makeArticle({ review_status: 'draft' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    fireEvent.click(screen.getByText('通过'))
    expect(mockReviewArticleMutate).toHaveBeenCalledWith(
      { articleId: 1, action: 'approve', notes: undefined },
      expect.objectContaining({
        onSuccess: expect.any(Function),
        onError: expect.any(Function),
      }),
    )
    // Trigger onSuccess callback
    const options = mockReviewArticleMutate.mock.calls[0][1]
    act(() => options.onSuccess())
    expect(toast.success).toHaveBeenCalledWith('文章已通过')
  })

  it('article review onError callback shows error', () => {
    mockTaskArticles.mockReturnValue({ data: [makeArticle({ review_status: 'draft' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    fireEvent.click(screen.getByText('通过'))
    const options = mockReviewArticleMutate.mock.calls[0][1]
    act(() => options.onError())
    expect(toast.error).toHaveBeenCalledWith('操作失败')
  })

  it('article review reject calls with correct action', () => {
    mockTaskArticles.mockReturnValue({ data: [makeArticle({ review_status: 'draft' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    fireEvent.click(screen.getByText('驳回'))
    const options = mockReviewArticleMutate.mock.calls[0][1]
    act(() => options.onSuccess())
    expect(toast.success).toHaveBeenCalledWith('文章已驳回')
  })

  it('save edit calls updateArticle mutate', () => {
    mockTaskArticles.mockReturnValue({ data: [makeArticle({ review_status: 'draft' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    fireEvent.click(screen.getByText('编辑'))
    fireEvent.click(screen.getByText('保存'))
    expect(mockUpdateArticleMutate).toHaveBeenCalled()
    const options = mockUpdateArticleMutate.mock.calls[0][1]
    act(() => options.onSuccess())
    expect(toast.success).toHaveBeenCalledWith('文章已更新')
  })

  it('save edit onError shows error', () => {
    mockTaskArticles.mockReturnValue({ data: [makeArticle({ review_status: 'draft' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    fireEvent.click(screen.getByText('编辑'))
    fireEvent.click(screen.getByText('保存'))
    const options = mockUpdateArticleMutate.mock.calls[0][1]
    act(() => options.onError())
    expect(toast.error).toHaveBeenCalledWith('保存失败')
  })

  it('regenerate article onError shows error', () => {
    mockTaskArticles.mockReturnValue({ data: [makeArticle({ review_status: 'draft' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    fireEvent.click(screen.getByText('重新生成'))
    const options = mockRegenerateArticleMutate.mock.calls[0][1]
    act(() => options.onSuccess())
    expect(toast.success).toHaveBeenCalledWith('文章已重新生成')
    act(() => options.onError())
    expect(toast.error).toHaveBeenCalledWith('重新生成失败')
  })

  it('exports article as markdown', () => {
    mockTaskArticles.mockReturnValue({ data: [makeArticle({ title: 'Test', content: 'Content' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    fireEvent.click(screen.getByText('导出'))
    expect(toast.success).toHaveBeenCalledWith('已导出 Markdown')
  })

  it('renders article with content over 300 chars shows expand', () => {
    mockTaskArticles.mockReturnValue({ data: [makeArticle({ content: 'x'.repeat(400) })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.getByText('展开全文')).toBeInTheDocument()
  })
})

describe('TaskDetail - EpisodeCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockTaskDetail.mockReturnValue({ data: makeTask({ status: 'completed' }), isLoading: false })
    mockTaskArticles.mockReturnValue({ data: [makeArticle()] })
    mockTaskEpisodes.mockReturnValue({ data: [] })
    mockTaskDiscussions.mockReturnValue({ data: [] })
  })

  function renderWithEpisodes(episodes: ReturnType<typeof makeEpisode>[]) {
    // Provide approved articles so their controls don't interfere with episode assertions
    mockTaskArticles.mockReturnValue({ data: [makeArticle({ review_status: 'approved' })] })
    mockTaskEpisodes.mockReturnValue({ data: episodes })
    const result = renderWithProviders(<TaskDetail taskId={1} />)
    return result
  }

  it('renders episode with voice name', () => {
    renderWithEpisodes([makeEpisode()])
    expect(screen.getByText(/音色: 冰糖/)).toBeInTheDocument()
  })

  it('renders file size', () => {
    renderWithEpisodes([makeEpisode({ file_size_bytes: 5242880 })])
    expect(screen.getByText('5.0MB')).toBeInTheDocument()
  })

  it('renders duration', () => {
    renderWithEpisodes([makeEpisode({ duration_seconds: 180 })])
    expect(screen.getByText('180秒')).toBeInTheDocument()
  })

  it('renders download link', () => {
    renderWithEpisodes([makeEpisode()])
    const link = screen.getByRole('link')
    expect(link).toHaveAttribute('href', 'http://test/audio/1')
  })

  it('renders review actions for draft episode', () => {
    renderWithEpisodes([makeEpisode({ review_status: 'draft' })])
    expect(screen.getByText('通过')).toBeInTheDocument()
  })

  it('approves episode', () => {
    renderWithEpisodes([makeEpisode({ review_status: 'draft' })])
    fireEvent.click(screen.getByText('通过'))
    expect(mockReviewEpisodeMutate).toHaveBeenCalledWith(
      { episodeId: 1, action: 'approve', notes: undefined },
      expect.any(Object),
    )
  })

  it('rejects episode with notes', () => {
    renderWithEpisodes([makeEpisode({ review_status: 'draft' })])
    const textarea = screen.getByPlaceholderText('审核备注（可选）')
    fireEvent.change(textarea, { target: { value: 'Needs work' } })
    fireEvent.click(screen.getByText('驳回'))
    expect(mockReviewEpisodeMutate).toHaveBeenCalledWith(
      { episodeId: 1, action: 'reject', notes: 'Needs work' },
      expect.any(Object),
    )
  })

  it('hides review for approved episode', () => {
    renderWithEpisodes([makeEpisode({ review_status: 'approved' })])
    expect(screen.queryByText('通过')).not.toBeInTheDocument()
  })

  it('renders play button', () => {
    renderWithEpisodes([makeEpisode()])
    expect(screen.getByTestId('play-icon')).toBeInTheDocument()
  })

  it('renders speed button with 1x', () => {
    renderWithEpisodes([makeEpisode()])
    expect(screen.getByText('1x')).toBeInTheDocument()
  })

  it('hides duration when not set', () => {
    renderWithEpisodes([makeEpisode({ duration_seconds: null })])
    expect(screen.queryByText(/秒$/)).not.toBeInTheDocument()
  })

  it('hides file size when not set', () => {
    renderWithEpisodes([makeEpisode({ file_size_bytes: null })])
    expect(screen.queryByText(/MB$/)).not.toBeInTheDocument()
  })

  // --- New tests for uncovered lines ---

  it('episode review approve callback fires', () => {
    renderWithEpisodes([makeEpisode({ review_status: 'draft' })])
    fireEvent.click(screen.getByText('通过'))
    const options = mockReviewEpisodeMutate.mock.calls[0][1]
    act(() => options.onSuccess())
    expect(toast.success).toHaveBeenCalledWith('音频已通过')
  })

  it('episode review reject callback fires', () => {
    renderWithEpisodes([makeEpisode({ review_status: 'draft' })])
    fireEvent.click(screen.getByText('驳回'))
    const options = mockReviewEpisodeMutate.mock.calls[0][1]
    act(() => options.onError())
    expect(toast.error).toHaveBeenCalledWith('操作失败')
  })

  it('episode review reject clears notes on success', () => {
    renderWithEpisodes([makeEpisode({ review_status: 'draft' })])
    fireEvent.click(screen.getByText('驳回'))
    const options = mockReviewEpisodeMutate.mock.calls[0][1]
    act(() => options.onSuccess())
    expect(toast.success).toHaveBeenCalledWith('音频已驳回')
  })

  it('audio element has onError handler', () => {
    renderWithEpisodes([makeEpisode()])
    const audio = document.querySelector('audio')
    expect(audio).toBeInTheDocument()
  })

  it('audio element onEnded handler sets playing false', () => {
    renderWithEpisodes([makeEpisode()])
    const audio = document.querySelector('audio') as HTMLAudioElement
    // Simulate ended event
    fireEvent.ended(audio)
    // Playing should be false (no pause icon visible)
    expect(screen.getByTestId('play-icon')).toBeInTheDocument()
  })

  it('audio element onError handler sets error state', () => {
    renderWithEpisodes([makeEpisode()])
    const audio = document.querySelector('audio') as HTMLAudioElement
    fireEvent.error(audio)
    expect(screen.getByText('音频加载失败')).toBeInTheDocument()
  })

  it('renders episode without file_size_bytes and duration', () => {
    renderWithEpisodes([makeEpisode({ file_size_bytes: null, duration_seconds: null })])
    expect(screen.queryByText(/MB$/)).not.toBeInTheDocument()
    expect(screen.queryByText(/秒$/)).not.toBeInTheDocument()
  })
})

describe('TaskDetail - DiscussionScriptCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockTaskDetail.mockReturnValue({ data: makeTask({ status: 'completed' }), isLoading: false })
    mockTaskArticles.mockReturnValue({ data: [] })
    mockTaskEpisodes.mockReturnValue({ data: [] })
    mockTaskDiscussions.mockReturnValue({ data: [] })
  })

  it('renders discussion title and topic', () => {
    mockTaskDiscussions.mockReturnValue({ data: [makeDiscussion()] })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.getByText('Test Discussion')).toBeInTheDocument()
    expect(screen.getByText('Legal topic')).toBeInTheDocument()
  })

  it('renders turns with speaker names', () => {
    mockTaskDiscussions.mockReturnValue({ data: [makeDiscussion()] })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.getByText('Alice')).toBeInTheDocument()
    expect(screen.getByText('Bob')).toBeInTheDocument()
  })

  it('renders turn count', () => {
    mockTaskDiscussions.mockReturnValue({ data: [makeDiscussion()] })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.getByText('2 轮对话')).toBeInTheDocument()
  })

  it('hides topic when not present', () => {
    mockTaskDiscussions.mockReturnValue({ data: [makeDiscussion({ topic: '' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.queryByText('Legal topic')).not.toBeInTheDocument()
  })

  it('renders review actions for draft discussion', () => {
    mockTaskDiscussions.mockReturnValue({ data: [makeDiscussion({ review_status: 'draft' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.getByText('重新生成')).toBeInTheDocument()
    expect(screen.getByText('合成音频')).toBeInTheDocument()
  })

  it('regenerates discussion', () => {
    mockTaskDiscussions.mockReturnValue({ data: [makeDiscussion({ review_status: 'draft' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    fireEvent.click(screen.getByText('重新生成'))
    expect(mockRegenerateDiscussionMutate).toHaveBeenCalledWith(1, expect.any(Object))
  })

  it('synthesizes discussion', () => {
    mockTaskDiscussions.mockReturnValue({ data: [makeDiscussion({ review_status: 'draft' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    fireEvent.click(screen.getByText('合成音频'))
    expect(mockSynthesizeDiscussionMutate).toHaveBeenCalledWith(1, expect.any(Object))
  })

  it('approves discussion', () => {
    mockTaskDiscussions.mockReturnValue({ data: [makeDiscussion({ review_status: 'draft' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    fireEvent.click(screen.getByText('通过'))
    expect(mockReviewDiscussionMutate).toHaveBeenCalledWith(
      { scriptId: 1, action: 'approve', notes: undefined },
      expect.any(Object),
    )
  })

  it('rejects discussion with notes', () => {
    mockTaskDiscussions.mockReturnValue({ data: [makeDiscussion({ review_status: 'draft' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    const textarea = screen.getByPlaceholderText('审核备注（可选）')
    fireEvent.change(textarea, { target: { value: 'Needs revision' } })
    fireEvent.click(screen.getByText('驳回'))
    expect(mockReviewDiscussionMutate).toHaveBeenCalledWith(
      { scriptId: 1, action: 'reject', notes: 'Needs revision' },
      expect.any(Object),
    )
  })

  it('hides review actions for approved discussion', () => {
    mockTaskDiscussions.mockReturnValue({ data: [makeDiscussion({ review_status: 'approved' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.queryByText('重新生成')).not.toBeInTheDocument()
    expect(screen.queryByText('合成音频')).not.toBeInTheDocument()
  })

  it('handles discussion without llm_model', () => {
    mockTaskDiscussions.mockReturnValue({ data: [makeDiscussion({ llm_model: '' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.queryByText(/模型:/)).not.toBeInTheDocument()
  })

  it('handles discussion without token_usage', () => {
    mockTaskDiscussions.mockReturnValue({ data: [makeDiscussion({ token_usage: null })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.queryByText(/Token:/)).not.toBeInTheDocument()
  })

  it('hides pencil buttons for non-draft discussions', () => {
    mockTaskDiscussions.mockReturnValue({ data: [makeDiscussion({ review_status: 'approved' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.queryByTestId('pencil-icon')).not.toBeInTheDocument()
  })

  it('renders rejected badge', () => {
    mockTaskDiscussions.mockReturnValue({ data: [makeDiscussion({ review_status: 'rejected' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.getByText('已驳回')).toBeInTheDocument()
  })

  // --- New tests for uncovered lines ---

  it('enters edit mode for discussion turn on pencil click', () => {
    mockTaskDiscussions.mockReturnValue({ data: [makeDiscussion({ review_status: 'draft' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    // Hover over a turn to reveal the pencil button, then click it
    const pencilButtons = screen.getAllByTestId('pencil-icon')
    fireEvent.click(pencilButtons[0])
    // Should show save/cancel buttons for the turn
    expect(screen.getByText('保存')).toBeInTheDocument()
  })

  it('cancels editing a discussion turn', () => {
    mockTaskDiscussions.mockReturnValue({ data: [makeDiscussion({ review_status: 'draft' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    const pencilButtons = screen.getAllByTestId('pencil-icon')
    fireEvent.click(pencilButtons[0])
    // Find the cancel button inside the turn editing area
    const cancelButtons = screen.getAllByText('取消')
    // The last cancel should be the turn editing cancel
    fireEvent.click(cancelButtons[cancelButtons.length - 1])
  })

  it('saves edited discussion turn', () => {
    mockTaskDiscussions.mockReturnValue({ data: [makeDiscussion({ review_status: 'draft' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    const pencilButtons = screen.getAllByTestId('pencil-icon')
    fireEvent.click(pencilButtons[0])
    // Click save
    const saveButtons = screen.getAllByText('保存')
    fireEvent.click(saveButtons[saveButtons.length - 1])
    expect(mockUpdateDiscussionTurnMutate).toHaveBeenCalled()
    const options = mockUpdateDiscussionTurnMutate.mock.calls[0][1]
    act(() => options.onSuccess())
    expect(toast.success).toHaveBeenCalledWith('对话已更新')
    act(() => options.onError())
    expect(toast.error).toHaveBeenCalledWith('保存失败')
  })

  it('discussion review approve callback', () => {
    mockTaskDiscussions.mockReturnValue({ data: [makeDiscussion({ review_status: 'draft' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    fireEvent.click(screen.getByText('通过'))
    const options = mockReviewDiscussionMutate.mock.calls[0][1]
    act(() => options.onSuccess())
    expect(toast.success).toHaveBeenCalledWith('讨论稿已通过')
  })

  it('discussion review reject callback', () => {
    mockTaskDiscussions.mockReturnValue({ data: [makeDiscussion({ review_status: 'draft' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    fireEvent.click(screen.getByText('驳回'))
    const options = mockReviewDiscussionMutate.mock.calls[0][1]
    act(() => options.onError())
    expect(toast.error).toHaveBeenCalledWith('操作失败')
  })

  it('discussion regenerate callbacks', () => {
    mockTaskDiscussions.mockReturnValue({ data: [makeDiscussion({ review_status: 'draft' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    fireEvent.click(screen.getByText('重新生成'))
    const options = mockRegenerateDiscussionMutate.mock.calls[0][1]
    act(() => options.onSuccess())
    expect(toast.success).toHaveBeenCalledWith('讨论稿已重新生成')
    act(() => options.onError())
    expect(toast.error).toHaveBeenCalledWith('重新生成失败')
  })

  it('discussion synthesize callbacks', () => {
    mockTaskDiscussions.mockReturnValue({ data: [makeDiscussion({ review_status: 'draft' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    fireEvent.click(screen.getByText('合成音频'))
    const options = mockSynthesizeDiscussionMutate.mock.calls[0][1]
    act(() => options.onSuccess())
    expect(toast.success).toHaveBeenCalledWith('音频合成完成')
    act(() => options.onError(new Error('合成失败原因')))
    expect(toast.error).toHaveBeenCalledWith('合成失败: 合成失败原因')
  })

  it('discussion without topic hides topic', () => {
    mockTaskDiscussions.mockReturnValue({ data: [makeDiscussion({ topic: '' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.queryByText('Legal topic')).not.toBeInTheDocument()
  })

  it('renders batch approve with articles only', async () => {
    const { contentOpsApi } = await import('../api')
    mockTaskArticles.mockReturnValue({ data: [makeArticle({ review_status: 'draft' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    fireEvent.click(screen.getByText(/一键全部通过/))
    await waitFor(() => {
      expect(contentOpsApi.batchApproveArticles).toHaveBeenCalled()
    })
  })

  it('renders batch approve with discussions only', async () => {
    const { contentOpsApi } = await import('../api')
    mockTaskDiscussions.mockReturnValue({ data: [makeDiscussion({ review_status: 'draft' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    fireEvent.click(screen.getByText(/一键全部通过/))
    await waitFor(() => {
      expect(contentOpsApi.approveDiscussion).toHaveBeenCalled()
    })
  })
})

describe('TaskDetail - BatchApproveButton', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockTaskDetail.mockReturnValue({ data: makeTask({ status: 'completed' }), isLoading: false })
    mockTaskArticles.mockReturnValue({ data: [] })
    mockTaskEpisodes.mockReturnValue({ data: [] })
    mockTaskDiscussions.mockReturnValue({ data: [] })
  })

  it('shows count of all draft items', () => {
    mockTaskArticles.mockReturnValue({ data: [makeArticle({ review_status: 'draft' })] })
    mockTaskEpisodes.mockReturnValue({ data: [makeEpisode({ review_status: 'draft' })] })
    mockTaskDiscussions.mockReturnValue({ data: [makeDiscussion({ review_status: 'draft' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    expect(screen.getByText(/一键全部通过 \(3\)/)).toBeInTheDocument()
  })

  it('batch approves all drafts', async () => {
    const { contentOpsApi } = await import('../api')
    mockTaskArticles.mockReturnValue({ data: [makeArticle({ id: 10, review_status: 'draft' })] })
    mockTaskEpisodes.mockReturnValue({ data: [makeEpisode({ id: 20, review_status: 'draft' })] })
    mockTaskDiscussions.mockReturnValue({ data: [makeDiscussion({ id: 30, review_status: 'draft' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    fireEvent.click(screen.getByText(/一键全部通过/))
    await waitFor(() => {
      expect(contentOpsApi.batchApproveArticles).toHaveBeenCalledWith([10])
      expect(contentOpsApi.batchApproveEpisodes).toHaveBeenCalledWith([20])
      expect(contentOpsApi.approveDiscussion).toHaveBeenCalledWith(30)
    })
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith(expect.stringContaining('已批量通过')))
  })

  it('batch approve handles only articles', async () => {
    const { contentOpsApi } = await import('../api')
    mockTaskArticles.mockReturnValue({ data: [makeArticle({ review_status: 'draft' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    fireEvent.click(screen.getByText(/一键全部通过/))
    await waitFor(() => {
      expect(contentOpsApi.batchApproveArticles).toHaveBeenCalled()
      expect(contentOpsApi.batchApproveEpisodes).not.toHaveBeenCalled()
    })
  })

  it('batch approve handles only episodes', async () => {
    const { contentOpsApi } = await import('../api')
    mockTaskEpisodes.mockReturnValue({ data: [makeEpisode({ review_status: 'draft' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    fireEvent.click(screen.getByText(/一键全部通过/))
    await waitFor(() => {
      expect(contentOpsApi.batchApproveArticles).not.toHaveBeenCalled()
      expect(contentOpsApi.batchApproveEpisodes).toHaveBeenCalled()
    })
  })

  it('batch approve handles only discussions', async () => {
    const { contentOpsApi } = await import('../api')
    mockTaskDiscussions.mockReturnValue({ data: [makeDiscussion({ review_status: 'draft' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    fireEvent.click(screen.getByText(/一键全部通过/))
    await waitFor(() => {
      expect(contentOpsApi.approveDiscussion).toHaveBeenCalled()
    })
  })

  it('batch approve shows error toast on failure', async () => {
    const { contentOpsApi } = await import('../api')
    vi.mocked(contentOpsApi.batchApproveArticles).mockRejectedValueOnce(new Error('fail'))
    mockTaskArticles.mockReturnValue({ data: [makeArticle({ review_status: 'draft' })] })
    renderWithProviders(<TaskDetail taskId={1} />)
    fireEvent.click(screen.getByText(/一键全部通过/))
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('批量操作失败'))
  })
})
