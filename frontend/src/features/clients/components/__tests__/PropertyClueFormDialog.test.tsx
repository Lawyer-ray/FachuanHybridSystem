vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useMutation: vi.fn((config) => ({
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    isPending: false,
    ...config,
  })),
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...p }: Record<string, unknown>) => <button {...p}>{children}</button>,
}))

vi.mock('@/components/ui/input', () => ({
  Input: (props: Record<string, unknown>) => <input {...props} />,
}))

vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  DialogContent: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  DialogFooter: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  DialogHeader: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  DialogTitle: ({ children }: Record<string, unknown>) => <h2>{children}</h2>,
}))

vi.mock('@/components/ui/form', () => ({
  Form: ({ children }: { children: React.ReactNode }) => <form>{children}</form>,
  FormControl: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  FormField: ({ render: renderFn }: { render: (props: { field: Record<string, unknown> }) => React.ReactNode }) =>
    renderFn({ field: { value: 'bank', onChange: vi.fn(), onBlur: vi.fn(), name: 'clue_type', ref: vi.fn() } }),
  FormItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  FormLabel: ({ children }: { children: React.ReactNode }) => <label>{children}</label>,
  FormMessage: () => <div />,
}))

vi.mock('@/components/ui/select', () => ({
  Select: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  SelectContent: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  SelectItem: ({ children, value }: Record<string, unknown>) => <option value={value}>{children}</option>,
  SelectTrigger: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  SelectValue: () => <span />,
}))

vi.mock('lucide-react', () => {
  const Icon = (p: Record<string, unknown>) => <svg data-testid="icon" {...p} />
  return { Loader2: Icon, Paperclip: Icon, X: Icon }
})

vi.mock('../../api', () => ({
  clientApi: {
    getContentTemplate: vi.fn().mockResolvedValue({ clue_type: 'bank', template: 'template text' }),
  },
}))

vi.mock('../../hooks/use-property-clue-mutations', () => ({
  usePropertyClueMutations: vi.fn(() => ({
    createClue: { mutateAsync: vi.fn().mockResolvedValue({ id: 1 }), isPending: false },
    updateClue: { mutateAsync: vi.fn().mockResolvedValue({ id: 1 }), isPending: false },
    uploadAttachment: { mutateAsync: vi.fn().mockResolvedValue({ id: 1 }), isPending: false },
  })),
}))

import { render, screen } from '@testing-library/react'
import { PropertyClueFormDialog } from '../PropertyClueFormDialog'

describe('PropertyClueFormDialog', () => {
  const defaultProps = {
    clientId: 1,
    clue: null,
    open: true,
    onOpenChange: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders create title when no clue is provided', () => {
    render(<PropertyClueFormDialog {...defaultProps} />)
    expect(screen.getByText('新建财产线索')).toBeInTheDocument()
  })

  it('renders edit title when clue is provided', () => {
    render(
      <PropertyClueFormDialog
        {...defaultProps}
        clue={{
          id: 1, client_id: 1, clue_type: 'bank', clue_type_label: '银行账户',
          content: 'test', attachments: [], created_at: '2024-01-01', updated_at: '2024-01-01',
        }}
      />,
    )
    expect(screen.getByText('编辑财产线索')).toBeInTheDocument()
  })

  it('renders form labels', () => {
    render(<PropertyClueFormDialog {...defaultProps} />)
    expect(screen.getByText('线索类型')).toBeInTheDocument()
    expect(screen.getByText('线索内容')).toBeInTheDocument()
  })

  it('renders cancel and create buttons', () => {
    render(<PropertyClueFormDialog {...defaultProps} />)
    expect(screen.getByText('取消')).toBeInTheDocument()
    expect(screen.getByText('创建')).toBeInTheDocument()
  })

  it('renders save button in edit mode', () => {
    render(
      <PropertyClueFormDialog
        {...defaultProps}
        clue={{
          id: 1, client_id: 1, clue_type: 'bank', clue_type_label: '银行账户',
          content: 'test', attachments: [], created_at: '2024-01-01', updated_at: '2024-01-01',
        }}
      />,
    )
    expect(screen.getByText('保存')).toBeInTheDocument()
  })

  it('shows attachment upload section in create mode', () => {
    render(<PropertyClueFormDialog {...defaultProps} />)
    expect(screen.getByText('附件')).toBeInTheDocument()
  })
})
