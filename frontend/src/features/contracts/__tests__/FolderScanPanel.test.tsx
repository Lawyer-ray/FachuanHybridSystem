import { render, screen } from '@testing-library/react'
import { FolderScanPanel } from '../components/FolderScanPanel'

vi.mock('lucide-react', () => ({
  Play: (props: Record<string, unknown>) => <svg data-testid="play-icon" {...props} />,
  RefreshCw: (props: Record<string, unknown>) => <svg data-testid="refresh-icon" {...props} />,
  Check: (props: Record<string, unknown>) => <svg data-testid="check-icon" {...props} />,
  X: (props: Record<string, unknown>) => <svg data-testid="x-icon" {...props} />,
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('../hooks/use-folder-scan', () => ({
  useFolderScan: () => ({
    subfolders: { data: null },
    startScan: { mutateAsync: vi.fn(), isPending: false },
    confirmScan: { mutateAsync: vi.fn(), isPending: false },
  }),
  useScanStatus: () => ({ data: null }),
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

vi.mock('@/components/ui/progress', () => ({
  Progress: (props: Record<string, unknown>) => <div data-testid="progress" {...props} />,
}))

vi.mock('@/components/ui/select', () => ({
  Select: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectValue: () => <span />,
}))

describe('FolderScanPanel', () => {
  it('renders card title', () => {
    render(<FolderScanPanel contractId={1} />)
    expect(screen.getByText('文件夹扫描')).toBeInTheDocument()
  })

  it('renders start scan button', () => {
    render(<FolderScanPanel contractId={1} />)
    expect(screen.getByText('开始扫描')).toBeInTheDocument()
  })

  it('renders rescan button', () => {
    render(<FolderScanPanel contractId={1} />)
    expect(screen.getByText('重新扫描')).toBeInTheDocument()
  })

  it('renders both buttons as enabled initially', () => {
    render(<FolderScanPanel contractId={1} />)
    const startBtn = screen.getByText('开始扫描')
    const rescanBtn = screen.getByText('重新扫描')
    expect(startBtn).not.toBeDisabled()
    expect(rescanBtn).not.toBeDisabled()
  })

})
