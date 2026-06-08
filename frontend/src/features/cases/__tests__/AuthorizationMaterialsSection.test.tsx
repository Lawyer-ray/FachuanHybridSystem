import { render, screen, fireEvent } from '@testing-library/react'
import { AuthorizationMaterialsSection } from '../components/AuthorizationMaterialsSection'

vi.mock('lucide-react', () => ({
  Download: (props: Record<string, unknown>) => <svg data-testid="download-icon" {...props} />,
  Loader2: (props: Record<string, unknown>) => <svg data-testid="loader-icon" {...props} />,
  FileText: (props: Record<string, unknown>) => <svg data-testid="file-text-icon" {...props} />,
  FileCheck: (props: Record<string, unknown>) => <svg data-testid="file-check-icon" {...props} />,
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('../api', () => ({
  caseApi: {
    downloadAuthorizationPackage: vi.fn().mockResolvedValue(undefined),
    downloadAuthorizationLetter: vi.fn().mockResolvedValue(undefined),
    downloadLegalRepCertificate: vi.fn().mockResolvedValue(undefined),
    downloadCombinedPOA: vi.fn().mockResolvedValue(undefined),
  },
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
}))

vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/ui/checkbox', () => ({
  Checkbox: (props: Record<string, unknown>) => <input type="checkbox" {...props} />,
}))

const ourParties = [
  { id: 1, client: 10, legal_status: 'plaintiff', client_detail: { name: '张三', is_our_client: true } },
]
const mixedParties = [
  { id: 1, client: 10, legal_status: 'plaintiff', client_detail: { name: '张三', is_our_client: true } },
  { id: 2, client: 20, legal_status: 'defendant', client_detail: { name: '李四', is_our_client: false } },
]

describe('AuthorizationMaterialsSection', () => {
  it('renders all four download buttons', () => {
    render(<AuthorizationMaterialsSection caseId={1} caseName="测试案" parties={ourParties as never} />)
    expect(screen.getByText('全套委托材料')).toBeInTheDocument()
    expect(screen.getByText('法定代表人证明')).toBeInTheDocument()
    expect(screen.getByText('所函')).toBeInTheDocument()
    expect(screen.getByText('授权委托书')).toBeInTheDocument()
  })

  it('disables buttons when no our parties', () => {
    render(<AuthorizationMaterialsSection caseId={1} caseName="测试案" parties={[]} />)
    const btn = screen.getByText('全套委托材料')
    expect(btn).toBeDisabled()
  })

  it('enables buttons when our parties exist', () => {
    render(<AuthorizationMaterialsSection caseId={1} caseName="测试案" parties={ourParties as never} />)
    const btn = screen.getByText('全套委托材料')
    expect(btn).not.toBeDisabled()
  })

  it('enables letter button even without our parties', () => {
    render(<AuthorizationMaterialsSection caseId={1} caseName="测试案" parties={[]} />)
    const btn = screen.getByText('所函')
    expect(btn).not.toBeDisabled()
  })

  it('calls downloadAuthorizationPackage on click', async () => {
    const { caseApi } = await import('../api')
    render(<AuthorizationMaterialsSection caseId={1} caseName="测试案" parties={ourParties as never} />)
    fireEvent.click(screen.getByText('全套委托材料'))
    expect(caseApi.downloadAuthorizationPackage).toHaveBeenCalledWith(1, '测试案')
  })
})
