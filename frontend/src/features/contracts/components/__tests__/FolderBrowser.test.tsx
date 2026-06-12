import { render, screen, fireEvent } from '@testing-library/react'
import { FolderBrowser } from '../components/FolderBrowser'

vi.mock('lucide-react', () => ({
  Folder: (props: Record<string, unknown>) => <svg data-testid="folder-icon" {...props} />,
  ChevronRight: (props: Record<string, unknown>) => <svg data-testid="chevron" {...props} />,
  ArrowUp: (props: Record<string, unknown>) => <svg data-testid="arrow-up" {...props} />,
}))

vi.mock('../hooks/use-folder-binding', () => ({
  useFolderBrowse: vi.fn(() => ({
    data: { path: '/home/user', entries: [], browsable: true },
    isLoading: false,
  })),
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
}))

vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children, open }: { children: React.ReactNode; open?: boolean }) =>
    open ? <div data-testid="dialog">{children}</div> : null,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/ui/skeleton', () => ({
  Skeleton: (props: Record<string, unknown>) => <div data-testid="skeleton" {...props} />,
}))

import { useFolderBrowse } from '../hooks/use-folder-binding'
const mockUseFolderBrowse = vi.mocked(useFolderBrowse)

describe('FolderBrowser', () => {
  beforeEach(() => {
    mockUseFolderBrowse.mockReturnValue({
      data: { path: '/home/user', entries: [], browsable: true },
      isLoading: false,
    } as never)
  })

  it('renders dialog when open', () => {
    render(<FolderBrowser open={true} onOpenChange={vi.fn()} onSelect={vi.fn()} />)
    expect(screen.getByText('选择文件夹')).toBeInTheDocument()
  })

  it('does not render content when closed', () => {
    render(<FolderBrowser open={false} onOpenChange={vi.fn()} onSelect={vi.fn()} />)
    expect(screen.queryByText('选择文件夹')).not.toBeInTheDocument()
  })

  it('renders cloud title for cloud storage', () => {
    render(<FolderBrowser open={true} onOpenChange={vi.fn()} onSelect={vi.fn()} storageType="webdav" />)
    expect(screen.getByText('选择云存储文件夹')).toBeInTheDocument()
  })

  it('renders folder entries', () => {
    mockUseFolderBrowse.mockReturnValue({
      data: {
        path: '/home/user',
        entries: [
          { path: '/home/user/docs', name: 'docs' },
          { path: '/home/user/images', name: 'images' },
        ],
        browsable: true,
      },
      isLoading: false,
    } as never)
    render(<FolderBrowser open={true} onOpenChange={vi.fn()} onSelect={vi.fn()} />)
    expect(screen.getByText('docs')).toBeInTheDocument()
    expect(screen.getByText('images')).toBeInTheDocument()
  })

  it('renders loading skeletons when loading', () => {
    mockUseFolderBrowse.mockReturnValue({ data: null, isLoading: true } as never)
    render(<FolderBrowser open={true} onOpenChange={vi.fn()} onSelect={vi.fn()} />)
    expect(screen.getAllByTestId('skeleton').length).toBeGreaterThan(0)
  })

  it('renders empty folder message', () => {
    mockUseFolderBrowse.mockReturnValue({
      data: { path: '/empty', entries: [], browsable: true },
      isLoading: false,
    } as never)
    render(<FolderBrowser open={true} onOpenChange={vi.fn()} onSelect={vi.fn()} />)
    expect(screen.getByText('空文件夹')).toBeInTheDocument()
  })

  it('renders non-browsable message', () => {
    mockUseFolderBrowse.mockReturnValue({
      data: { path: '/restricted', entries: [], browsable: false, message: '无权限访问' },
      isLoading: false,
    } as never)
    render(<FolderBrowser open={true} onOpenChange={vi.fn()} onSelect={vi.fn()} />)
    expect(screen.getByText('无权限访问')).toBeInTheDocument()
  })
})
