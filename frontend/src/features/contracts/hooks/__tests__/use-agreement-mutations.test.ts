vi.mock('../api', () => ({
  agreementsApi: {
    list: vi.fn().mockResolvedValue([]),
    create: vi.fn().mockResolvedValue({}),
    update: vi.fn().mockResolvedValue({}),
    remove: vi.fn().mockResolvedValue({}),
    download: vi.fn().mockResolvedValue({}),
  },
}))

vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>()
  return {
    ...actual,
    useQuery: vi.fn().mockReturnValue({ data: [], isLoading: false }),
    useMutation: vi.fn().mockReturnValue({ mutate: vi.fn(), isPending: false }),
    useQueryClient: vi.fn().mockReturnValue({ invalidateQueries: vi.fn() }),
  }
})

import { useAgreementMutations } from '../use-agreement-mutations'

describe('contracts/hooks/use-agreement-mutations', () => {
  it('exports useAgreementMutations function', () => {
    expect(typeof useAgreementMutations).toBe('function')
  })

  it('returns expected mutation functions', () => {
    const result = useAgreementMutations()
    expect(result).toHaveProperty('createAgreement')
    expect(result).toHaveProperty('deleteAgreement')
  })
})
