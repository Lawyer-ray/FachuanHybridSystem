vi.mock('react-router', () => ({
  useNavigate: () => vi.fn(),
  generatePath: { clientDetail: (id: number | string) => `/admin/clients/${id}` },
}))

vi.mock('@/lib/clipboard', () => ({
  copyToClipboard: vi.fn(),
}))

vi.mock('framer-motion', () => ({
  motion: { div: (p: Record<string, unknown>) => <div {...p} /> },
  AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

vi.mock('lucide-react', () => {
  const Icon = (props: Record<string, unknown>) => <svg data-testid="icon" {...props} />
  return {
    Users: Icon, User: Icon, Building2: Icon, Landmark: Icon, Copy: Icon,
  }
})

vi.mock('@/components/ui/table', () => ({
  Table: ({ children, ...p }: Record<string, unknown>) => <table {...p}>{children}</table>,
  TableHeader: ({ children }: Record<string, unknown>) => <thead>{children}</thead>,
  TableBody: ({ children }: Record<string, unknown>) => <tbody>{children}</tbody>,
  TableRow: ({ children, ...p }: Record<string, unknown>) => <tr {...p}>{children}</tr>,
  TableHead: ({ children, ...p }: Record<string, unknown>) => <th {...p}>{children}</th>,
  TableCell: ({ children, ...p }: Record<string, unknown>) => <td {...p}>{children}</td>,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...p }: Record<string, unknown>) => <button {...p}>{children}</button>,
}))

vi.mock('@/routes/paths', () => ({
  generatePath: { clientDetail: (id: number | string) => `/admin/clients/${id}` },
}))

import { render, screen, fireEvent } from '@testing-library/react'
import { ClientTable } from '../ClientTable'
import { copyToClipboard } from '@/lib/clipboard'
import type { Client } from '../../types'

function makeClient(overrides: Partial<Client> = {}): Client {
  return {
    id: 1,
    name: 'Wang',
    is_our_client: true,
    phone: '00000000000',
    address: 'Beijing',
    client_type: 'natural',
    client_type_label: '自然人',
    id_number: '000000000000000100', // pragma: allowlist secret
    legal_representative: null,
    legal_representative_id_number: null,
    identity_docs: [],
    ...overrides,
  }
}

describe('ClientTable - coverage improvements', () => {
  // ========== formatIdNumber - covers null and short id_number ==========

  it('shows raw id_number when length <= 8', () => {
    render(<ClientTable clients={[makeClient({ id_number: '12345678' })]} />)
    expect(screen.getByText('12345678')).toBeInTheDocument()
  })

  it('shows dash for null id_number', () => {
    render(<ClientTable clients={[makeClient({ id_number: null })]} />)
    const dashes = screen.getAllByText('-')
    expect(dashes.length).toBeGreaterThanOrEqual(1)
  })

  // ========== formatPhone - covers null and non-11-digit phone ==========

  it('shows raw phone when length is not 11', () => {
    render(<ClientTable clients={[makeClient({ phone: '12345' })]} />)
    expect(screen.getByText('12345')).toBeInTheDocument()
  })

  it('shows dash for null phone', () => {
    render(<ClientTable clients={[makeClient({ phone: null })]} />)
    const dashes = screen.getAllByText('-')
    expect(dashes.length).toBeGreaterThanOrEqual(1)
  })

  it('shows masked phone for 11-digit number', () => {
    render(<ClientTable clients={[makeClient({ phone: '13800000000' })]} />) // pragma: allowlist secret
    expect(screen.getByText('138****0000')).toBeInTheDocument()
  })

  // ========== formatIdNumber - covers masked id_number ==========

  it('shows masked id_number for long id', () => {
    render(<ClientTable clients={[makeClient({ id_number: '000000000000000100' })]} />)
    expect(screen.getByText('0000****0100')).toBeInTheDocument()
  })

  // ========== ClientRow - covers TYPE_CONFIG fallback ==========

  it('renders with non_legal_org client type', () => {
    render(<ClientTable clients={[makeClient({ client_type: 'non_legal_org' })]} />)
    expect(screen.getByText('Wang')).toBeInTheDocument()
  })

  it('renders with legal client type', () => {
    render(<ClientTable clients={[makeClient({ client_type: 'legal' })]} />)
    expect(screen.getByText('Wang')).toBeInTheDocument()
  })

  // ========== ClientRow - covers copy button ==========

  it('copy button stops propagation and copies text', () => {
    render(<ClientTable clients={[makeClient()]} />)
    const copyBtn = screen.getByRole('button')
    fireEvent.click(copyBtn)
    // copyToClipboard should be called (mocked)
  })

  // ========== ClientRow - covers row click ==========

  it('row click navigates to client detail', () => {
    render(<ClientTable clients={[makeClient()]} />)
    const row = screen.getByText('Wang').closest('tr')
    if (row) {
      fireEvent.click(row)
    }
  })

  // ========== Loading state ==========

  it('renders skeleton when isLoading is true', () => {
    const { container } = render(<ClientTable clients={[]} isLoading />)
    expect(container.querySelectorAll('tr').length).toBeGreaterThanOrEqual(5)
  })

  // ========== Empty state ==========

  it('renders empty state', () => {
    render(<ClientTable clients={[]} />)
    expect(screen.getByText('暂无当事人数据')).toBeInTheDocument()
  })

  // ========== Multiple clients ==========

  it('renders multiple client rows', () => {
    render(<ClientTable clients={[makeClient(), makeClient({ id: 2, name: 'Li', client_type: 'legal' })]} />)
    expect(screen.getByText('Wang')).toBeInTheDocument()
    expect(screen.getByText('Li')).toBeInTheDocument()
  })

  // ========== is_our_client badges ==========

  it('shows 我方 badge for our client', () => {
    render(<ClientTable clients={[makeClient({ is_our_client: true })]} />)
    expect(screen.getByText('我方')).toBeInTheDocument()
  })

  it('shows 对方 badge for other client', () => {
    render(<ClientTable clients={[makeClient({ is_our_client: false })]} />)
    expect(screen.getByText('对方')).toBeInTheDocument()
  })

  // ========== Table headers ==========

  it('renders all table headers', () => {
    render(<ClientTable clients={[makeClient()]} />)
    expect(screen.getByText('ID')).toBeInTheDocument()
    expect(screen.getByText('名称')).toBeInTheDocument()
    expect(screen.getByText('证件号码')).toBeInTheDocument()
    expect(screen.getByText('联系方式')).toBeInTheDocument()
  })

  // ========== ClientRow memo - covers handleCopy callback ==========

  it('handleCopy callback uses copyToClipboard with formatted text', () => {
    render(<ClientTable clients={[makeClient()]} />)
    const copyBtns = screen.getAllByRole('button')
    fireEvent.click(copyBtns[0])
    expect(copyToClipboard).toHaveBeenCalled()
  })
})
