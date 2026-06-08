import { render, screen } from '@testing-library/react'
import { FolderBindingManager } from '../components/FolderBindingManager'

vi.mock('lucide-react', () => ({
  Folder: () => <svg data-testid="folder" />,
  Link: () => <svg data-testid="link" />,
  Unlink: () => <svg data-testid="unlink" />,
  FolderOpen: () => <svg data-testid="folder-open" />,
  Cloud: () => <svg data-testid="cloud" />,
  HardDrive: () => <svg data-testid="hd" />,
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

vi.mock('../hooks/use-folder-binding', () => ({
  useFolderBinding: () => ({
    binding: { data: null },
    createBinding: { mutateAsync: vi.fn() },
    deleteBinding: { mutateAsync: vi.fn() },
  }),
  useFolderBrowse: vi.fn(() => ({
    data: { path: '/home/user', entries: [], browsable: true },
    isLoading: false,
  })),
}))

vi.mock('../api/folders', () => ({
  foldersApi: { listCloudStorageAccounts: vi.fn().mockResolvedValue([]) },
}))

vi.mock('@tanstack/react-query', () => ({
  useQuery: () => ({ data: [] }),
}))

vi.mock('../components/FolderBrowser', () => ({
  FolderBrowser: () => <div data-testid="folder-browser" />,
}))

vi.mock('../components/FolderScanPanel', () => ({
  FolderScanPanel: () => <div data-testid="folder-scan-panel" />,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
}))
vi.mock('@/components/ui/card', () => ({
  Card: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  CardContent: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  CardHeader: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  CardTitle: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
}))
vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, ...props }: Record<string, unknown>) => <span {...props}>{children}</span>,
}))
vi.mock('@/components/ui/select', () => ({
  Select: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectValue: () => <span />,
}))

describe('FolderBindingManager', () => {
  it('renders title', () => {
    render(<FolderBindingManager contractId={1} />)
    expect(screen.getByText('文件夹绑定')).toBeInTheDocument()
  })

  it('renders unbound state', () => {
    render(<FolderBindingManager contractId={1} />)
    expect(screen.getByText(/未绑定文件夹/)).toBeInTheDocument()
  })

  it('renders bind button when no binding', () => {
    render(<FolderBindingManager contractId={1} />)
    expect(screen.getByText('绑定')).toBeInTheDocument()
  })

  it('renders without crashing', () => {
    const { container } = render(<FolderBindingManager contractId={1} />)
    expect(container).toBeTruthy()
  })

})
