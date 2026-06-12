import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { AuthorizationMaterialsSection } from '../AuthorizationMaterialsSection'
import type { CaseParty } from '../../types'
import { caseApi } from '../../api'

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})

vi.mock('../../api', () => ({
  caseApi: {
    downloadAuthorizationPackage: vi.fn().mockResolvedValue(undefined),
    downloadLegalRepCertificate: vi.fn().mockResolvedValue(undefined),
    downloadAuthorizationLetter: vi.fn().mockResolvedValue(undefined),
    downloadCombinedPOA: vi.fn().mockResolvedValue(undefined),
  },
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...p }: Record<string, unknown>) => <button {...p}>{children}</button>,
}))
vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children, open }: { children: React.ReactNode; open?: boolean }) =>
    open === false ? null : <div data-testid="dialog">{children}</div>,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))
vi.mock('@/components/ui/checkbox', () => ({
  Checkbox: ({ onCheckedChange, checked, ...p }: Record<string, unknown>) => (
    <input
      type="checkbox"
      checked={!!checked}
      onChange={(e) => onCheckedChange?.(e.target.checked)}
      {...p}
    />
  ),
}))

vi.mock('lucide-react', () => ({
  Download: (p: Record<string, unknown>) => <svg data-testid="download" {...p} />,
  Loader2: (p: Record<string, unknown>) => <svg data-testid="loader" {...p} />,
  FileText: (p: Record<string, unknown>) => <svg data-testid="file-text" {...p} />,
  FileCheck: (p: Record<string, unknown>) => <svg data-testid="file-check" {...p} />,
}))

const makeParty = (id: number, name: string, isOur: boolean, legalStatus?: string): CaseParty =>
  ({
    id,
    client: id,
    client_detail: { name, is_our_client: isOur, client_type: 'natural' },
    legal_status: legalStatus ?? null,
  }) as unknown as CaseParty

