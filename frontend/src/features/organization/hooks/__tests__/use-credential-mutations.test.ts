vi.mock('../api', () => ({
  credentialApi: {
    create: vi.fn().mockResolvedValue({ id: 1 }),
    update: vi.fn().mockResolvedValue({ id: 1 }),
    delete: vi.fn().mockResolvedValue(undefined),
  },
}))

vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>()
  return {
    ...actual,
    useMutation: vi.fn().mockReturnValue({ mutate: vi.fn(), isPending: false }),
    useQueryClient: vi.fn().mockReturnValue({
      invalidateQueries: vi.fn(),
    }),
  }
})

import { useCredentialMutations } from '../use-credential-mutations'

describe('organization/hooks/use-credential-mutations', () => {
  it('exports useCredentialMutations function', () => {
    expect(typeof useCredentialMutations).toBe('function')
  })

  it('returns create, update, and delete mutations', () => {
    const result = useCredentialMutations()
    expect(result).toHaveProperty('createCredential')
    expect(result).toHaveProperty('updateCredential')
    expect(result).toHaveProperty('deleteCredential')
  })
})
