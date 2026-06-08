vi.mock('../api', () => ({
  lawyerApi: {
    create: vi.fn().mockResolvedValue({ id: 1 }),
    update: vi.fn().mockResolvedValue({ id: 1 }),
    delete: vi.fn().mockResolvedValue(undefined),
  },
}))

vi.mock('./use-lawyer', () => ({
  lawyerQueryKey: (id: number) => ['lawyer', id],
}))

vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>()
  return {
    ...actual,
    useMutation: vi.fn().mockReturnValue({ mutate: vi.fn(), isPending: false }),
    useQueryClient: vi.fn().mockReturnValue({
      invalidateQueries: vi.fn(),
      removeQueries: vi.fn(),
      setQueryData: vi.fn(),
    }),
  }
})

import { useLawyerMutations } from '../use-lawyer-mutations'

describe('organization/hooks/use-lawyer-mutations', () => {
  it('exports useLawyerMutations function', () => {
    expect(typeof useLawyerMutations).toBe('function')
  })

  it('returns create, update, and delete mutations', () => {
    const result = useLawyerMutations()
    expect(result).toHaveProperty('createLawyer')
    expect(result).toHaveProperty('updateLawyer')
    expect(result).toHaveProperty('deleteLawyer')
  })
})
