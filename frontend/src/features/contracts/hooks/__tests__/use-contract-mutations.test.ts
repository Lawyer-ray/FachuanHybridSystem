vi.mock('../api', () => ({
  contractApi: {
    create: vi.fn().mockResolvedValue({ id: 1 }),
    update: vi.fn().mockResolvedValue({ id: 1 }),
    delete: vi.fn().mockResolvedValue(undefined),
    duplicateContract: vi.fn().mockResolvedValue({ id: 2 }),
    createCaseFromContract: vi.fn().mockResolvedValue({ case_id: 1 }),
    renewAdvisorContract: vi.fn().mockResolvedValue({ id: 1 }),
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

import { useContractMutations } from '../use-contract-mutations'

describe('contracts/hooks/use-contract-mutations', () => {
  it('exports useContractMutations function', () => {
    expect(typeof useContractMutations).toBe('function')
  })

  it('returns all mutation operations', () => {
    const result = useContractMutations()
    expect(result).toHaveProperty('createContract')
    expect(result).toHaveProperty('updateContract')
    expect(result).toHaveProperty('deleteContract')
    expect(result).toHaveProperty('duplicateContract')
    expect(result).toHaveProperty('createCaseFromContract')
    expect(result).toHaveProperty('renewAdvisorContract')
  })
})
