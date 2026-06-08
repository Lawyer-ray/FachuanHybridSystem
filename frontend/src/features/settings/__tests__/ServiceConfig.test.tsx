import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { ServiceConfig } from '../components/ServiceConfig'

vi.mock('lucide-react', () => ({
  ArrowLeft: () => <svg data-testid="arrow-left" />,
  Save: () => <svg data-testid="save-icon" />,
  Eye: () => <svg data-testid="eye-icon" />,
  EyeOff: () => <svg data-testid="eye-off-icon" />,
  Loader2: () => <svg data-testid="loader-icon" />,
  Plus: () => <svg data-testid="plus-icon" />,
  Pencil: () => <svg data-testid="pencil-icon" />,
  Trash2: () => <svg data-testid="trash-icon" />,
  Lock: () => <svg data-testid="lock-icon" />,
  ShieldCheck: () => <svg data-testid="shield-check" />,
  ShieldOff: () => <svg data-testid="shield-off" />,
  Wifi: () => <svg data-testid="wifi-icon" />,
  WifiOff: () => <svg data-testid="wifi-off" />,
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

vi.mock('@/routes/paths', () => ({
  PATHS: { ADMIN_SETTINGS: '/admin/settings' },
}))

vi.mock('@/lib/api', () => ({
  getApiBaseUrl: () => 'http://localhost:8002/api/v1',
  getBackendUrl: () => 'http://localhost:8002',
}))

vi.mock('../hooks/use-system-configs', () => ({
  useSystemConfigs: () => ({ data: null, isLoading: false }),
  useUpdateSystemConfigs: () => ({ mutate: vi.fn(), isPending: false }),
  useCreateSystemConfig: () => ({ mutate: vi.fn(), isPending: false }),
  usePatchSystemConfig: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteSystemConfig: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('../constants/config-hints', () => ({
  CATEGORY_HINTS: {
    ai: { title: 'AI 服务配置', description: 'AI 后端参数', fields: {}, fieldOrder: [] },
  },
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
}))
vi.mock('@/components/ui/input', () => ({
  Input: (props: Record<string, unknown>) => <input {...props} />,
}))
vi.mock('@/components/ui/label', () => ({
  Label: ({ children, ...props }: Record<string, unknown>) => <label {...props}>{children}</label>,
}))
vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, ...props }: Record<string, unknown>) => <span {...props}>{children}</span>,
}))
vi.mock('@/components/ui/switch', () => ({
  Switch: (props: Record<string, unknown>) => <input type="checkbox" {...props} />,
}))
vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
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
}))

describe('ServiceConfig', () => {
  it('renders default title when no category', () => {
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    expect(screen.getByText('配置')).toBeInTheDocument()
  })

  it('renders back to settings button', () => {
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    expect(screen.getByText('返回设置')).toBeInTheDocument()
  })


  it('renders without crashing', () => {
    const { container } = render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    expect(container).toBeTruthy()
  })

  it('renders arrow left icon', () => {
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    expect(screen.getByTestId('arrow-left')).toBeInTheDocument()
  })
})
