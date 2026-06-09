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
  getAccessToken: vi.fn(() => 'test-token'),
}))

vi.mock('@/lib/download', () => ({
  downloadBlob: vi.fn(),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children, open, onOpenChange }: { children: React.ReactNode; open: boolean; onOpenChange?: (open: boolean) => void }) =>
    open ? <div data-testid="alert-dialog" onClick={() => onOpenChange?.(false)}>{children}</div> : null,
  AlertDialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogCancel: ({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) => <button onClick={onClick}>{children}</button>,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, variant }: { children: React.ReactNode; onClick?: () => void; variant?: string }) => (
    <button onClick={onClick}>{children}</button>
  ),
}))

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { BatchDownloadButton } from '../BatchDownloadButton'
import { downloadBlob } from '@/lib/download'
import { toast } from 'sonner'

describe('BatchDownloadButton', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    vi.clearAllMocks()
    fetchSpy = vi.spyOn(globalThis, 'fetch')
  })

  afterEach(() => {
    fetchSpy.mockRestore()
  })

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

  // --- Download execution tests ---

  it('downloads CSV with all cases when clicking 全部案例', async () => {
    const mockBlob = new Blob(['csv-data'], { type: 'text/csv' })
    fetchSpy.mockResolvedValue({
      ok: true,
      blob: () => Promise.resolve(mockBlob),
    } as Response)

    render(<BatchDownloadButton jobId="abc12345-xxxx" />)
    fireEvent.click(screen.getByText('下载汇总 CSV'))
    fireEvent.click(screen.getByText('全部案例'))

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        'http://localhost:8000/api/workbench/batch/abc12345-xxxx/download?',
        expect.objectContaining({
          headers: { Authorization: 'Bearer ' + 'test-token' }, // 测试
        }),
      )
      expect(downloadBlob).toHaveBeenCalledWith(mockBlob, '案例分析汇总_abc12345.csv')
    })
  })

  it('downloads CSV with relevant only when clicking 仅相关案例', async () => {
    const mockBlob = new Blob(['csv-data'])
    fetchSpy.mockResolvedValue({
      ok: true,
      blob: () => Promise.resolve(mockBlob),
    } as Response)

    render(<BatchDownloadButton jobId="abc12345-xxxx" />)
    fireEvent.click(screen.getByText('下载汇总 CSV'))
    fireEvent.click(screen.getByText('仅相关案例'))

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        'http://localhost:8000/api/workbench/batch/abc12345-xxxx/download?relevant_only=true',
        expect.anything(),
      )
      expect(downloadBlob).toHaveBeenCalledWith(mockBlob, '案例分析汇总_abc12345.csv')
    })
  })

  it('downloads ZIP with all cases', async () => {
    const mockBlob = new Blob(['zip-data'])
    fetchSpy.mockResolvedValue({
      ok: true,
      blob: () => Promise.resolve(mockBlob),
    } as Response)

    render(<BatchDownloadButton jobId="abc12345-xxxx" />)
    fireEvent.click(screen.getByText('下载分析详情 ZIP'))
    fireEvent.click(screen.getByText('全部案例'))

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        'http://localhost:8000/api/workbench/batch/abc12345-xxxx/download-detail?',
        expect.anything(),
      )
      expect(downloadBlob).toHaveBeenCalledWith(mockBlob, '案例分析详情_abc12345.zip')
    })
  })

  it('shows toast error for 404 on CSV download', async () => {
    fetchSpy.mockResolvedValue({
      ok: false,
      status: 404,
    } as Response)

    render(<BatchDownloadButton jobId="abc12345-xxxx" />)
    fireEvent.click(screen.getByText('下载汇总 CSV'))
    fireEvent.click(screen.getByText('全部案例'))

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('汇总文件不存在')
    })
  })

  it('shows toast error for 404 on ZIP download', async () => {
    fetchSpy.mockResolvedValue({
      ok: false,
      status: 404,
    } as Response)

    render(<BatchDownloadButton jobId="abc12345-xxxx" />)
    fireEvent.click(screen.getByText('下载分析详情 ZIP'))
    fireEvent.click(screen.getByText('全部案例'))

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('分析详情文件尚未生成')
    })
  })

  it('shows toast error for non-404 HTTP errors', async () => {
    fetchSpy.mockResolvedValue({
      ok: false,
      status: 500,
    } as Response)

    render(<BatchDownloadButton jobId="abc12345-xxxx" />)
    fireEvent.click(screen.getByText('下载汇总 CSV'))
    fireEvent.click(screen.getByText('全部案例'))

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('下载失败')
    })
  })

  it('shows toast error when fetch throws network error', async () => {
    fetchSpy.mockRejectedValue(new Error('Network error'))

    render(<BatchDownloadButton jobId="abc12345-xxxx" />)
    fireEvent.click(screen.getByText('下载汇总 CSV'))
    fireEvent.click(screen.getByText('全部案例'))

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('下载失败')
    })
  })

  it('disables buttons while downloading', async () => {
    let resolveFetch: (v: unknown) => void
    fetchSpy.mockReturnValue(new Promise((resolve) => { resolveFetch = resolve }) as unknown as Promise<Response>)

    render(<BatchDownloadButton jobId="abc12345-xxxx" />)
    fireEvent.click(screen.getByText('下载汇总 CSV'))
    fireEvent.click(screen.getByText('全部案例'))

    await waitFor(() => {
      expect(screen.getByText('下载中...')).toBeInTheDocument()
    })

    resolveFetch!({ ok: true, blob: () => Promise.resolve(new Blob(['x'])) } as Response)
    await waitFor(() => {
      expect(screen.getByText('下载汇总 CSV')).toBeInTheDocument()
    })
  })

  it('renders without auth token when getAccessToken returns null', async () => {
    const { getAccessToken } = await import('@/lib/token')
    vi.mocked(getAccessToken).mockReturnValue(null as unknown as string)

    const mockBlob = new Blob(['csv'])
    fetchSpy.mockResolvedValue({
      ok: true,
      blob: () => Promise.resolve(mockBlob),
    } as Response)

    render(<BatchDownloadButton jobId="abc12345-xxxx" />)
    fireEvent.click(screen.getByText('下载汇总 CSV'))
    fireEvent.click(screen.getByText('全部案例'))

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: {},
        }),
      )
    })
  })

  it('closes dialog when cancel is clicked', () => {
    render(<BatchDownloadButton jobId="abc12345-xxxx" />)
    fireEvent.click(screen.getByText('下载汇总 CSV'))
    expect(screen.getByTestId('alert-dialog')).toBeInTheDocument()

    // Clicking the alert dialog wrapper triggers onOpenChange(false) in our mock
    fireEvent.click(screen.getByTestId('alert-dialog'))

    // Dialog should be closed now
    expect(screen.queryByTestId('alert-dialog')).not.toBeInTheDocument()
  })
})
