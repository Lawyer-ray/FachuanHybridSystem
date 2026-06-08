import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'

// Mock all heavy dependencies so the real WorkbenchPage renders
vi.mock('lucide-react', () => {
  const icons = ['Plus', 'Loader2', 'Search', 'X', 'PanelLeftClose', 'PanelLeft', 'Menu', 'History', 'Download', 'AlertTriangle']
  const mocks: Record<string, React.FC<Record<string, unknown>>> = {}
  for (const name of icons) {
    mocks[name] = (props) => <svg data-testid={`${name.toLowerCase()}-icon`} {...props} />
  }
  return mocks
})

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
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

vi.mock('@/lib/utils', () => ({
  cn: (...args: (string | undefined | false | null)[]) => args.filter(Boolean).join(' '),
}))

vi.mock('@/stores/ui', () => ({
  useUIStore: (sel: (s: Record<string, unknown>) => unknown) => sel({ sidebarCollapsed: false, setSidebarCollapsed: vi.fn() }),
}))

const mockStore: Record<string, unknown> = {
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
  selectedModel: 'gpt-4',
  models: [],
  batchProgress: null,
  submitBatchAnalysis: vi.fn(),
  cancelBatchAnalysis: vi.fn(),
  dismissBatchProgress: vi.fn(),
  recoverActiveBatchJob: vi.fn(),
  messages: [],
  abortStream: vi.fn(),
}

vi.mock('@/features/workbench/stores/workbench-store', () => ({
  useWorkbenchStore: (sel: (s: Record<string, unknown>) => unknown) => sel(mockStore),
}))

vi.mock('@/features/workbench/components/MessageList', () => ({
  MessageList: () => <div data-testid="message-list" />,
}))

vi.mock('@/features/workbench/components/ChatInput', () => ({
  ChatInput: (props: Record<string, unknown>) => <div data-testid="chat-input" />,
}))

vi.mock('@/features/workbench/components/ModelSelector', () => ({
  ModelSelector: (props: Record<string, unknown>) => <div data-testid="model-selector" />,
}))

vi.mock('@/features/workbench/components/ContextUsageBar', () => ({
  ContextUsageBar: () => <div data-testid="context-usage-bar" />,
}))

vi.mock('@/features/workbench/components/ApprovalDialog', () => ({
  ApprovalDialog: () => <div data-testid="approval-dialog" />,
}))

vi.mock('@/features/workbench/components/BatchAnalysisDialog', () => ({
  BatchAnalysisDialog: () => <div data-testid="batch-analysis-dialog" />,
}))

vi.mock('@/features/workbench/components/BatchProgressCard', () => ({
  BatchProgressCard: () => <div data-testid="batch-progress-card" />,
}))

vi.mock('@/features/workbench/components/BatchHistoryPanel', () => ({
  BatchHistoryPanel: () => <div data-testid="batch-history-panel" />,
}))

vi.mock('@/features/workbench/components/WorkbenchWelcome', () => ({
  WorkbenchWelcome: () => <div data-testid="workbench-welcome" />,
}))

vi.mock('@/features/workbench/components/WorkbenchCommandPalette', () => ({
  WorkbenchCommandPalette: () => <div data-testid="command-palette" />,
}))

vi.mock('@/features/workbench/components/SessionItem', () => ({
  SessionItem: () => <div data-testid="session-item" />,
}))

vi.mock('@/features/workbench/components/EditableTitle', () => ({
  EditableTitle: ({ title }: { title: string }) => <div data-testid="editable-title">{title}</div>,
}))

vi.mock('@/features/workbench/hooks/use-context-usage', () => ({
  useContextUsage: () => ({ percent: 30 }),
}))

vi.mock('@/features/workbench/api', () => ({
  deleteSession: vi.fn(),
  updateSession: vi.fn(),
}))

vi.mock('@/features/workbench/utils/export', () => ({
  exportToMarkdown: vi.fn(() => 'mock md'),
  downloadFile: vi.fn(),
}))

vi.mock('@/routes/paths', () => ({
  generatePath: {
    workbenchSession: (id: string) => `/admin/workbench/${id}`,
  },
}))

// Import AFTER mocks so the real WorkbenchPage module executes (covers the re-export line)
import WorkbenchPage from '../WorkbenchPage'

describe('WorkbenchPage (re-export)', () => {
  it('renders the real WorkbenchPage through the re-export', () => {
    render(
      <MemoryRouter>
        <WorkbenchPage />
      </MemoryRouter>,
    )
    expect(screen.getByTestId('editable-title')).toHaveTextContent('工作台')
  })

  it('renders welcome screen when no current session', () => {
    render(
      <MemoryRouter>
        <WorkbenchPage />
      </MemoryRouter>,
    )
    expect(screen.getByTestId('workbench-welcome')).toBeInTheDocument()
  })

  it('renders model selector', () => {
    render(
      <MemoryRouter>
        <WorkbenchPage />
      </MemoryRouter>,
    )
    expect(screen.getByTestId('model-selector')).toBeInTheDocument()
  })
})
