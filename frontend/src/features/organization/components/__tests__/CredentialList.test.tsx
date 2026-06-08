vi.mock('../../hooks/use-credentials', () => ({
  useCredentials: vi.fn().mockReturnValue({ data: [], isLoading: false }),
}))
vi.mock('../../hooks/use-credential-mutations', () => ({
  useCredentialMutations: () => ({
    deleteCredential: { mutate: vi.fn(), isPending: false },
    createCredential: { mutate: vi.fn(), isPending: false },
    updateCredential: { mutate: vi.fn(), isPending: false },
  }),
}))
vi.mock('../../hooks/use-lawyers', () => ({
  useLawyers: () => ({ data: [{ id: 1, real_name: '张三', username: 'zhang' }], isLoading: false }),
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import { render, screen } from '@testing-library/react'
import { CredentialList } from '../CredentialList'
import { useCredentials } from '../../hooks/use-credentials'

describe('CredentialList', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders create button and filter', () => {
    render(<CredentialList />)
    expect(screen.getByText('新建凭证')).toBeInTheDocument()
    expect(screen.getByText('全部律师')).toBeInTheDocument()
  })

  it('shows empty state when no credentials', () => {
    vi.mocked(useCredentials).mockReturnValue({ data: [], isLoading: false } as any)
    render(<CredentialList />)
    expect(screen.getByText('暂无凭证数据')).toBeInTheDocument()
  })
})
