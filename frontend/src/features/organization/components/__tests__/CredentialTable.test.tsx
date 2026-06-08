vi.mock('@/lib/date', () => ({
  formatDateOnly: (d: string) => d?.split('T')[0] ?? '-',
}))

import { render, screen, fireEvent } from '@testing-library/react'
import { CredentialTable } from '../CredentialTable'
import type { AccountCredential, Lawyer } from '../../types'

describe('CredentialTable', () => {
  const mockLawyers: Lawyer[] = [
    { id: 1, username: 'zhang', real_name: '张三', phone: null, license_no: '', id_card: '', law_firm: null, is_admin: false, is_active: true, license_pdf_url: null, avatar_url: null, law_firm_detail: null },
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
})