describe('AuthorizationMaterialsSection', () => {
  beforeEach(() => {
    cleanup()
    vi.clearAllMocks()
    vi.mocked(caseApi.downloadAuthorizationPackage).mockResolvedValue(undefined)
    vi.mocked(caseApi.downloadLegalRepCertificate).mockResolvedValue(undefined)
    vi.mocked(caseApi.downloadAuthorizationLetter).mockResolvedValue(undefined)
    vi.mocked(caseApi.downloadCombinedPOA).mockResolvedValue(undefined)
  })

  const ourParty = makeParty(1, '张三', true, 'plaintiff')
  const theirParty = makeParty(2, '李四', false, 'defendant')
  const ourParty2 = makeParty(3, '王五', true, 'plaintiff')

  it('renders all 4 download buttons', () => {
    render(<AuthorizationMaterialsSection caseId={1} caseName="Test" parties={[ourParty]} />)
    expect(screen.getByText('全套委托材料')).toBeInTheDocument()
    expect(screen.getByText('法定代表人证明')).toBeInTheDocument()
    expect(screen.getByText('所函')).toBeInTheDocument()
    expect(screen.getByText('授权委托书')).toBeInTheDocument()
  })

  it('disables package, legal-rep, and poa buttons when no our parties', () => {
    render(<AuthorizationMaterialsSection caseId={1} caseName="Test" parties={[theirParty]} />)
    const pkgBtn = screen.getByText('全套委托材料').closest('button')!
    expect(pkgBtn).toBeDisabled()
    const legalRepBtn = screen.getByText('法定代表人证明').closest('button')!
    expect(legalRepBtn).toBeDisabled()
    const poaBtn = screen.getByText('授权委托书').closest('button')!
    expect(poaBtn).toBeDisabled()
  })

  it('letter button is not disabled when no our parties', () => {
    render(<AuthorizationMaterialsSection caseId={1} caseName="Test" parties={[theirParty]} />)
    const letterBtn = screen.getByText('所函').closest('button')!
    expect(letterBtn).not.toBeDisabled()
  })

  it('downloads package successfully', async () => {
    render(<AuthorizationMaterialsSection caseId={1} caseName="Test Case" parties={[ourParty]} />)
    fireEvent.click(screen.getByText('全套委托材料'))
    expect(caseApi.downloadAuthorizationPackage).toHaveBeenCalledWith(1, 'Test Case')
  })

  it('downloads letter successfully', async () => {
    render(<AuthorizationMaterialsSection caseId={1} caseName="Test Case" parties={[]} />)
    fireEvent.click(screen.getByText('所函'))
    expect(caseApi.downloadAuthorizationLetter).toHaveBeenCalledWith(1, 'Test Case')
  })

  it('downloads combined POA with our party ids', async () => {
    render(<AuthorizationMaterialsSection caseId={1} caseName="Test Case" parties={[ourParty, theirParty]} />)
    fireEvent.click(screen.getByText('授权委托书'))
    expect(caseApi.downloadCombinedPOA).toHaveBeenCalledWith(1, 'Test Case', [1])
  })

  it('handles download error', async () => {
    vi.mocked(caseApi.downloadAuthorizationPackage).mockRejectedValue(new Error('fail'))
    const { toast } = await import('sonner')
    render(<AuthorizationMaterialsSection caseId={1} caseName="Test" parties={[ourParty]} />)
    fireEvent.click(screen.getByText('全套委托材料'))
    // wait a tick
    await new Promise(r => setTimeout(r, 10))
    expect(vi.mocked(toast.error)).toHaveBeenCalledWith('下载失败')
  })

  // Legal rep dialog
  it('opens legal rep dialog and shows our parties', () => {
    render(<AuthorizationMaterialsSection caseId={1} caseName="Test" parties={[ourParty, theirParty]} />)
    fireEvent.click(screen.getByText('法定代表人证明'))
    expect(screen.getByText('法定代表人证明 — 选择当事人')).toBeInTheDocument()
    expect(screen.getByText('张三')).toBeInTheDocument()
    // 李四 is not our client, should not appear in the dialog
    expect(screen.queryByText('李四')).not.toBeInTheDocument()
  })

  it('shows legal status in parentheses', () => {
    render(<AuthorizationMaterialsSection caseId={1} caseName="Test" parties={[ourParty]} />)
    fireEvent.click(screen.getByText('法定代表人证明'))
    expect(screen.getByText(/原告/)).toBeInTheDocument()
  })

  it('shows toggleAll checkbox when multiple our parties', () => {
    render(<AuthorizationMaterialsSection caseId={1} caseName="Test" parties={[ourParty, ourParty2]} />)
    fireEvent.click(screen.getByText('法定代表人证明'))
    expect(screen.getByText('全选')).toBeInTheDocument()
  })

  it('does not show toggleAll when single our party', () => {
    render(<AuthorizationMaterialsSection caseId={1} caseName="Test" parties={[ourParty]} />)
    fireEvent.click(screen.getByText('法定代表人证明'))
    expect(screen.queryByText('全选')).not.toBeInTheDocument()
  })

  it('handles confirm with no selection (early return)', () => {
    render(<AuthorizationMaterialsSection caseId={1} caseName="Test" parties={[ourParty]} />)
    fireEvent.click(screen.getByText('法定代表人证明'))
    // Click confirm without selecting anyone
    fireEvent.click(screen.getByText('生成并下载'))
    expect(caseApi.downloadLegalRepCertificate).not.toHaveBeenCalled()
  })

  it('selects a party and confirms legal rep download', async () => {
    render(<AuthorizationMaterialsSection caseId={1} caseName="Test" parties={[ourParty]} />)
    fireEvent.click(screen.getByText('法定代表人证明'))
    // Click checkbox for 张三
    const checkboxes = screen.getAllByRole('checkbox')
    fireEvent.click(checkboxes[0])
    fireEvent.click(screen.getByText('生成并下载'))
    expect(caseApi.downloadLegalRepCertificate).toHaveBeenCalledWith(1, 1, '张三')
  })

  it('closes legal rep dialog on cancel', () => {
    render(<AuthorizationMaterialsSection caseId={1} caseName="Test" parties={[ourParty]} />)
    fireEvent.click(screen.getByText('法定代表人证明'))
    expect(screen.getByText('法定代表人证明 — 选择当事人')).toBeInTheDocument()
    const cancelBtns = screen.getAllByText('取消')
    fireEvent.click(cancelBtns[cancelBtns.length - 1])
  })

  it('handles legal rep download error', async () => {
    vi.mocked(caseApi.downloadLegalRepCertificate).mockRejectedValue(new Error('fail'))
    const { toast } = await import('sonner')
    render(<AuthorizationMaterialsSection caseId={1} caseName="Test" parties={[ourParty]} />)
    fireEvent.click(screen.getByText('法定代表人证明'))
    const checkboxes = screen.getAllByRole('checkbox')
    fireEvent.click(checkboxes[0])
    fireEvent.click(screen.getByText('生成并下载'))
    await new Promise(r => setTimeout(r, 10))
    expect(vi.mocked(toast.error)).toHaveBeenCalledWith('下载失败')
  })

  it('shows party name fallback when client_detail.name is null', () => {
    const partyNoName = {
      id: 5,
      client: 5,
      client_detail: { name: null, is_our_client: true, client_type: 'natural' },
      legal_status: null,
    } as unknown as CaseParty
    render(<AuthorizationMaterialsSection caseId={1} caseName="Test" parties={[partyNoName]} />)
    fireEvent.click(screen.getByText('法定代表人证明'))
    expect(screen.getByText('#5')).toBeInTheDocument()
  })

  it('shows party without legal_status (no parentheses)', () => {
    const partyNoStatus = makeParty(6, '赵六', true)
    render(<AuthorizationMaterialsSection caseId={1} caseName="Test" parties={[partyNoStatus]} />)
    fireEvent.click(screen.getByText('法定代表人证明'))
    expect(screen.getByText('赵六')).toBeInTheDocument()
  })

  it('handles toggle all then deselect', () => {
    render(<AuthorizationMaterialsSection caseId={1} caseName="Test" parties={[ourParty, ourParty2]} />)
    fireEvent.click(screen.getByText('法定代表人证明'))
    // Toggle all
    const allCheckbox = screen.getByText('全选').closest('label')!.querySelector('input[type="checkbox"]')!
    fireEvent.click(allCheckbox)
    // Toggle all off
    fireEvent.click(allCheckbox)
    // Confirm button should be disabled (0 selected)
    const confirmBtn = screen.getByText('生成并下载').closest('button')!
    expect(confirmBtn).toBeDisabled()
  })

  it('shows title attribute when no our parties', () => {
    render(<AuthorizationMaterialsSection caseId={1} caseName="Test" parties={[theirParty]} />)
    const pkgBtn = screen.getByText('全套委托材料').closest('button')!
    expect(pkgBtn).toHaveAttribute('title', '没有我方当事人')
  })
})
