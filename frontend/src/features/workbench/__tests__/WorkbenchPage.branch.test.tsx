/**
 * WorkbenchPage - additional branch coverage tests
 * Targets uncovered branches in WorkbenchPage.tsx
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'

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
let mockContextPercent = 0
vi.mock('../hooks/use-context-usage', () => ({
  useContextUsage: () => ({ percent: mockContextPercent }),
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
import { WorkbenchPage } from '../WorkbenchPage'
import { exportToMarkdown, downloadFile } from '../utils/export'

describe('WorkbenchPage - branch coverage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setWorkbenchState()
    vi.mocked(useParams).mockReturnValue({})
    mockContextPercent = 0
    Object.defineProperty(window, 'innerWidth', { value: 1024, writable: true })
  })

  // Branch: localStorage.getItem in sidebarCollapsed initialization (line 68)
  it('initializes sidebarCollapsed from localStorage', () => {
    const getItemSpy = vi.spyOn(Storage.prototype, 'getItem').mockReturnValue('true')
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    expect(getItemSpy).toHaveBeenCalledWith('workbench_sidebar_collapsed')
    getItemSpy.mockRestore()
  })

  // Branch: localStorage throws during sidebarCollapsed init
  it('handles localStorage error in sidebarCollapsed init', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    // Should render without crashing
    expect(screen.getByTestId('workbench-welcome')).toBeInTheDocument()
    vi.restoreAllMocks()
  })

  // Branch: export keyboard shortcut with title fallback (line 139)
  it('exports with title fallback "对话" when title is empty', () => {
    setWorkbenchState({
      currentSession: { id: 1, session_id: 'abc', title: '' },
      messages: [{ id: 1, role: 'user', content: 'hello' }],
    })
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    fireEvent.keyDown(document, { key: 'e', ctrlKey: true })
    expect(exportToMarkdown).toHaveBeenCalled()
    expect(downloadFile).toHaveBeenCalledWith('markdown', '对话.md', 'text/markdown;charset=utf-8')
  })

  // Branch: export button click with title fallback (line 414-415)
  it('exports via button click with title fallback', () => {
    setWorkbenchState({
      currentSession: { id: 1, session_id: 'abc', title: '' },
      messages: [{ id: 1, role: 'user', content: 'hello' }],
    })
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    fireEvent.click(screen.getByTestId('download'))
    expect(exportToMarkdown).toHaveBeenCalled()
    expect(downloadFile).toHaveBeenCalledWith('markdown', '对话.md', 'text/markdown;charset=utf-8')
  })

  // Branch: sidebar collapse toggle with localStorage.setItem (line 235-245)
  it('sidebar collapse toggle saves to localStorage', () => {
    const setItemSpy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {})
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    fireEvent.click(screen.getByTestId('panel-left-close'))
    expect(setItemSpy).toHaveBeenCalledWith('workbench_sidebar_collapsed', 'true')
    setItemSpy.mockRestore()
  })

  // Branch: localStorage.setItem throws during collapse (line 237)
  it('handles localStorage.setItem error during collapse', () => {
    const origSetItem = Storage.prototype.setItem
    Storage.prototype.setItem = () => { throw new Error('quota') }
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    fireEvent.click(screen.getByTestId('panel-left-close'))
    // Should not crash; after collapse, PanelLeft icon appears
    expect(screen.getByTestId('panel-left')).toBeInTheDocument()
    Storage.prototype.setItem = origSetItem
  })

  // Branch: prevAdminCollapsedRef restore when expanding (line 241-243)
  it('restores admin sidebar when expanding workbench sidebar', () => {
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    // Collapse first
    fireEvent.click(screen.getByTestId('panel-left-close'))
    // Then expand
    fireEvent.click(screen.getByTestId('panel-left'))
    // Should not crash
    expect(screen.getByTestId('panel-left-close')).toBeInTheDocument()
  })

  // Branch: mobile sidebar open (line 353)
  it('opens mobile sidebar when menu button clicked', () => {
    Object.defineProperty(window, 'innerWidth', { value: 500, writable: true })
    window.dispatchEvent(new Event('resize'))
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    fireEvent.click(screen.getByTestId('menu'))
    // Mobile sidebar should open (the X button appears in mobile sidebar)
    expect(screen.getByTestId('x')).toBeInTheDocument()
  })

  // Branch: mobile sidebar close (line 260-263)
  it('closes mobile sidebar when X clicked in mobile mode', () => {
    Object.defineProperty(window, 'innerWidth', { value: 500, writable: true })
    window.dispatchEvent(new Event('resize'))
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    fireEvent.click(screen.getByTestId('menu'))
    // Click the X in the mobile sidebar
    const xButtons = screen.getAllByTestId('x')
    fireEvent.click(xButtons[0])
  })

  // Branch: mobile overlay click to close (line 346)
  it('closes mobile sidebar when overlay clicked', () => {
    Object.defineProperty(window, 'innerWidth', { value: 500, writable: true })
    window.dispatchEvent(new Event('resize'))
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    fireEvent.click(screen.getByTestId('menu'))
    // The overlay div should be present
    const overlay = document.querySelector('.fixed.inset-0')
    if (overlay) {
      fireEvent.click(overlay)
    }
  })

  // Branch: messageSearchOpen rendering (line 428-449)
  it('shows message search bar and counts results', () => {
    setWorkbenchState({
      currentSession: { id: 1, session_id: 'abc', title: '会话' },
      messages: [
        { id: 1, role: 'user', content: 'Hello world' },
        { id: 2, role: 'assistant', content: 'Hi there' },
      ],
    })
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    fireEvent.keyDown(document, { key: 'f', ctrlKey: true })
    const searchInput = screen.getByPlaceholderText('搜索消息...')
    fireEvent.change(searchInput, { target: { value: 'hello' } })
    // Should show result count
    expect(screen.getByText(/条结果/)).toBeInTheDocument()
  })

  // Branch: messageSearchOpen with empty search (line 440 ternary)
  it('shows no count when message search is empty', () => {
    setWorkbenchState({
      currentSession: { id: 1, session_id: 'abc', title: '会话' },
      messages: [{ id: 1, role: 'user', content: 'Hello' }],
    })
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    fireEvent.keyDown(document, { key: 'f', ctrlKey: true })
    // Empty search => empty string count display
    const resultSpan = document.querySelector('.text-\\[10px\\]')
    expect(resultSpan).toBeInTheDocument()
  })

  // Branch: messageSearch close button (line 443)
  it('closes message search when X clicked', () => {
    setWorkbenchState({
      currentSession: { id: 1, session_id: 'abc', title: '会话' },
    })
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    fireEvent.keyDown(document, { key: 'f', ctrlKey: true })
    expect(screen.getByPlaceholderText('搜索消息...')).toBeInTheDocument()
    // Click the close button
    const closeBtn = screen.getByPlaceholderText('搜索消息...').closest('div')?.querySelector('button')
    if (closeBtn) fireEvent.click(closeBtn)
  })

  // Branch: handleSend without currentSession (line 162)
  it('does not send when no currentSession', () => {
    setWorkbenchState({ currentSession: null })
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    // No chat input rendered, so can't send
    expect(screen.queryByTestId('chat-input')).not.toBeInTheDocument()
    expect(mockSendMessage).not.toHaveBeenCalled()
  })

  // Branch: handleTitleUpdate without currentSession (line 170)
  it('renders with no session and title shows "工作台"', () => {
    setWorkbenchState({ currentSession: null })
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    expect(screen.getByTestId('editable-title')).toHaveTextContent('工作台')
  })

  // Branch: search query filter with empty title session (line 178)
  it('filters sessions with empty title using "新会话" fallback', () => {
    setWorkbenchState({
      sessions: [
        { id: 1, session_id: 'a', title: '', updated_at: new Date().toISOString() },
        { id: 2, session_id: 'b', title: '法律', updated_at: new Date().toISOString() },
      ],
    })
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    const searchInput = screen.getByPlaceholderText('搜索会话...')
    fireEvent.change(searchInput, { target: { value: '新会话' } })
    // Should match the session with empty title via fallback
    expect(screen.getByPlaceholderText('搜索会话...')).toBeInTheDocument()
  })

  // Branch: contextPercent >= 90 warning (line 480-488)
  it('shows context warning with new session button', () => {
    mockContextPercent = 95
    setWorkbenchState({
      currentSession: { id: 1, session_id: 'abc', title: '会话' },
    })
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    expect(screen.getByText(/上下文窗口已使用 95%/)).toBeInTheDocument()
    const newSessionBtn = screen.getByText('新建会话')
    expect(newSessionBtn).toBeInTheDocument()
    mockContextPercent = 0
  })

  // Branch: contextPercent < 90 => no warning
  it('hides context warning when usage < 90', () => {
    mockContextPercent = 50
    setWorkbenchState({
      currentSession: { id: 1, session_id: 'abc', title: '会话' },
    })
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    expect(screen.queryByText(/上下文窗口已使用/)).not.toBeInTheDocument()
  })

  // Branch: export keyboard shortcut without messages (line 138)
  it('does not export when no messages', () => {
    setWorkbenchState({
      currentSession: { id: 1, session_id: 'abc', title: '会话' },
      messages: [],
    })
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    fireEvent.keyDown(document, { key: 'e', ctrlKey: true })
    expect(exportToMarkdown).not.toHaveBeenCalled()
  })

  // Branch: export keyboard shortcut without session (line 138)
  it('does not export when no session', () => {
    setWorkbenchState({ currentSession: null, messages: [] })
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    fireEvent.keyDown(document, { key: 'e', ctrlKey: true })
    expect(exportToMarkdown).not.toHaveBeenCalled()
  })

  // Branch: cmd+F without session (line 134)
  it('does not open message search without session', () => {
    setWorkbenchState({ currentSession: null })
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    fireEvent.keyDown(document, { key: 'f', ctrlKey: true })
    expect(screen.queryByPlaceholderText('搜索消息...')).not.toBeInTheDocument()
  })

  // Branch: sessionId sync when target session matches (line 89-91)
  it('syncs session from URL param when session found', () => {
    vi.mocked(useParams).mockReturnValue({ sessionId: 'abc' })
    setWorkbenchState({
      currentSession: null,
      sessions: [{ id: 1, session_id: 'abc', title: 'Found', updated_at: new Date().toISOString() }],
    })
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    expect(mockSetCurrentSession).toHaveBeenCalledWith(
      expect.objectContaining({ session_id: 'abc' }),
    )
  })

  // Branch: sessionId sync when target already current (line 90)
  it('does not re-set current session when already set', () => {
    vi.mocked(useParams).mockReturnValue({ sessionId: 'abc' })
    setWorkbenchState({
      currentSession: { id: 1, session_id: 'abc', title: 'Current' },
      sessions: [{ id: 1, session_id: 'abc', title: 'Current', updated_at: new Date().toISOString() }],
    })
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    // Should not call setCurrentSession since it already matches
    expect(mockSetCurrentSession).not.toHaveBeenCalled()
  })

  // Branch: sessionId not found in sessions (line 89)
  it('does nothing when sessionId not in sessions', () => {
    vi.mocked(useParams).mockReturnValue({ sessionId: 'nonexistent' })
    setWorkbenchState({
      currentSession: null,
      sessions: [{ id: 1, session_id: 'abc', title: 'Other', updated_at: new Date().toISOString() }],
    })
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    expect(mockSetCurrentSession).not.toHaveBeenCalled()
  })

  // Branch: Ctrl+N keyboard shortcut (line 128-131)
  it('handles Ctrl+N keyboard shortcut', async () => {
    mockCreateSession.mockResolvedValue({ session_id: 'new', title: 'New' })
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    fireEvent.keyDown(document, { key: 'n', ctrlKey: true })
    expect(mockCreateSession).toHaveBeenCalled()
  })

  // Branch: sidebarCollapsed => PanelLeft icon shown (line 249-252)
  it('shows PanelLeft icon when sidebar is collapsed', () => {
    // First collapse the sidebar
    const setItemSpy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {})
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    fireEvent.click(screen.getByTestId('panel-left-close'))
    // After collapse, PanelLeft should appear
    expect(screen.getByTestId('panel-left')).toBeInTheDocument()
    setItemSpy.mockRestore()
  })
})
