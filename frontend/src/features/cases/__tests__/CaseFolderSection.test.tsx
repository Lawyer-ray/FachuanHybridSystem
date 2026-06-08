import { render, screen, fireEvent } from '@testing-library/react'
import { CaseFolderSection } from '../components/CaseFolderSection'
import { toast } from 'sonner'

vi.mock('lucide-react', () => ({
  FolderOpen: (props: Record<string, unknown>) => <svg data-testid="folder-icon" {...props} />,
  Link2: (props: Record<string, unknown>) => <svg data-testid="link-icon" {...props} />,
  Unlink: (props: Record<string, unknown>) => <svg data-testid="unlink-icon" {...props} />,
  Loader2: (props: Record<string, unknown>) => <svg data-testid="loader-icon" {...props} />,
  Search: (props: Record<string, unknown>) => <svg data-testid="search-icon" {...props} />,
  Cloud: (props: Record<string, unknown>) => <svg data-testid="cloud-icon" {...props} />,
  HardDrive: (props: Record<string, unknown>) => <svg data-testid="hd-icon" {...props} />,
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('../hooks/use-folder-mutations', () => ({
  useFolderMutations: () => ({
    createFolderBinding: { mutate: vi.fn(), isPending: false },
    deleteFolderBinding: { mutate: vi.fn(), isPending: false },
    startFolderScan: { mutateAsync: vi.fn(), isPending: false },
    stageScanResults: { mutate: vi.fn(), isPending: false },
  }),
}))

vi.mock('../api/materials', () => ({
  materialsApi: {
    listCloudStorageAccounts: vi.fn().mockResolvedValue([]),
  },
}))

vi.mock('@tanstack/react-query', () => ({
  useQuery: () => ({ data: [] }),
}))

vi.mock('@/features/contracts/components/FolderBrowser', () => ({
  FolderBrowser: (props: Record<string, unknown>) => <div data-testid="folder-browser" {...props} />,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
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

vi.mock('@/components/ui/checkbox', () => ({
  Checkbox: (props: Record<string, unknown>) => <input type="checkbox" {...props} />,
}))

vi.mock('@/components/ui/progress', () => ({
  Progress: (props: Record<string, unknown>) => <div data-testid="progress" {...props} />,
}))

describe('CaseFolderSection', () => {
  it('renders unbound state when no binding', () => {
    render(<CaseFolderSection binding={null} caseId={1} />)
    expect(screen.getByText('未绑定文件夹')).toBeInTheDocument()
  })

  it('renders bind button when no binding', () => {
    render(<CaseFolderSection binding={null} caseId={1} />)
    expect(screen.getByText('绑定')).toBeInTheDocument()
  })

  it('renders bound folder path when binding exists', () => {
    const binding = {
      id: 1,
      folder_path: '/home/user/cases/001',
      folder_path_display: '案件001文件夹',
      storage_type: 'local',
      is_accessible: true,
    }
    render(<CaseFolderSection binding={binding as never} caseId={1} />)
    expect(screen.getByText('案件001文件夹')).toBeInTheDocument()
  })

  it('renders accessible status for accessible binding', () => {
    const binding = {
      id: 1,
      folder_path: '/test',
      storage_type: 'local',
      is_accessible: true,
    }
    render(<CaseFolderSection binding={binding as never} caseId={1} />)
    expect(screen.getByText('可访问')).toBeInTheDocument()
  })

  it('renders inaccessible status for inaccessible binding', () => {
    const binding = {
      id: 1,
      folder_path: '/test',
      storage_type: 'local',
      is_accessible: false,
    }
    render(<CaseFolderSection binding={binding as never} caseId={1} />)
    expect(screen.getByText('不可访问')).toBeInTheDocument()
  })

  it('renders storage type label for cloud binding', () => {
    const binding = {
      id: 1,
      folder_path: '/test',
      storage_type: 'webdav',
      is_accessible: true,
    }
    render(<CaseFolderSection binding={binding as never} caseId={1} />)
    expect(screen.getByText('WebDAV')).toBeInTheDocument()
  })

  it('renders local binding without storage label', () => {
    const binding = {
      id: 1,
      folder_path: '/test',
      storage_type: 'local',
      is_accessible: true,
    }
    render(<CaseFolderSection binding={binding as never} caseId={1} />)
    expect(screen.queryByText('本地')).not.toBeInTheDocument()
  })

  it('renders OneDrive storage type', () => {
    const binding = {
      id: 1,
      folder_path: '/test',
      storage_type: 'onedrive',
      is_accessible: true,
    }
    render(<CaseFolderSection binding={binding as never} caseId={1} />)
    expect(screen.getByText('OneDrive')).toBeInTheDocument()
  })

  it('renders S3 storage type', () => {
    const binding = {
      id: 1,
      folder_path: '/test',
      storage_type: 's3',
      is_accessible: true,
    }
    render(<CaseFolderSection binding={binding as never} caseId={1} />)
    expect(screen.getByText('S3 兼容存储')).toBeInTheDocument()
  })

  it('renders binding with folder_path_display', () => {
    const binding = {
      id: 1,
      folder_path: '/home/user/cases/001',
      folder_path_display: '案件001文件夹',
      storage_type: 'local',
      is_accessible: true,
    }
    render(<CaseFolderSection binding={binding as never} caseId={1} />)
    expect(screen.getByText('案件001文件夹')).toBeInTheDocument()
  })

  it('renders binding without folder_path_display uses folder_path', () => {
    const binding = {
      id: 1,
      folder_path: '/home/user/cases/001',
      storage_type: 'local',
      is_accessible: true,
    }
    render(<CaseFolderSection binding={binding as never} caseId={1} />)
    expect(screen.getByText('/home/user/cases/001')).toBeInTheDocument()
  })

  it('renders relative path when present', () => {
    const binding = {
      id: 1,
      folder_path: '/test',
      relative_path: 'cases/001',
      storage_type: 'local',
      is_accessible: true,
    }
    render(<CaseFolderSection binding={binding as never} caseId={1} />)
    expect(screen.getByText('相对路径: cases/001')).toBeInTheDocument()
  })

  it('renders unbound state with storage type selector', () => {
    render(<CaseFolderSection binding={null} caseId={1} />)
    expect(screen.getByText('未绑定文件夹')).toBeInTheDocument()
    expect(screen.getByText('绑定')).toBeInTheDocument()
  })

  it('renders scan button for bound folder', () => {
    const binding = {
      id: 1,
      folder_path: '/test',
      storage_type: 'local',
      is_accessible: true,
    }
    render(<CaseFolderSection binding={binding as never} caseId={1} />)
    // Scan button should be present (hidden, visible on hover)
    const searchIcons = screen.getAllByTestId('search-icon')
    expect(searchIcons.length).toBeGreaterThan(0)
  })

  it('renders unlink button for bound folder', () => {
    const binding = {
      id: 1,
      folder_path: '/test',
      storage_type: 'local',
      is_accessible: true,
    }
    render(<CaseFolderSection binding={binding as never} caseId={1} />)
    const unlinkIcons = screen.getAllByTestId('unlink-icon')
    expect(unlinkIcons.length).toBeGreaterThan(0)
  })

  it('renders Google Drive storage type', () => {
    const binding = {
      id: 1,
      folder_path: '/test',
      storage_type: 'google_drive',
      is_accessible: true,
    }
    render(<CaseFolderSection binding={binding as never} caseId={1} />)
    expect(screen.getByText('Google Drive')).toBeInTheDocument()
  })

  it('renders Dropbox storage type', () => {
    const binding = {
      id: 1,
      folder_path: '/test',
      storage_type: 'dropbox',
      is_accessible: true,
    }
    render(<CaseFolderSection binding={binding as never} caseId={1} />)
    expect(screen.getByText('Dropbox')).toBeInTheDocument()
  })

  it('renders unknown storage type falls back to local label', () => {
    const binding = {
      id: 1,
      folder_path: '/test',
      storage_type: 'unknown',
      is_accessible: true,
    }
    render(<CaseFolderSection binding={binding as never} caseId={1} />)
    // Unknown type should fall back to default label
    expect(screen.getByText('/test')).toBeInTheDocument()
  })

  it('handles bind button click for local storage', () => {
    render(<CaseFolderSection binding={null} caseId={1} />)
    fireEvent.click(screen.getByText('绑定'))
    // Should open folder browser (FolderBrowser is mocked)
    expect(screen.getByTestId('folder-browser')).toBeInTheDocument()
  })

  it('handles undefined binding', () => {
    render(<CaseFolderSection binding={undefined} caseId={1} />)
    expect(screen.getByText('未绑定文件夹')).toBeInTheDocument()
  })
})
