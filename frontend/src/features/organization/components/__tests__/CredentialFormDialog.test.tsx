vi.mock('../../hooks/use-credential-mutations', () => ({
  useCredentialMutations: () => ({
    createCredential: { mutate: vi.fn(), isPending: false },
    updateCredential: { mutate: vi.fn(), isPending: false },
  }),
}))

vi.mock('../../hooks/use-lawyers', () => ({
  useLawyers: () => ({ data: [{ id: 1, real_name: '张三', username: 'zhang' }], isLoading: false }),
}))

vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children }: any) => <div>{children}</div>,
  DialogContent: ({ children }: any) => <div>{children}</div>,
  DialogDescription: ({ children }: any) => <p>{children}</p>,
  DialogFooter: ({ children }: any) => <div>{children}</div>,
  DialogHeader: ({ children }: any) => <div>{children}</div>,
  DialogTitle: ({ children }: any) => <h2>{children}</h2>,
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import { render, screen } from '@testing-library/react'
import { CredentialFormDialog } from '../CredentialFormDialog'

describe('CredentialFormDialog', () => {
  it('renders create mode title when open', () => {
    render(<CredentialFormDialog open onOpenChange={vi.fn()} />)
    expect(screen.getByText('新建凭证')).toBeInTheDocument()
  })

  it('renders edit mode title', () => {
    const cred = { id: 1, lawyer: 1, site_name: '威科', url: '', account: 'admin', created_at: '', updated_at: '' }
    render(<CredentialFormDialog open onOpenChange={vi.fn()} credential={cred} />)
    expect(screen.getByText('编辑凭证')).toBeInTheDocument()
  })

  it('renders form fields', () => {
    render(<CredentialFormDialog open onOpenChange={vi.fn()} />)
    expect(screen.getByPlaceholderText('请输入网站名称')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('请输入账号')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('请输入密码')).toBeInTheDocument()
  })

  it('renders save and cancel buttons', () => {
    render(<CredentialFormDialog open onOpenChange={vi.fn()} />)
    expect(screen.getByText('保存')).toBeInTheDocument()
    expect(screen.getByText('取消')).toBeInTheDocument()
  })

  it('shows password placeholder in edit mode', () => {
    const cred = { id: 1, lawyer: 1, site_name: '威科', url: '', account: 'admin', created_at: '', updated_at: '' }
    render(<CredentialFormDialog open onOpenChange={vi.fn()} credential={cred} />)
    expect(screen.getByPlaceholderText('留空表示不修改')).toBeInTheDocument()
  })
})
