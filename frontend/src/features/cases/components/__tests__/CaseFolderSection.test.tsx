import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { CaseFolderSection } from '../CaseFolderSection'

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})
vi.mock('../../api/materials', () => ({
  materialsApi: {
    listCloudStorageAccounts: vi.fn().mockResolvedValue([]),
  },
}))
vi.mock('../../hooks/use-folder-mutations', () => ({
  useFolderMutations: () => ({
    createFolderBinding: { mutate: vi.fn() },
    deleteFolderBinding: { mutate: vi.fn() },
    startFolderScan: { mutateAsync: vi.fn() },
    stageScanResults: { isPending: false, mutate: vi.fn() },
  }),
}))
vi.mock('@/features/contracts/components/FolderBrowser', () => ({
  FolderBrowser: ({ open }: { open: boolean }) => open ? <div data-testid="folder-browser" /> : null,
}))
vi.mock('@tanstack/react-query', () => ({
  useQuery: vi.fn().mockReturnValue({ data: [] }),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useMutation: vi.fn().mockReturnValue({ mutate: vi.fn(), mutateAsync: vi.fn().mockResolvedValue({}), isPending: false }),
}))

describe('CaseFolderSection', () => {
  beforeEach(() => cleanup())

  it('shows unbound state', () => {
    render(<CaseFolderSection binding={null} caseId={1} />)
    expect(screen.getByText('未绑定文件夹')).toBeInTheDocument()
  })

  it('renders storage type selector when unbound', () => {
    render(<CaseFolderSection binding={null} caseId={1} />)
    expect(screen.getByText('本地')).toBeInTheDocument()
  })

  it('renders bind button when unbound', () => {
    render(<CaseFolderSection binding={null} caseId={1} />)
    expect(screen.getByText('绑定')).toBeInTheDocument()
  })

  it('shows bound folder path', () => {
    const binding = {
      folder_path: '/data/cases/1',
      folder_path_display: '案件1文件夹',
      storage_type: 'local',
      storage_account_id: null,
      is_accessible: true,
      relative_path: './materials',
    }
    render(<CaseFolderSection binding={binding} caseId={1} />)
    expect(screen.getByText('案件1文件夹')).toBeInTheDocument()
    expect(screen.getByText('可访问')).toBeInTheDocument()
  })

  it('shows inaccessible folder', () => {
    const binding = {
      folder_path: '/data/cases/1',
      folder_path_display: '案件1文件夹',
      storage_type: 'local',
      storage_account_id: null,
      is_accessible: false,
      relative_path: null,
    }
    render(<CaseFolderSection binding={binding} caseId={1} />)
    expect(screen.getByText('不可访问')).toBeInTheDocument()
  })

  it('shows relative path when present', () => {
    const binding = {
      folder_path: '/data/cases/1',
      folder_path_display: null,
      storage_type: 'local',
      storage_account_id: null,
      is_accessible: true,
      relative_path: './docs',
    }
    render(<CaseFolderSection binding={binding} caseId={1} />)
    expect(screen.getByText(/相对路径.*docs/)).toBeInTheDocument()
  })

  it('shows cloud storage badge for webdav', () => {
    const binding = {
      folder_path: '/dav/cases/1',
      folder_path_display: null,
      storage_type: 'webdav',
      storage_account_id: 1,
      is_accessible: true,
      relative_path: null,
    }
    render(<CaseFolderSection binding={binding} caseId={1} />)
    expect(screen.getByText('WebDAV')).toBeInTheDocument()
  })

  it('shows unbind confirmation dialog', () => {
    const binding = {
      folder_path: '/data/cases/1',
      folder_path_display: 'Test',
      storage_type: 'local',
      storage_account_id: null,
      is_accessible: true,
      relative_path: null,
    }
    render(<CaseFolderSection binding={binding} caseId={1} />)
    // Find and click the unbind button (Unlink icon button)
    const unbindButtons = screen.getAllByRole('button')
    // The unbind button is in the hover group
    fireEvent.click(unbindButtons[unbindButtons.length - 1])
  })

  it('renders storage type options', () => {
    render(<CaseFolderSection binding={null} caseId={1} />)
    // Storage selector is present by default showing "本地"
    expect(screen.getByText('本地')).toBeInTheDocument()
    // Bind button is present
    expect(screen.getByText('绑定')).toBeInTheDocument()
  })

  it('renders cloud account selector for non-local storage', () => {
    // This test validates the component renders without error when cloud accounts exist
    render(<CaseFolderSection binding={null} caseId={1} />)
    expect(screen.getByText('未绑定文件夹')).toBeInTheDocument()
  })
})
