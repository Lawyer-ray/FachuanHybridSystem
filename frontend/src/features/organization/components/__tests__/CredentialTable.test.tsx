vi.mock('@/lib/date', () => ({
  formatDateOnly: (d: string) => d?.split('T')[0] ?? '-',
}))

vi.mock('@/components/ui/table', () => ({
  Table: ({ children }: any) => <table>{children}</table>,
  TableBody: ({ children }: any) => <tbody>{children}</tbody>,
  TableCell: ({ children, className, colSpan }: any) => <td className={className} colSpan={colSpan}>{children}</td>,
  TableHead: ({ children, className }: any) => <th className={className}>{children}</th>,
  TableHeader: ({ children }: any) => <thead>{children}</thead>,
  TableRow: ({ children, className, onClick }: any) => <tr className={className} onClick={onClick}>{children}</tr>,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, variant, size, className, ...props }: any) => (
    <button onClick={onClick} {...props}>{children}</button>
  ),
}))

import { render, screen, fireEvent } from '@testing-library/react'
import { CredentialTable } from '../CredentialTable'
import type { AccountCredential, Lawyer } from '../../types'

describe('CredentialTable', () => {
  const mockLawyers: Lawyer[] = [
    { id: 1, username: 'zhang', real_name: '张三', phone: null, license_no: '', id_card: '', law_firm: null, is_admin: false, is_active: true, license_pdf_url: null, avatar_url: null, law_firm_detail: null },
    { id: 2, username: 'lisi', real_name: '', phone: null, license_no: '', id_card: '', law_firm: null, is_admin: false, is_active: true, license_pdf_url: null, avatar_url: null, law_firm_detail: null },
  ]

  const mockCredentials: AccountCredential[] = [
    { id: 1, lawyer: 1, site_name: '威科先行', url: 'https://wk.com', account: 'admin', created_at: '2026-01-15T00:00:00Z', updated_at: '2026-01-15T00:00:00Z' },
    { id: 2, lawyer: 1, site_name: 'Alpha', url: null, account: 'test', created_at: '2026-02-20T00:00:00Z', updated_at: '2026-02-20T00:00:00Z' },
  ]

  it('renders table headers', () => {
    render(<CredentialTable credentials={[]} lawyers={[]} onEdit={vi.fn()} onDelete={vi.fn()} />)
    expect(screen.getByText('网站名称')).toBeInTheDocument()
    expect(screen.getByText('URL')).toBeInTheDocument()
    expect(screen.getByText('账号')).toBeInTheDocument()
    expect(screen.getByText('所属律师')).toBeInTheDocument()
    expect(screen.getByText('创建时间')).toBeInTheDocument()
  })

  it('renders credential data', () => {
    render(<CredentialTable credentials={mockCredentials} lawyers={mockLawyers} onEdit={vi.fn()} onDelete={vi.fn()} />)
    expect(screen.getByText('威科先行')).toBeInTheDocument()
    expect(screen.getByText('Alpha')).toBeInTheDocument()
    expect(screen.getByText('admin')).toBeInTheDocument()
  })

  it('renders empty state when no credentials', () => {
    render(<CredentialTable credentials={[]} lawyers={[]} onEdit={vi.fn()} onDelete={vi.fn()} />)
    expect(screen.getByText('暂无凭证数据')).toBeInTheDocument()
  })

  it('calls onEdit when edit button clicked', () => {
    const onEdit = vi.fn()
    render(<CredentialTable credentials={mockCredentials} lawyers={mockLawyers} onEdit={onEdit} onDelete={vi.fn()} />)
    fireEvent.click(screen.getByLabelText('编辑凭证 威科先行'))
    expect(onEdit).toHaveBeenCalledWith(mockCredentials[0])
  })

  it('calls onDelete when delete button clicked', () => {
    const onDelete = vi.fn()
    render(<CredentialTable credentials={mockCredentials} lawyers={mockLawyers} onEdit={vi.fn()} onDelete={onDelete} />)
    fireEvent.click(screen.getByLabelText('删除凭证 威科先行'))
    expect(onDelete).toHaveBeenCalledWith(mockCredentials[0])
  })

  it('shows loading skeleton when isLoading is true', () => {
    const { container } = render(<CredentialTable credentials={[]} lawyers={[]} isLoading onEdit={vi.fn()} onDelete={vi.fn()} />)
    expect(container.querySelectorAll('[class*="animate-pulse"]').length).toBeGreaterThan(0)
  })

  it('shows lawyer name from real_name', () => {
    render(<CredentialTable credentials={mockCredentials} lawyers={mockLawyers} onEdit={vi.fn()} onDelete={vi.fn()} />)
    expect(screen.getAllByText('张三').length).toBeGreaterThanOrEqual(1)
  })

  it('shows - when lawyer not found', () => {
    const creds = [{ ...mockCredentials[0], lawyer: 999 }]
    render(<CredentialTable credentials={creds} lawyers={mockLawyers} onEdit={vi.fn()} onDelete={vi.fn()} />)
    // lawyer 999 not in list -> '-'
    const cells = screen.getAllByText('-')
    expect(cells.length).toBeGreaterThanOrEqual(1)
  })

  it('falls back to username when real_name is empty', () => {
    const creds = [{ ...mockCredentials[0], lawyer: 2 }]
    render(<CredentialTable credentials={creds} lawyers={mockLawyers} onEdit={vi.fn()} onDelete={vi.fn()} />)
    // lawyer 2 has real_name='', so falls back to username 'lisi'
    expect(screen.getByText('lisi')).toBeInTheDocument()
  })

  it('shows - for empty site_name', () => {
    const creds = [{ ...mockCredentials[0], site_name: '' }]
    render(<CredentialTable credentials={creds} lawyers={mockLawyers} onEdit={vi.fn()} onDelete={vi.fn()} />)
    const cells = screen.getAllByText('-')
    expect(cells.length).toBeGreaterThanOrEqual(1)
  })

  it('shows - for empty account', () => {
    const creds = [{ ...mockCredentials[0], account: '' }]
    render(<CredentialTable credentials={creds} lawyers={mockLawyers} onEdit={vi.fn()} onDelete={vi.fn()} />)
    const cells = screen.getAllByText('-')
    expect(cells.length).toBeGreaterThanOrEqual(1)
  })

  it('shows - for null url', () => {
    const creds = [{ ...mockCredentials[0], url: null }]
    render(<CredentialTable credentials={creds} lawyers={mockLawyers} onEdit={vi.fn()} onDelete={vi.fn()} />)
    // URL cell should show '-'
    const cells = screen.getAllByText('-')
    expect(cells.length).toBeGreaterThanOrEqual(1)
  })

  it('renders URL as clickable link when present', () => {
    render(<CredentialTable credentials={mockCredentials} lawyers={mockLawyers} onEdit={vi.fn()} onDelete={vi.fn()} />)
    const link = screen.getByText('https://wk.com')
    expect(link.closest('a')).toHaveAttribute('href', 'https://wk.com')
    expect(link.closest('a')).toHaveAttribute('target', '_blank')
  })

  it('shows - for empty url string', () => {
    const creds = [{ ...mockCredentials[0], url: '' }]
    render(<CredentialTable credentials={creds} lawyers={mockLawyers} onEdit={vi.fn()} onDelete={vi.fn()} />)
    // Empty string is falsy, so shows '-'
    const cells = screen.getAllByText('-')
    expect(cells.length).toBeGreaterThanOrEqual(1)
  })
})
