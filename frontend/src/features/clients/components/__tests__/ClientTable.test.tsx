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

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ClientTable } from '../ClientTable'
import type { Client } from '../../types'

function makeClient(overrides: Partial<Client> = {}): Client {
  return {
    id: 1,
    name: 'Wang',
    is_our_client: true,
    phone: '13800138000',
    address: 'Beijing',
    client_type: 'natural',
    client_type_label: '自然人',
    id_number: '110101199001011234',
    legal_representative: null,
    legal_representative_id_number: null,
    identity_docs: [],
    ...overrides,
  }
}

describe('ClientTable', () => {
  it('renders loading skeleton when isLoading is true', () => {
    const { container } = render(<ClientTable clients={[]} isLoading />)
    // Should render skeleton rows (5 data rows + 1 header)
    expect(container.querySelectorAll('tr').length).toBeGreaterThanOrEqual(5)
  })

  it('renders empty state when no clients', () => {
    render(<ClientTable clients={[]} />)
    expect(screen.getByText('暂无当事人数据')).toBeInTheDocument()
  })

  it('renders client rows when clients are provided', () => {
    render(<ClientTable clients={[makeClient(), makeClient({ id: 2, name: 'Li' })]} />)
    expect(screen.getByText('Wang')).toBeInTheDocument()
    expect(screen.getByText('Li')).toBeInTheDocument()
  })

  it('displays client id numbers with masking', () => {
    render(<ClientTable clients={[makeClient({ id_number: '110101199001011234' })]} />)
    expect(screen.getByText('1101****1234')).toBeInTheDocument()
  })

  it('displays phone numbers with masking', () => {
    render(<ClientTable clients={[makeClient({ phone: '13800138000' })]} />)
    expect(screen.getByText('138****8000')).toBeInTheDocument()
  })

  it('shows dash for null id_number and phone', () => {
    render(<ClientTable clients={[makeClient({ id_number: null, phone: null })]} />)
    const dashes = screen.getAllByText('-')
    expect(dashes.length).toBeGreaterThanOrEqual(2)
  })

  it('shows 我方 badge for our client', () => {
    render(<ClientTable clients={[makeClient({ is_our_client: true })]} />)
    expect(screen.getByText('我方')).toBeInTheDocument()
  })

  it('shows 对方 badge for other party client', () => {
    render(<ClientTable clients={[makeClient({ is_our_client: false })]} />)
    expect(screen.getByText('对方')).toBeInTheDocument()
  })

  it('renders all table header columns', () => {
    render(<ClientTable clients={[makeClient()]} />)
    expect(screen.getByText('ID')).toBeInTheDocument()
    expect(screen.getByText('名称')).toBeInTheDocument()
    expect(screen.getByText('证件号码')).toBeInTheDocument()
    expect(screen.getByText('联系方式')).toBeInTheDocument()
  })
})
