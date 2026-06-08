vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useMutation: vi.fn((config) => ({
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    isPending: false,
    ...config,
  })),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/lib/api', () => ({
  resolveMediaUrl: vi.fn((url: string | null) => url),
  createFeatureApiClient: vi.fn(),
  API_BASE_URL: 'http://localhost:8002/api/v1',
  BACKEND_URL: 'http://localhost:8002',
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...p }: Record<string, unknown>) => <button {...p}>{children}</button>,
}))

vi.mock('@/components/ui/card', () => ({
  Card: ({ children, ...p }: Record<string, unknown>) => <div {...p}>{children}</div>,
}))

vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  DialogContent: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  DialogFooter: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  DialogHeader: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  DialogTitle: ({ children }: Record<string, unknown>) => <h2>{children}</h2>,
}))

vi.mock('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  AlertDialogAction: ({ children, ...p }: Record<string, unknown>) => <button {...p}>{children}</button>,
  AlertDialogCancel: ({ children }: Record<string, unknown>) => <button>{children}</button>,
  AlertDialogContent: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: Record<string, unknown>) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: Record<string, unknown>) => <h2>{children}</h2>,
}))

vi.mock('@/components/ui/select', () => ({
  Select: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  SelectContent: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  SelectItem: ({ children, value }: Record<string, unknown>) => <option value={value}>{children}</option>,
  SelectTrigger: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  SelectValue: () => <span />,
}))

vi.mock('@/components/ui/input', () => ({
  Input: (props: Record<string, unknown>) => <input {...props} />,
}))

vi.mock('@/components/ui/label', () => ({
  Label: ({ children }: Record<string, unknown>) => <label>{children}</label>,
}))

vi.mock('lucide-react', () => {
  const Icon = (p: Record<string, unknown>) => <svg data-testid="icon" {...p} />
  return {
    Plus: Icon, Trash2: Icon, Eye: Icon, FileText: Icon,
    Image: Icon, Calendar: Icon, Upload: Icon, Merge: Icon,
  }
})

vi.mock('date-fns', () => ({
  format: vi.fn(() => '2024年01月01日 12:00'),
}))

vi.mock('date-fns/locale', () => ({
  zhCN: {},
}))

vi.mock('../../hooks/use-identity-doc-mutations', () => ({
  useIdentityDocMutations: vi.fn(() => ({
    addDoc: { mutateAsync: vi.fn(), isPending: false },
    deleteDoc: { mutateAsync: vi.fn(), isPending: false },
  })),
}))

vi.mock('../api', () => ({
  clientApi: {
    mergeIdCard: vi.fn(),
  },
}))

import { render, screen } from '@testing-library/react'
import { IdentityDocManager } from '../IdentityDocManager'
import type { IdentityDoc } from '../../types'

const mockDocs: IdentityDoc[] = [
  { id: 1, doc_type: 'id_card', file_path: '/files/id.jpg', uploaded_at: '2024-01-01T12:00:00', media_url: '/media/id.jpg' },
]

describe('IdentityDocManager', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders doc count', () => {
    render(<IdentityDocManager clientId="1" clientType="natural" docs={mockDocs} />)
    expect(screen.getByText('共 1 份证件')).toBeInTheDocument()
  })

  it('renders add button', () => {
    render(<IdentityDocManager clientId="1" clientType="natural" docs={[]} />)
    const addButtons = screen.getAllByText('添加证件')
    expect(addButtons.length).toBeGreaterThanOrEqual(1)
  })

  it('renders merge id card button', () => {
    render(<IdentityDocManager clientId="1" clientType="natural" docs={[]} />)
    expect(screen.getByText('合并身份证')).toBeInTheDocument()
  })

  it('renders empty state when no docs', () => {
    render(<IdentityDocManager clientId="1" clientType="natural" docs={[]} />)
    expect(screen.getByText('暂无证件')).toBeInTheDocument()
    expect(screen.getByText('点击「添加证件」上传')).toBeInTheDocument()
  })

  it('renders doc cards when docs are provided', () => {
    render(<IdentityDocManager clientId="1" clientType="natural" docs={mockDocs} />)
    const idCards = screen.getAllByText('身份证')
    expect(idCards.length).toBeGreaterThanOrEqual(1)
  })

  it('renders multiple doc count', () => {
    const docs: IdentityDoc[] = [
      { id: 1, doc_type: 'id_card', file_path: '/files/id.jpg', uploaded_at: '2024-01-01T12:00:00', media_url: '/media/id.jpg' },
      { id: 2, doc_type: 'passport', file_path: '/files/passport.jpg', uploaded_at: '2024-01-02T12:00:00', media_url: '/media/passport.jpg' },
    ]
    render(<IdentityDocManager clientId="1" clientType="natural" docs={docs} />)
    expect(screen.getByText('共 2 份证件')).toBeInTheDocument()
  })
})
