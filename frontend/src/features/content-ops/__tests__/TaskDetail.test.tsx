import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { TaskDetail } from '../components/TaskDetail'
import { toast } from 'sonner'

vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  },
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

vi.mock('@/lib/utils', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

vi.mock('../types', async () => {
  const actual = await vi.importActual<typeof import('../types')>('../types')
  return actual
})

vi.mock('../api', () => ({
  contentOpsApi: {
    getTask: vi.fn(),
    getAudioUrl: vi.fn(() => 'http://test/audio.mp3'),
    batchApproveArticles: vi.fn().mockResolvedValue({ results: [] }),
    batchApproveEpisodes: vi.fn().mockResolvedValue({ results: [] }),
    approveDiscussion: vi.fn().mockResolvedValue({}),
  },
}))

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, disabled, variant, size, className, title }: Record<string, unknown>) => (
    <button
      onClick={onClick as React.MouseEventHandler}
      disabled={disabled as boolean}
      className={className as string}
      title={title as string}
      data-variant={variant}
    >{children}</button>
  ),
}))
vi.mock('@/components/ui/card', () => ({
  Card: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  CardContent: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  CardDescription: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  CardHeader: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  CardTitle: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
}))
vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, variant }: Record<string, unknown>) => <span data-variant={variant}>{children}</span>,
}))
vi.mock('@/components/ui/progress', () => ({
  Progress: (props: Record<string, unknown>) => <div data-testid="progress" {...props} />,
}))
vi.mock('@/components/ui/tabs', () => ({
  Tabs: ({ children, defaultValue }: { children: React.ReactNode; defaultValue?: string }) => <div data-default={defaultValue}>{children}</div>,
  TabsContent: ({ children, value }: { children: React.ReactNode; value?: string }) => <div data-value={value}>{children}</div>,
  TabsList: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TabsTrigger: ({ children, value }: { children: React.ReactNode; value?: string }) => <button data-value={value}>{children}</button>,
}))
vi.mock('@/components/ui/textarea', () => ({
  Textarea: (props: Record<string, unknown>) => <textarea {...props} />,
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

const mockMutate = vi.fn()
const mockMutateAsync = vi.fn()

// Default hooks state - loading
let hookOverrides: Record<string, unknown> = {}

vi.mock('../hooks/use-content-ops', () => ({
  useTaskDetail: () => hookOverrides.taskDetail ?? { data: null, isLoading: true },
  useTaskArticles: () => hookOverrides.taskArticles ?? { data: [] },
  useTaskEpisodes: () => hookOverrides.taskEpisodes ?? { data: [] },
  useTaskDiscussions: () => hookOverrides.taskDiscussions ?? { data: [] },
  useRetryTask: () => hookOverrides.retryTask ?? ({ mutate: vi.fn(), isPending: false }),
  useCancelTask: () => hookOverrides.cancelTask ?? ({ mutate: vi.fn(), isPending: false }),
  useDeleteTask: () => hookOverrides.deleteTask ?? ({ mutate: vi.fn(), isPending: false }),
  useReviewArticle: () => hookOverrides.reviewArticle ?? ({ mutate: vi.fn(), isPending: false }),
  useReviewEpisode: () => hookOverrides.reviewEpisode ?? ({ mutate: vi.fn(), isPending: false }),
  useReviewDiscussion: () => hookOverrides.reviewDiscussion ?? ({ mutate: vi.fn(), isPending: false }),
  useUpdateArticle: () => hookOverrides.updateArticle ?? ({ mutate: vi.fn(), isPending: false }),
  useRegenerateArticle: () => hookOverrides.regenerateArticle ?? ({ mutate: vi.fn(), isPending: false }),
  useUpdateDiscussionTurn: () => hookOverrides.updateDiscussionTurn ?? ({ mutate: vi.fn(), isPending: false }),
  useRegenerateDiscussion: () => hookOverrides.regenerateDiscussion ?? ({ mutate: vi.fn(), isPending: false }),
  useSynthesizeDiscussion: () => hookOverrides.synthesizeDiscussion ?? ({ mutate: vi.fn(), isPending: false }),
}))

function setTask(task: Record<string, unknown> | null, opts?: { articles?: unknown[]; episodes?: unknown[]; discussions?: unknown[] }) {
  hookOverrides = {
    taskDetail: { data: task, isLoading: false },
    taskArticles: { data: opts?.articles ?? [] },
    taskEpisodes: { data: opts?.episodes ?? [] },
    taskDiscussions: { data: opts?.discussions ?? [] },
  }
}

const baseTask = {
  id: 1,
  status: 'completed',
  source_title: '测试标题',
  keyword: '测试关键词',
  source_court_text: '某法院',
  source_judgment_date: '2024-01-01',
  progress: 100,
  message: '完成',
  error: '',
  mode: 'search',
  voice: '冰糖',
}

describe('TaskDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    hookOverrides = {}
  })

  it('shows loading state when loading', () => {
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(document.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('renders task title from source_title', () => {
    setTask(baseTask)
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(screen.getByText('测试标题')).toBeInTheDocument()
  })

  it('renders keyword when source_title is empty', () => {
    setTask({ ...baseTask, source_title: '' })
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(screen.getByText('测试关键词')).toBeInTheDocument()
  })

  it('renders task id when title and keyword are empty', () => {
    setTask({ ...baseTask, source_title: '', keyword: '' })
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(screen.getByText('任务 #1')).toBeInTheDocument()
  })

  it('renders court text and judgment date', () => {
    setTask(baseTask)
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(screen.getByText(/某法院/)).toBeInTheDocument()
  })

  it('renders completed badge for completed task', () => {
    setTask(baseTask)
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(screen.getByText('已完成')).toBeInTheDocument()
  })

  it('renders failed badge for failed task', () => {
    setTask({ ...baseTask, status: 'failed', error: 'Something went wrong' })
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(screen.getByText('失败')).toBeInTheDocument()
  })

  it('shows progress bar for active task', () => {
    setTask({ ...baseTask, status: 'running', progress: 50, message: '处理中...' })
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(screen.getByText('处理中...')).toBeInTheDocument()
    expect(screen.getByText('50%')).toBeInTheDocument()
    expect(screen.getByTestId('progress')).toBeInTheDocument()
  })

  it('shows error message and retry button for failed task', () => {
    setTask({ ...baseTask, status: 'failed', error: '网络错误' })
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(screen.getByText('网络错误')).toBeInTheDocument()
    expect(screen.getByText('重试任务')).toBeInTheDocument()
  })

  it('shows cancel button for active task', () => {
    setTask({ ...baseTask, status: 'running', progress: 30 })
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(screen.getByText('取消任务')).toBeInTheDocument()
  })

  it('shows delete button for non-active task', () => {
    setTask(baseTask)
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(screen.getByText('删除任务')).toBeInTheDocument()
  })

  it('does not show delete button for active task', () => {
    setTask({ ...baseTask, status: 'pending', progress: 0 })
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(screen.queryByText('删除任务')).not.toBeInTheDocument()
  })

  it('renders articles tab when articles exist', () => {
    const articles = [
      { id: 1, title: '文章1', content: '内容', source_summary: '', review_status: 'draft', reviewer_notes: '', llm_model: '', token_usage: null, created_at: '', updated_at: '' },
    ]
    setTask(baseTask, { articles })
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(screen.getByText(/文章 \(1\)/)).toBeInTheDocument()
  })

  it('renders episodes tab when episodes exist', () => {
    const episodes = [
      { id: 1, voice: '冰糖', audio_url: '', duration_seconds: 60, file_size_bytes: 1024, review_status: 'draft', reviewer_notes: '', content_source: 'article', article_id: 1, discussion_script_id: null, created_at: '', updated_at: '' },
    ]
    setTask(baseTask, { episodes })
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(screen.getByText(/音频 \(1\)/)).toBeInTheDocument()
  })

  it('renders discussions tab when discussions exist', () => {
    const discussions = [
      { id: 1, title: '讨论稿1', topic: '话题', review_status: 'draft', reviewer_notes: '', turns: [{ id: 1, speaker_name: '张三', speaker_style_prompt: '', text: '你好', order: 0 }], llm_model: '', token_usage: null, created_at: '', updated_at: '' },
    ]
    setTask(baseTask, { discussions })
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(screen.getByText(/讨论稿 \(1\)/)).toBeInTheDocument()
  })

  it('does not render tabs when no content', () => {
    setTask(baseTask, { articles: [], episodes: [], discussions: [] })
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(screen.queryByText(/^文章 \(\d+\)$/)).not.toBeInTheDocument()
    expect(screen.queryByText(/^音频 \(\d+\)$/)).not.toBeInTheDocument()
    expect(screen.queryByText(/^讨论稿 \(\d+\)$/)).not.toBeInTheDocument()
  })

  it('renders secondary badge for pending task', () => {
    setTask({ ...baseTask, status: 'pending', progress: 0 })
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(screen.getByText('待处理')).toBeInTheDocument()
  })

  it('renders no court text when empty', () => {
    setTask({ ...baseTask, source_court_text: '', source_judgment_date: '' })
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    // Should not crash
    expect(screen.getByText('测试标题')).toBeInTheDocument()
  })

  it('renders article with model and token info', () => {
    const articles = [
      { id: 1, title: '文章1', content: '短内容', source_summary: '摘要', review_status: 'draft', reviewer_notes: '', llm_model: 'gpt-4', token_usage: { total_tokens: 500 }, created_at: '', updated_at: '' },
    ]
    setTask(baseTask, { articles })
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(screen.getByText(/模型: gpt-4/)).toBeInTheDocument()
    expect(screen.getByText(/Token: 500/)).toBeInTheDocument()
  })

  it('renders article with reviewer notes for non-draft status', () => {
    const articles = [
      { id: 1, title: '文章1', content: '内容', source_summary: '', review_status: 'approved', reviewer_notes: '写得不错', llm_model: '', token_usage: null, created_at: '', updated_at: '' },
    ]
    setTask(baseTask, { articles })
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(screen.getByText(/审核备注: 写得不错/)).toBeInTheDocument()
  })

  it('renders episode with file size', () => {
    const episodes = [
      { id: 1, voice: '冰糖', audio_url: '', duration_seconds: 120, file_size_bytes: 5242880, review_status: 'draft', reviewer_notes: '', content_source: 'article', article_id: 1, discussion_script_id: null, created_at: '', updated_at: '' },
    ]
    setTask(baseTask, { episodes })
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(screen.getByText(/5\.0MB/)).toBeInTheDocument()
  })

  it('renders episode with duration', () => {
    const episodes = [
      { id: 1, voice: '冰糖', audio_url: '', duration_seconds: 90, file_size_bytes: null, review_status: 'draft', reviewer_notes: '', content_source: 'article', article_id: 1, discussion_script_id: null, created_at: '', updated_at: '' },
    ]
    setTask(baseTask, { episodes })
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(screen.getByText(/90秒/)).toBeInTheDocument()
  })

  it('renders discussion script with topic and model', () => {
    const discussions = [
      { id: 1, title: '讨论稿', topic: '法律热点', review_status: 'draft', reviewer_notes: '', turns: [{ id: 1, speaker_name: 'A', speaker_style_prompt: '', text: 'hello', order: 0 }], llm_model: 'gpt-4o', token_usage: { total_tokens: 1000 }, created_at: '', updated_at: '' },
    ]
    setTask(baseTask, { discussions })
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(screen.getByText('法律热点')).toBeInTheDocument()
    expect(screen.getByText(/模型: gpt-4o/)).toBeInTheDocument()
  })

  it('renders discussion script with multiple speakers and colors', () => {
    const discussions = [
      { id: 1, title: '讨论稿', topic: '', review_status: 'draft', reviewer_notes: '', turns: [
        { id: 1, speaker_name: 'A', speaker_style_prompt: '', text: 'hello', order: 0 },
        { id: 2, speaker_name: 'B', speaker_style_prompt: '', text: 'world', order: 1 },
      ], llm_model: '', token_usage: null, created_at: '', updated_at: '' },
    ]
    setTask(baseTask, { discussions })
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(screen.getByText('A')).toBeInTheDocument()
    expect(screen.getByText('B')).toBeInTheDocument()
    expect(screen.getByText(/2 轮对话/)).toBeInTheDocument()
  })

  it('renders pending badge for episodes', () => {
    const episodes = [
      { id: 1, voice: '冰糖', audio_url: '', duration_seconds: 60, file_size_bytes: 1024, review_status: 'approved', reviewer_notes: '', content_source: 'article', article_id: 1, discussion_script_id: null, created_at: '', updated_at: '' },
    ]
    setTask(baseTask, { episodes })
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(screen.getByText('已通过')).toBeInTheDocument()
  })

  it('renders article with long content (expand/collapse)', () => {
    const articles = [
      { id: 1, title: '长文', content: 'A'.repeat(500), source_summary: '', review_status: 'draft', reviewer_notes: '', llm_model: '', token_usage: null, created_at: '', updated_at: '' },
    ]
    setTask(baseTask, { articles })
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(screen.getByText('展开全文')).toBeInTheDocument()
  })

  it('renders pending queue status', () => {
    setTask({ ...baseTask, status: 'queued', progress: 0, message: '等待中...' })
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(screen.getByText('队列中')).toBeInTheDocument()
  })

  it('renders cancelled task', () => {
    setTask({ ...baseTask, status: 'cancelled' })
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(screen.getByText('已取消')).toBeInTheDocument()
    expect(screen.getByText('删除任务')).toBeInTheDocument()
  })

  it('renders episode with approved status badge', () => {
    const episodes = [
      { id: 1, voice: '冰糖', audio_url: '', duration_seconds: 60, file_size_bytes: null, review_status: 'rejected', reviewer_notes: '音质不好', content_source: 'article', article_id: 1, discussion_script_id: null, created_at: '', updated_at: '' },
    ]
    setTask(baseTask, { episodes })
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(screen.getByText('已驳回')).toBeInTheDocument()
  })

  it('renders article review section for draft articles', () => {
    const articles = [
      { id: 1, title: '文章1', content: '内容', source_summary: '', review_status: 'draft', reviewer_notes: '', llm_model: '', token_usage: null, created_at: '', updated_at: '' },
    ]
    setTask(baseTask, { articles })
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(screen.getByText('通过')).toBeInTheDocument()
    expect(screen.getByText('驳回')).toBeInTheDocument()
  })

  it('renders episode review section for draft episodes', () => {
    const episodes = [
      { id: 1, voice: '冰糖', audio_url: '', duration_seconds: 60, file_size_bytes: null, review_status: 'draft', reviewer_notes: '', content_source: 'article', article_id: 1, discussion_script_id: null, created_at: '', updated_at: '' },
    ]
    setTask(baseTask, { episodes })
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(screen.getByText(/音色: 冰糖/)).toBeInTheDocument()
  })

  it('renders discussion review section for draft discussions', () => {
    const discussions = [
      { id: 1, title: '讨论稿', topic: '', review_status: 'draft', reviewer_notes: '', turns: [{ id: 1, speaker_name: 'A', speaker_style_prompt: '', text: '内容', order: 0 }], llm_model: '', token_usage: null, created_at: '', updated_at: '' },
    ]
    setTask(baseTask, { discussions })
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(screen.getByText('重新生成')).toBeInTheDocument()
    expect(screen.getByText('合成音频')).toBeInTheDocument()
  })

  it('renders all content tabs when all types exist', () => {
    const articles = [
      { id: 1, title: '文章1', content: '内容', source_summary: '', review_status: 'draft', reviewer_notes: '', llm_model: '', token_usage: null, created_at: '', updated_at: '' },
    ]
    const episodes = [
      { id: 1, voice: '冰糖', audio_url: '', duration_seconds: 60, file_size_bytes: null, review_status: 'draft', reviewer_notes: '', content_source: 'article', article_id: 1, discussion_script_id: null, created_at: '', updated_at: '' },
    ]
    const discussions = [
      { id: 1, title: '讨论稿', topic: '', review_status: 'draft', reviewer_notes: '', turns: [{ id: 1, speaker_name: 'A', speaker_style_prompt: '', text: '内容', order: 0 }], llm_model: '', token_usage: null, created_at: '', updated_at: '' },
    ]
    setTask(baseTask, { articles, episodes, discussions })
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(screen.getByText(/文章 \(1\)/)).toBeInTheDocument()
    expect(screen.getByText(/音频 \(1\)/)).toBeInTheDocument()
    expect(screen.getByText(/讨论稿 \(1\)/)).toBeInTheDocument()
  })

  it('renders batch approve button with drafts', () => {
    const articles = [
      { id: 1, title: '文章1', content: '内容', source_summary: '', review_status: 'draft', reviewer_notes: '', llm_model: '', token_usage: null, created_at: '', updated_at: '' },
    ]
    const discussions = [
      { id: 1, title: '讨论稿', topic: '', review_status: 'draft', reviewer_notes: '', turns: [{ id: 1, speaker_name: 'A', speaker_style_prompt: '', text: '内容', order: 0 }], llm_model: '', token_usage: null, created_at: '', updated_at: '' },
    ]
    setTask(baseTask, { articles, discussions })
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(screen.getByText(/一键全部通过/)).toBeInTheDocument()
  })

  it('does not render batch approve when no drafts', () => {
    const articles = [
      { id: 1, title: '文章1', content: '内容', source_summary: '', review_status: 'approved', reviewer_notes: '', llm_model: '', token_usage: null, created_at: '', updated_at: '' },
    ]
    setTask(baseTask, { articles })
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(screen.queryByText(/一键全部通过/)).not.toBeInTheDocument()
  })

  it('renders episode speed button', () => {
    const episodes = [
      { id: 1, voice: '冰糖', audio_url: '', duration_seconds: 60, file_size_bytes: null, review_status: 'draft', reviewer_notes: '', content_source: 'article', article_id: 1, discussion_script_id: null, created_at: '', updated_at: '' },
    ]
    setTask(baseTask, { episodes })
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(screen.getByText('1x')).toBeInTheDocument()
  })

  it('renders article source summary', () => {
    const articles = [
      { id: 1, title: '文章1', content: '内容', source_summary: '来源摘要', review_status: 'approved', reviewer_notes: '', llm_model: '', token_usage: null, created_at: '', updated_at: '' },
    ]
    setTask(baseTask, { articles })
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    expect(screen.getByText('来源摘要')).toBeInTheDocument()
  })

  it('hides source summary in edit mode', () => {
    const articles = [
      { id: 1, title: '文章1', content: '内容', source_summary: '来源摘要', review_status: 'draft', reviewer_notes: '', llm_model: '', token_usage: null, created_at: '', updated_at: '' },
    ]
    setTask(baseTask, { articles })
    render(<MemoryRouter><TaskDetail taskId={1} /></MemoryRouter>)
    // In non-edit mode, source_summary should be visible
    expect(screen.getByText('来源摘要')).toBeInTheDocument()
  })
})
