import { render, screen } from '@testing-library/react'
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

vi.mock('../stores/workbench-store', () => ({
  useWorkbenchStore: vi.fn((selector?: (s: Record<string, unknown>) => unknown) => {
    const state = {
      sessions: [],
      currentSession: null,
      fetchSessions: vi.fn(),
      createSession: vi.fn(),
      setCurrentSession: vi.fn(),
      fetchModels: vi.fn(),
      pendingApproval: null,
      respondApproval: vi.fn(),
      isStreaming: false,
      sendMessage: vi.fn(),
      selectedModel: null,
      models: [],
      batchProgress: null,
      submitBatchAnalysis: vi.fn(),
      cancelBatchAnalysis: vi.fn(),
      dismissBatchProgress: vi.fn(),
      recoverActiveBatchJob: vi.fn(),
      messages: [],
      abortStream: vi.fn(),
    }
    return selector ? selector(state) : state
  }),
}))

vi.mock('../components/MessageList', () => ({
  MessageList: () => <div data-testid="message-list" />,
}))
vi.mock('../components/ChatInput', () => ({
  ChatInput: () => <div data-testid="chat-input" />,
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
  WorkbenchWelcome: () => <div data-testid="workbench-welcome" />,
}))
vi.mock('../components/WorkbenchCommandPalette', () => ({
  WorkbenchCommandPalette: () => <div data-testid="command-palette" />,
}))
vi.mock('../components/SessionItem', () => ({
  SessionItem: () => <div data-testid="session-item" />,
}))
vi.mock('../components/EditableTitle', () => ({
  EditableTitle: () => <div data-testid="editable-title" />,
}))
vi.mock('../hooks/use-context-usage', () => ({
  useContextUsage: () => ({ percent: 0 }),
}))
vi.mock('../api', () => ({
  deleteSession: vi.fn(),
  updateSession: vi.fn(),
}))
vi.mock('../utils/export', () => ({
  exportToMarkdown: vi.fn(),
  downloadFile: vi.fn(),
}))
vi.mock('@/routes/paths', () => ({
  generatePath: { workbench: (id: string) => `/admin/workbench/${id}` },
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

describe('WorkbenchPage', () => {
  it('renders the page', () => {
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    expect(screen.getByTestId('workbench-welcome')).toBeInTheDocument()
  })



  it('renders model selector', () => {
    render(<MemoryRouter><WorkbenchPage /></MemoryRouter>)
    expect(screen.getByTestId('model-selector')).toBeInTheDocument()
  })

})
