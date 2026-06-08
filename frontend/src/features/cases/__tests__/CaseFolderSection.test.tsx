import { render, screen } from '@testing-library/react'
import { CaseFolderSection } from '../components/CaseFolderSection'

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
})
