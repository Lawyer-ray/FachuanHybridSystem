vi.mock('../api', () => ({
  teamApi: {
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

import { useTeamMutations } from '../use-team-mutations'

describe('organization/hooks/use-team-mutations', () => {
  it('exports useTeamMutations function', () => {
    expect(typeof useTeamMutations).toBe('function')
  })

  it('returns create, update, and delete mutations', () => {
    const result = useTeamMutations()
    expect(result).toHaveProperty('createTeam')
    expect(result).toHaveProperty('updateTeam')
    expect(result).toHaveProperty('deleteTeam')
  })
})
