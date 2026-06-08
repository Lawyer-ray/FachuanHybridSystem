/**
 * BatchDownloadButton Component Tests
 * 测试批量分析下载按钮
 */

vi.mock('@/lib/utils', () => ({
  cn: (...args: (string | undefined | false | null)[]) => args.filter(Boolean).join(' '),
}))

vi.mock('@/lib/api', () => ({
  API_BASE_URL: 'http://localhost:8000/api',
}))

vi.mock('@/lib/token', () => ({
  getAccessToken: () => 'test-token',
}))

vi.mock('@/lib/download', () => ({
  downloadBlob: vi.fn(),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children, open }: { children: React.ReactNode; open: boolean }) =>
    open ? <div data-testid="alert-dialog">{children}</div> : null,
  AlertDialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogCancel: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, variant }: { children: React.ReactNode; onClick?: () => void; variant?: string }) => (
    <button onClick={onClick}>{children}</button>
  ),
}))

import { render, screen, fireEvent } from '@testing-library/react'
import { BatchDownloadButton } from '../BatchDownloadButton'

describe('BatchDownloadButton', () => {
  it('renders CSV and ZIP download buttons', () => {
    render(<BatchDownloadButton jobId="abc12345-xxxx" />)
    expect(screen.getByText('下载汇总 CSV')).toBeInTheDocument()
    expect(screen.getByText('下载分析详情 ZIP')).toBeInTheDocument()
  })

  it('opens CSV download dialog when clicking CSV button', () => {
    render(<BatchDownloadButton jobId="abc12345-xxxx" />)
    fireEvent.click(screen.getByText('下载汇总 CSV'))
    expect(screen.getByText('下载汇总 CSV', { selector: 'h2' })).toBeInTheDocument()
    expect(screen.getByText('仅相关案例')).toBeInTheDocument()
    expect(screen.getByText('全部案例')).toBeInTheDocument()
  })

  it('opens ZIP download dialog when clicking ZIP button', () => {
    render(<BatchDownloadButton jobId="abc12345-xxxx" />)
    fireEvent.click(screen.getByText('下载分析详情 ZIP'))
    expect(screen.getByText('下载分析详情 ZIP', { selector: 'h2' })).toBeInTheDocument()
  })

  it('shows description text in download dialog', () => {
    render(<BatchDownloadButton jobId="abc12345-xxxx" />)
    fireEvent.click(screen.getByText('下载汇总 CSV'))
    expect(screen.getByText(/选择下载范围/)).toBeInTheDocument()
  })

  it('has cancel button in download dialog', () => {
    render(<BatchDownloadButton jobId="abc12345-xxxx" />)
    fireEvent.click(screen.getByText('下载汇总 CSV'))
    expect(screen.getByText('取消')).toBeInTheDocument()
  })
})
