vi.mock('react-router', () => ({
  useNavigate: () => vi.fn(),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...p }: Record<string, unknown>) => <button {...p}>{children}</button>,
}))

vi.mock('@/components/ui/input', () => ({
  Input: (props: Record<string, unknown>) => <input {...props} />,
}))

vi.mock('@/components/ui/card', () => ({
  Card: ({ children, ...p }: Record<string, unknown>) => <div {...p}>{children}</div>,
  CardContent: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  CardHeader: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  CardTitle: ({ children }: Record<string, unknown>) => <h3>{children}</h3>,
}))

vi.mock('@/components/ui/tabs', () => ({
  Tabs: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  TabsContent: ({ children, value }: Record<string, unknown>) => <div data-tab={value}>{children}</div>,
  TabsList: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  TabsTrigger: ({ children, value }: Record<string, unknown>) => <button data-value={value}>{children}</button>,
}))

vi.mock('@/components/ui/form', () => ({
  Form: ({ children }: { children: React.ReactNode }) => <form>{children}</form>,
  FormControl: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  FormField: ({ render: renderFn }: { render: (props: { field: Record<string, unknown> }) => React.ReactNode }) =>
    renderFn({ field: { value: '', onChange: vi.fn(), onBlur: vi.fn(), name: '', ref: vi.fn() } }),
  FormItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  FormLabel: ({ children }: { children: React.ReactNode }) => <label>{children}</label>,
  FormMessage: () => <div />,
  FormDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
}))

vi.mock('@/components/ui/select', () => ({
  Select: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  SelectContent: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  SelectItem: ({ children, value }: Record<string, unknown>) => <option value={value}>{children}</option>,
  SelectTrigger: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  SelectValue: () => <span />,
}))

vi.mock('@/components/ui/switch', () => ({
  Switch: (props: Record<string, unknown>) => <input type="checkbox" {...props} />,
}))

vi.mock('lucide-react', () => {
  const Icon = (p: Record<string, unknown>) => <svg data-testid="icon" {...p} />
  return { Loader2: Icon, Save: Icon, X: Icon, Upload: Icon }
})

vi.mock('../../hooks/use-client', () => ({
  useClient: vi.fn(() => ({
    data: null,
    isLoading: false,
    error: null,
  })),
}))

vi.mock('../../hooks/use-client-mutations', () => ({
  useClientMutations: vi.fn(() => ({
    createClient: { mutate: vi.fn(), isPending: false },
    updateClient: { mutate: vi.fn(), isPending: false },
    deleteClient: { mutate: vi.fn(), isPending: false },
  })),
}))

vi.mock('../api', () => ({
  clientApi: {
    createWithDocs: vi.fn(),
    validateIdCard: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
  },
}))

vi.mock('../../components/EnterpriseSearch', () => ({
  EnterpriseSearch: ({ onPrefill }: { onPrefill: (d: unknown) => void }) => (
    <div data-testid="enterprise-search">EnterpriseSearch</div>
  ),
}))

vi.mock('../../components/TextParser', () => ({
  TextParser: ({ onParsed }: { onParsed: (d: unknown) => void }) => (
    <div data-testid="text-parser">TextParser</div>
  ),
}))

vi.mock('../../components/PropertyClueList', () => ({
  PropertyClueList: () => <div data-testid="property-clue-list">PropertyClueList</div>,
}))

vi.mock('../../components/IdentityDocManager', () => ({
  IdentityDocManager: () => <div data-testid="identity-doc-manager">IdentityDocManager</div>,
}))

vi.mock('@/routes/paths', () => ({
  generatePath: {
    clientDetail: (id: string | number) => `/admin/clients/${id}`,
    clientEdit: (id: string) => `/admin/clients/${id}/edit`,
  },
}))

vi.mock('framer-motion', () => ({
  motion: { div: (p: Record<string, unknown>) => <div {...p} /> },
  AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

import { render, screen } from '@testing-library/react'
import { ClientForm } from '../ClientForm'
import { useClient } from '../../hooks/use-client'
import { useClientMutations } from '../../hooks/use-client-mutations'

describe('ClientForm', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders create mode with form title', () => {
    render(<ClientForm mode="create" />)
    expect(screen.getByText('当事人信息')).toBeInTheDocument()
  })

  it('renders create mode with enterprise search and text parser', () => {
    render(<ClientForm mode="create" />)
    expect(screen.getByTestId('enterprise-search')).toBeInTheDocument()
    expect(screen.getByTestId('text-parser')).toBeInTheDocument()
  })

  it('renders doc upload section in create mode', () => {
    render(<ClientForm mode="create" />)
    expect(screen.getByText('证件上传（可选）')).toBeInTheDocument()
    expect(screen.getByText('添加证件')).toBeInTheDocument()
  })

  it('renders form fields in create mode', () => {
    render(<ClientForm mode="create" />)
    expect(screen.getByText('姓名')).toBeInTheDocument()
    expect(screen.getByText('类型')).toBeInTheDocument()
    expect(screen.getByText('手机号')).toBeInTheDocument()
    expect(screen.getByText('地址')).toBeInTheDocument()
  })

  it('renders loading spinner in edit mode when loading', () => {
    vi.mocked(useClient).mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as ReturnType<typeof useClient>)

    render(<ClientForm clientId="1" mode="edit" />)
    expect(document.querySelector('.animate-spin')).toBeTruthy()
  })

  it('renders error state in edit mode when error occurs', () => {
    vi.mocked(useClient).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error('Failed'),
    } as ReturnType<typeof useClient>)

    render(<ClientForm clientId="1" mode="edit" />)
    expect(screen.getByText('加载当事人数据失败')).toBeInTheDocument()
    expect(screen.getByText('返回')).toBeInTheDocument()
  })

  it('renders edit mode with tabs when client data is loaded', () => {
    vi.mocked(useClient).mockReturnValue({
      data: {
        id: 1, name: 'Wang', is_our_client: true, client_type: 'natural',
        phone: '138', address: 'Beijing', id_number: '110101190001010001',
        legal_representative: null, legal_representative_id_number: null,
        identity_docs: [], client_type_label: '自然人',
      },
      isLoading: false,
      error: null,
    } as ReturnType<typeof useClient>)

    render(<ClientForm clientId="1" mode="edit" />)
    expect(screen.getByText('基本信息')).toBeInTheDocument()
    expect(screen.getByText('财产线索')).toBeInTheDocument()
    expect(screen.getByText('证件管理')).toBeInTheDocument()
  })

  it('shows cancel and save buttons', () => {
    render(<ClientForm mode="create" />)
    expect(screen.getByText('取消')).toBeInTheDocument()
    expect(screen.getByText('保存')).toBeInTheDocument()
  })
})
