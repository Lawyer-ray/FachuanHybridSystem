import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { WorkbenchPage } from '../WorkbenchPage'

vi.mock('lucide-react', () => ({
  Plus: () => <svg data-testid="plus" />,
  Loader2: () => <svg data-testid="loader" />,
  Search: () => <svg data-testid="search" />,
  X: () => <svg data-testid="x" />,
  PanelLeftClose: () => <svg data-testid="panel-left-close" />,
  PanelLeft: () => <svg data-testid="panel-left" />,
  Menu: () => <svg data-testid="menu" />,
  History: () => <svg data-testid="history" />,
  Download: () => <svg data-testid="download" />,
  AlertTriangle: () => <svg data-testid="alert-triangle" />,
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

vi.mock('@/stores/ui', () => ({
  useUIStore: vi.fn((selector?: (s: Record<string, unknown>) => unknown) => {
    const state = { sidebarCollapsed: false, setSidebarCollapsed: vi.fn() }
    return selector ? selector(state) : state
  }),
}))

const mockFetchSessions = vi.fn()
const mockCreateSession = vi.fn()
const mockSetCurrentSession = vi.fn()
const mockFetchModels = vi.fn()
const mockSendMessage = vi.fn()
const mockAbortStream = vi.fn()
const mockSubmitBatch = vi.fn()
const mockCancelBatch = vi.fn()
const mockDismissBatch = vi.fn()
const mockRecoverBatch = vi.fn()
const mockRespondApproval = vi.fn()

let workbenchState: Record<string, unknown> = {}

function setWorkbenchState(overrides: Record<string, unknown> = {}) {
  workbenchState = {
    sessions: [],
    currentSession: null,
    fetchSessions: mockFetchSessions,
    createSession: mockCreateSession,
    setCurrentSession: mockSetCurrentSession,
    fetchModels: mockFetchModels,
    pendingApproval: null,
    respondApproval: mockRespondApproval,
    isStreaming: false,
    sendMessage: mockSendMessage,
    selectedModel: null,
    models: [],
    batchProgress: null,
    submitBatchAnalysis: mockSubmitBatch,
    cancelBatchAnalysis: mockCancelBatch,
    dismissBatchProgress: mockDismissBatch,
    recoverActiveBatchJob: mockRecoverBatch,
    messages: [],
    abortStream: mockAbortStream,
    ...overrides,
  }
}

vi.mock('../stores/workbench-store', () => ({
  useWorkbenchStore: vi.fn((selector?: (s: Record<string, unknown>) => unknown) => {
    return selector ? selector(workbenchState) : workbenchState
  }),
}))

vi.mock('../components/MessageList', () => ({
  MessageList: () => <div data-testid="message-list" />,
}))
vi.mock('../components/ChatInput', () => ({
  ChatInput: ({ onSend }: { onSend?: (text: string) => void }) => (
    <div data-testid="chat-input">
      <button onClick={() => onSend?.('test message')}>send</button>
    </div>
  ),
}))
vi.mock('../components/ModelSelector', () => ({
  ModelSelector: () => <div data-testid="model-selector" />,
}))
vi.mock('../components/ContextUsageBar', () => ({
  ContextUsageBar: () => <div data-testid="context-usage-bar" />,
}))
vi.mock('../components/ApprovalDialog', () => ({
  ApprovalDialog: () => <div data-testid="approval-dialog" />,
}))
vi.mock('../components/BatchAnalysisDialog', () => ({
  BatchAnalysisDialog: () => <div data-testid="batch-dialog" />,
}))
vi.mock('../components/BatchProgressCard', () => ({
  BatchProgressCard: () => <div data-testid="batch-progress" />,
}))
vi.mock('../components/BatchHistoryPanel', () => ({
  BatchHistoryPanel: () => <div data-testid="batch-history" />,
}))
vi.mock('../components/WorkbenchWelcome', () => ({
  WorkbenchWelcome: ({ onCreateSession }: { onCreateSession?: () => void }) => (
    <div data-testid="workbench-welcome">
      <button onClick={onCreateSession}>create-session</button>
    </div>
  ),
}))
vi.mock('../components/WorkbenchCommandPalette', () => ({
  WorkbenchCommandPalette: () => <div data-testid="command-palette" />,
}))
vi.mock('../components/SessionItem', () => ({
  SessionItem: ({ session, onSelect, onDelete }: Record<string, unknown>) => (
    <div data-testid="session-item">
      <span>{(session as Record<string, unknown>).title as string}</span>
      <button onClick={onSelect as React.MouseEventHandler}>select</button>
      <button onClick={onDelete as React.MouseEventHandler}>delete</button>
    </div>
  ),
}))
vi.mock('../components/EditableTitle', () => ({
  EditableTitle: ({ title }: { title: string }) => <div data-testid="editable-title">{title}</div>,
}))
vi.mock('../hooks/use-context-usage', () => ({
  useContextUsage: () => ({ percent: 0 }),
}))
vi.mock('../api', () => ({
  deleteSession: vi.fn().mockResolvedValue(undefined),
  updateSession: vi.fn().mockResolvedValue(undefined),
}))
vi.mock('../utils/export', () => ({
  exportToMarkdown: vi.fn(() => 'markdown'),
  downloadFile: vi.fn(),
}))
vi.mock('@/routes/paths', () => ({
  generatePath: {
    workbench: (id: string) => `/admin/workbench/${id}`,
    workbenchSession: (id: string) => `/admin/workbench/${id}`,
  },
}))

vi.mock('@/lib/utils', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
}))
vi.mock('@/components/ui/input', () => ({
  Input: (props: Record<string, unknown>) => <input {...props} />,
}))
vi.mock('@/components/ui/sheet', () => ({
  Sheet: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SheetContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SheetHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SheetTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SheetDescription: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('react-router', async () => {
  const actual = await vi.importActual<typeof import('react-router')>('react-router')
  return {
    ...actual,
    useParams: vi.fn(() => ({})),
    useNavigate: vi.fn(() => vi.fn()),
  }
})

import { useParams } from 'react-router'

describe('WorkbenchPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setWorkbenchState()
    vi.mocked(useParams).mockReturnValue({})
  })

  it('renders the page with welcome', () => {
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    expect(screen.getByTestId('workbench-welcome')).toBeInTheDocument()
  })

  it('renders model selector', () => {
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    expect(screen.getByTestId('model-selector')).toBeInTheDocument()
  })

  it('renders editable title', () => {
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    expect(screen.getByTestId('editable-title')).toHaveTextContent('工作台')
  })

  it('renders session list header', () => {
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    expect(screen.getByText('会话')).toBeInTheDocument()
  })

  it('renders empty session message', () => {
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    expect(screen.getByText('暂无会话')).toBeInTheDocument()
  })

  it('renders sessions when available', () => {
    setWorkbenchState({
      sessions: [
        { id: 1, session_id: 'abc', title: '会话1', updated_at: new Date().toISOString() },
        { id: 2, session_id: 'def', title: '会话2', updated_at: new Date().toISOString() },
      ],
    })
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    expect(screen.getByText('会话1')).toBeInTheDocument()
    expect(screen.getByText('会话2')).toBeInTheDocument()
  })

  it('renders current session with message list and chat input', () => {
    setWorkbenchState({
      currentSession: { id: 1, session_id: 'abc', title: '当前会话' },
      sessions: [{ id: 1, session_id: 'abc', title: '当前会话', updated_at: new Date().toISOString() }],
    })
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    expect(screen.getByTestId('message-list')).toBeInTheDocument()
    expect(screen.getByTestId('chat-input')).toBeInTheDocument()
    expect(screen.getByTestId('context-usage-bar')).toBeInTheDocument()
  })

  it('renders batch analysis dialog when session active', () => {
    setWorkbenchState({
      currentSession: { id: 1, session_id: 'abc', title: '当前会话' },
      sessions: [{ id: 1, session_id: 'abc', title: '当前会话', updated_at: new Date().toISOString() }],
    })
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    expect(screen.getByTestId('batch-dialog')).toBeInTheDocument()
  })

  it('renders title from current session', () => {
    setWorkbenchState({
      currentSession: { id: 1, session_id: 'abc', title: '我的会话' },
    })
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    expect(screen.getByTestId('editable-title')).toHaveTextContent('我的会话')
  })

  it('renders sidebar with search input', () => {
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    expect(screen.getByPlaceholderText('搜索会话...')).toBeInTheDocument()
  })

  it('renders new session button', () => {
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    expect(screen.getByTestId('plus')).toBeInTheDocument()
  })

  it('renders sidebar collapse toggle', () => {
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    expect(screen.getByTestId('panel-left-close')).toBeInTheDocument()
  })

  it('renders approval dialog when pending approval', () => {
    setWorkbenchState({
      currentSession: { id: 1, session_id: 'abc', title: '会话' },
      pendingApproval: { id: 1, type: 'tool_call' },
    })
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    expect(screen.getByTestId('approval-dialog')).toBeInTheDocument()
  })

  it('renders batch progress when available', () => {
    setWorkbenchState({
      currentSession: { id: 1, session_id: 'abc', title: '会话' },
      batchProgress: {
        job: { id: 'job1', status: 'running', progress: 50 },
        items: [],
        failed_items_detail: [],
      },
    })
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    expect(screen.getByTestId('batch-progress')).toBeInTheDocument()
  })

  it('renders history button when session active', () => {
    setWorkbenchState({
      currentSession: { id: 1, session_id: 'abc', title: '会话' },
    })
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    expect(screen.getByTestId('history')).toBeInTheDocument()
  })

  it('renders download button when messages exist', () => {
    setWorkbenchState({
      currentSession: { id: 1, session_id: 'abc', title: '会话' },
      messages: [{ id: 1, role: 'user', content: 'hello' }],
    })
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    expect(screen.getByTestId('download')).toBeInTheDocument()
  })

  it('renders no match message when search has no results', () => {
    setWorkbenchState({
      sessions: [
        { id: 1, session_id: 'abc', title: '测试会话', updated_at: new Date().toISOString() },
      ],
    })
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    const searchInput = screen.getByPlaceholderText('搜索会话...')
    fireEvent.change(searchInput, { target: { value: 'nonexistent' } })
    expect(screen.getByText('无匹配会话')).toBeInTheDocument()
  })

  it('filters sessions by search query', () => {
    setWorkbenchState({
      sessions: [
        { id: 1, session_id: 'abc', title: '法律分析', updated_at: new Date().toISOString() },
        { id: 2, session_id: 'def', title: '合同审查', updated_at: new Date().toISOString() },
      ],
    })
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    const searchInput = screen.getByPlaceholderText('搜索会话...')
    fireEvent.change(searchInput, { target: { value: '法律' } })
    expect(screen.getByText('法律分析')).toBeInTheDocument()
    expect(screen.queryByText('合同审查')).not.toBeInTheDocument()
  })

  it('renders session groups (today, yesterday, etc)', () => {
    const now = new Date()
    const yesterday = new Date(now.getTime() - 86400000)
    const weekAgo = new Date(now.getTime() - 6 * 86400000)
    const monthAgo = new Date(now.getTime() - 30 * 86400000)

    setWorkbenchState({
      sessions: [
        { id: 1, session_id: 'a', title: '今日任务', updated_at: now.toISOString() },
        { id: 2, session_id: 'b', title: '昨日任务', updated_at: yesterday.toISOString() },
        { id: 3, session_id: 'c', title: '本周任务', updated_at: weekAgo.toISOString() },
        { id: 4, session_id: 'd', title: '更早任务', updated_at: monthAgo.toISOString() },
      ],
    })
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    expect(screen.getByText('今日任务')).toBeInTheDocument()
    expect(screen.getByText('昨日任务')).toBeInTheDocument()
    expect(screen.getByText('本周任务')).toBeInTheDocument()
    expect(screen.getByText('更早任务')).toBeInTheDocument()
    // Group labels
    expect(screen.getByText('今天')).toBeInTheDocument()
    expect(screen.getByText('昨天')).toBeInTheDocument()
    expect(screen.getByText('本周')).toBeInTheDocument()
    expect(screen.getByText('更早')).toBeInTheDocument()
  })

  it('renders command palette component', () => {
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    expect(screen.getByTestId('command-palette')).toBeInTheDocument()
  })

  it('handles new session button click', async () => {
    mockCreateSession.mockResolvedValue({ session_id: 'new123', title: '新会话' })
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    fireEvent.click(screen.getByTestId('plus'))
    expect(mockCreateSession).toHaveBeenCalled()
  })

  it('renders with sessionId param', () => {
    vi.mocked(useParams).mockReturnValue({ sessionId: 'abc' })
    setWorkbenchState({
      currentSession: { id: 1, session_id: 'abc', title: '已选会话' },
      sessions: [{ id: 1, session_id: 'abc', title: '已选会话', updated_at: new Date().toISOString() }],
    })
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    expect(screen.getByTestId('message-list')).toBeInTheDocument()
  })

  it('renders new session button with loading state', () => {
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    // The plus icon should be visible
    expect(screen.getByTestId('plus')).toBeInTheDocument()
  })

  it('handles sessions with empty title', () => {
    setWorkbenchState({
      sessions: [
        { id: 1, session_id: 'abc', title: '', updated_at: new Date().toISOString() },
      ],
    })
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    // Session item shows empty title (the mock just shows the title string)
    expect(screen.getByTestId('session-item')).toBeInTheDocument()
  })
})
